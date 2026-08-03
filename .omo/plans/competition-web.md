# competition-web - Work Plan

## TL;DR (For humans)

**What you'll get:** 一个能跑起来的音游比赛网站——展示比赛与宣传图、注册账号、3 人组队或个人报名参赛、三种赛制（分组循环/瑞士轮/单败淘汰）自动编排与排名、比赛奖励积分与活动积分双轨排行、管理后台（选手/权限/裁判/活动积分/异常流量监控），并且能把 demo「三角占领」作为玩法模板嵌进比赛对局中实时对战。先在本机跑通全部功能，再按文档部署到服务器（国内轻量服务器单机部署，Docker 或裸进程二选一）。

**Why this approach:** 全套功能只用一个 Python 进程 + 一个 SQLite 文件 + 一个前端构建产物，50 人规模足够且最容易部署；玩法做成插件规范，demo 规则代码一行不改，只包一层适配就能复用，以后加新玩法只需按规范加目录。

**What it will NOT do:** 不做支付、邮件短信、第三方登录；不做应用层防火墙/反 DDoS；不引入 Redis/消息队列（单进程就够）；不改动 demo 玩法规则本身；不做「出线第二阶段」等未要求的多阶段赛制。

**Effort:** XL
**Risk:** Medium - 唯一实质风险是 Python 3.14 依赖兼容（M0 首日实测，失败即降 3.12）与 demo 改造适配层（规则零改动但补身份/持久化/防刷）
**Decisions to sanity-check:** ① 比赛对局中仅裁判（referee）与比赛管理员（admin）可操作棋盘，选手只读观看——最终确认（用户 2026-08-02）；② 队伍获奖时每名成员各得全额积分；③ 平局=双方各 0.5（循环/瑞士），单败淘汰平局由裁判指定胜者；④ 瑞士轮默认轮数封顶 7 轮。

Your next move: 批准后运行 `$start-work competition-web` 开始执行（或先要求高精度评审）。完整执行细节见下文。

---

> TL;DR (machine): XL effort, Medium risk - 26 implementation todos + 4 verification tasks, single-process FastAPI+Vue3+SQLite monolith with plugin-adapted demo as gameplay template; git-managed milestones M0-M11, local-first then Docker/systemd deploy.

## Scope
### Must have
- 比赛展示页：当前赛制安排、宣传插画位（开发期占位图）、报名入口
- 账号体系：注册/登录/登出（JWT httpOnly Cookie + SameSite=Lax + Origin 校验防 CSRF + bcrypt）；3 人组队（队长建队+邀请）；个人参赛
- 参赛单位模型：个人=1 人队伍，支持 team / individual / mixed 三种比赛参赛类型
- 三种赛制引擎（统一 TournamentEngine 接口）：分组循环赛（组内轮转）、瑞士轮、单败淘汰；支持配置组数/轮数/种子/季军赛；平局/轮空/同分决胜规则已固化（见 todos 9-11）
- 单场比赛排名 + 奖励积分（赛制结束自动结算，队伍成员各得全额）+ 独立排行榜页（场次榜/全局榜）
- 管理后台：选手账号管理、权限分配（admin/referee/player 三角色 RBAC + 比赛裁判组指派）、活动积分手动发放、异常流量检测与监控页、玩法模板管理（列表/启停）
- 玩法模板插件系统：GameplayPlugin 规范 + registry 自动注册；模板一 triangle_occupy（demo「三角占领」改造：规则逻辑零改动，适配层补身份映射/歌曲库来源/持久化恢复/平局语义/结果校验/测试）；**对局中仅 referee/admin 可操作棋盘，选手只读（用户 2026-08-02 最终确认）**
- 异常流量四件套：登录爆破防护（5 次失败锁定 15 分钟，IP+账号双维度）、API 全局限流（slowapi）、成绩防刷（validate_result 值域/顺序/频率 + 裁判可撤销）、AuditLog + 后台流量监控页
- 全站实时：对局进行中 WebSocket 状态推送（Cookie 鉴权 + 订阅白名单 + 消息频率限制，单进程连接管理器）
- 人数上限：比赛可配 max_participants 默认 50，满员拒绝报名
- git 项目管理：main/dev/feature 分支 + Conventional Commits + 里程碑 tag v0.x
- 本地先跑通（验收清单）→ 再部署；部署方案：**国内轻量服务器单机部署（腾讯云/阿里云香港 2C2G 优先，免备案）**，Docker Compose 或 systemd 二选一 + Caddy HTTPS + SQLite 定时备份 + 恢复演练；不使用 Cloudflare Pages（国内访问慢/不稳定，观众主要在国内——2026-08-02 决策）
- 测试：pytest（后端，含赛制引擎/插件/认证/限流/CSRF 单测）+ 前端构建验证 + M10 全链路联调验收清单

### Must NOT have (guardrails, anti-slop, scope boundaries)
- 不做应用层 WAF / DDoS 防护（交服务器防火墙/CDN，仅文档说明）
- 不做支付、邮件、短信、第三方登录、验证码（50 人规模不需要）
- 不做 Redis / 消息队列 / 多进程部署（单进程单体；文档注明未来扩展路径即可）
- 不改动 demo「三角占领」的玩法规则核心逻辑（GameController 规则代码零改动，只做适配层包装）
- 不做移动端 App / PWA
- 不做用户上传内容审核系统；不引入重量级前端（禁止把 Element Plus 换成自研组件库以炫技；管理后台用现成组件）
- 数据库只用 SQLite（禁止引入 PostgreSQL/MySQL）
- 不在本阶段做 CI/CD 流水线（单人项目，本地 pytest 足够；可留 .github/workflows 占位但不要求跑通）
- 不做赛制第二阶段/出线晋级（单场单一赛制）
- 不做 iframe 玩法嵌入过渡方案（直接组件化，避免双写）

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD（赛制引擎/插件/认证/限流先写测试后实现）+ pytest + httpx（内存 SQLite）；前端用 `npm run build` + `vite build` 产物 + Playwright 冒烟
- 证据目录：`.omo/evidence/task-<N>-competition-web.<ext>`（本计划不使用 ulw-loop，统一用 .omo/evidence/）
- 每个 todo 的 Acceptance criteria 必须能通过命令行断言验证（pytest 单测、curl 冒烟、构建产物检查）
- QA 场景一律给出精确工具调用（pytest 指定文件、curl 指定端点+期望码、node 脚本断言），happy + failure 双路径，产出证据文件

## Execution strategy
### Parallel execution waves
> Wave 1（M0 初始化）：1,2,3
> Wave 2（M1 账号权限）：4,5
> Wave 3（M2 队伍报名）：6,7
> Wave 4（M3 比赛管理）：8
> Wave 5（M4 赛制引擎，三者可并行）：9,10,11
> Wave 6（M5 玩法插件规范+改造）：12,13
> Wave 7（M6 对局实时 + 限流审计）：14,15,16,18
> Wave 8（M7 积分排行）：17
> Wave 9（M8 后台 + M9 前端打磨）：19,20,21,22,23
> Wave 10（M10 种子数据 + 联调验收）：24,25
> Wave 11（M11 部署上线）：26

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | — | 2,3 | — |
| 2 | 1 | 4,5,6 | 3 |
| 3 | 1 | 19,22,23,24 | 2 |
| 4 | 2 | 5,6,16 | — |
| 5 | 4 | 7,22,23 | 6 |
| 6 | 2,4 | 7 | 5 |
| 7 | 5,6 | 8 | — |
| 8 | 7 | 9,10,11 | — |
| 9 | 7,8 | 14 | 10,11 |
| 10 | 7,8 | 12,14 | 9,11 |
| 11 | 7,8 | 12,15 | 9,10 |
| 12 | 10,11 | 13,14 | — |
| 13 | 12 | 14,18 | — |
| 14 | 9,12,13 | 15,18,19 | — |
| 15 | 11,14 | 16,18 | — |
| 16 | 4,15 | 17,20,21 | — |
| 17 | 16 | 20,21 | — |
| 18 | 12,13,15 | 19 | 20,21 |
| 19 | 3,15,18 | 22,23 | 20,21 |
| 20 | 3,8,17 | 22 | 19,21 |
| 21 | 16,17,18 | 22 | 19,20 |
| 22 | 3,19,20,21 | 23 | — |
| 23 | 3,19,22 | 24 | — |
| 24 | 1-23 | 25 | — |
| 25 | 全部 1-24 | 26 | — |
| 26 | 25 | — | — |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. git 初始化 + 仓库骨架 + Python 3.14 依赖兼容性实测
  What to do / Must NOT do: 在 D:\myproject1\competition_web 执行 git init；创建 backend/、frontend/、deploy/、docs/ 目录与 .gitignore（忽略 .venv/、node_modules/、__pycache__/、*.db、*.db-wal、*.db-shm、.env）；创建 backend/requirements.txt（fastapi、uvicorn[standard]、sqlalchemy、pydantic、pydantic-settings、bcrypt、PyJWT、slowapi、httpx、pytest、python-multipart）；执行 pip install 实测 Python 3.14.0 兼容性。Must NOT: 不在本任务写任何业务代码；不提交 .env 或密钥。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 2,3
  References (executor has NO interview context - be exhaustive): .omo/drafts/competition-web.md（环境发现：Python 3.14.0/Node v24/Git 2.52.0/Docker 未装，Windows 11）；plan.md §四（环境确认表）与 §三（技术栈）
  Acceptance criteria (agent-executable): `git -C D:\myproject1\competition_web status` 显示 on branch main 且无报错；`cd backend && python -c "import fastapi, sqlalchemy, pydantic, bcrypt, jwt, slowapi"` 全部成功；`git log --oneline` 有 initial commit
  QA scenarios (name the exact tool + invocation): happy — 运行 `git log --oneline` 输出至少 1 条提交；failure — 在 requirements.txt 注入不存在的包名 `nonexistent-pkg-xyz` 后 `pip install -r requirements.txt` 返回非零退出码，证据 .omo/evidence/task-1-competition-web.txt
  Commit: Y | chore: 初始化仓库骨架与依赖清单

- [x] 2. 后端骨架：FastAPI 应用入口 + 配置 + SQLite 连接 + /api/health
  What to do / Must NOT do: 创建 backend/app/main.py（FastAPI 实例、CORS 中间件、路由挂载、静态文件托管目录预留）、config.py（pydantic-settings 读 .env：SECRET_KEY、DB_PATH、DATABASE_URL=sqlite:///./competition.db）、db.py（SQLAlchemy engine + SessionLocal + Base + WAL PRAGMA）、health 路由返回 {"status":"ok"}。Must NOT: 不实现任何业务路由；不在本任务引入前端。
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 4,5,6,10,11,16,17
  References (executor has NO interview context - be exhaustive): demo/main.py:1-24（FastAPI 入口+StaticFiles 模式可参考）；plan.md §五（架构图与目录结构）
  Acceptance criteria (agent-executable): `cd backend && python -m uvicorn app.main:app --port 8000 &` 后 `curl http://127.0.0.1:8000/api/health` 返回 `{"status":"ok"}`；`pytest tests/test_health.py -q` 通过（测试用 TestClient）
  QA scenarios: happy — curl /api/health 返回 200 + {"status":"ok"}；failure — 用错误路径 `curl http://127.0.0.1:8000/api/healthx` 返回 404，证据 .omo/evidence/task-2-competition-web.txt
  Commit: Y | feat: 后端骨架与健康检查

- [x] 3. 前端骨架：Vite + Vue3 + Pinia + Router + Element Plus + 代理
  What to do / Must NOT do: 在 frontend/ 用 Vite 创建 Vue3+TS 项目；安装 pinia、vue-router、element-plus、axios；配置 vite.config.ts 代理 /api 与 /ws → http://127.0.0.1:8000；创建基础布局（Header/Footer）、路由占位页（/、/login、/competitions、/admin、/profile）；package.json scripts: dev/build。Must NOT: 不实现业务页面细节；不引入多余 UI 库。
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 19,22,23,24
  References (executor has NO interview context - be exhaustive): plan.md §三（前端选型表）、§五（目录结构 frontend/src/views）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 退出码 0 且 dist/ 生成 index.html；`npm run dev` 启动后 `curl http://localhost:5173` 返回 200
  QA scenarios: happy — npm run build 成功生成 dist/；failure — 临时在 src/main.ts 引入不存在的模块 `import x from './nonexistent'` 后 npm run build 非零退出，改回后恢复，证据 .omo/evidence/task-3-competition-web.txt
  Commit: Y | feat: 前端 Vite+Vue3 骨架

- [x] 4. 账号认证：User 模型 + 注册/登录/登出 + JWT httpOnly Cookie
  What to do / Must NOT do: backend/app/models/user.py（User: id, username unique, email, password_hash, role, status, created_at）；core/security.py（bcrypt hash/verify、PyJWT create/decode，token 存 httpOnly cookie 且 **SameSite=Lax**）；core/csrf.py（对非 GET/HEAD/OPTIONS 请求校验 Origin/Referer 头是否为本站，拒绝跨站状态变更请求——CSRF 防护，Metis 审查补入）；api/auth.py（POST /api/auth/register、/login、/logout、GET /api/auth/me）；schema 用 pydantic 校验（用户名 3-20 字符、密码 ≥6）。Must NOT: 不使用明文密码；不把 token 放 localStorage；不实现角色权限逻辑（下一任务）。
  Parallelization: Wave 2 | Blocked by: 2 | Blocks: 6,7,16
  References (executor has NO interview context - be exhaustive): plan.md §九（权限系统，role 枚举）；§十三 API 概要 /auth 行；Metis 审查 E12（httpOnly cookie 无 CSRF 防护风险，已补 SameSite+Origin 校验）
  Acceptance criteria (agent-executable): pytest tests/test_auth.py 全绿（注册成功→me 返回正确 username；重复注册 400；错误密码 401；登出后 me 401）；tests/test_csrf.py 全绿（带伪造 Origin 的 POST 被 403 拒绝，同源 POST 通过）；`curl -X POST http://127.0.0.1:8000/api/auth/register -H "Content-Type: application/json" -d '{"username":"t1","password":"pass123","email":"t1@e.com"}'` 返回 200 且 Set-Cookie 含 token 与 SameSite=Lax
  QA scenarios: happy — 完整注册-登录-me-登出链断言 200；failure — 已存在用户名注册返回 400、错误密码登录返回 401、伪造 Origin 的 POST 返回 403，证据 .omo/evidence/task-4-competition-web.txt
  Commit: Y | feat: 账号注册登录与 JWT Cookie 会话

- [x] 5. 权限系统：三角色 RBAC 依赖注入 + 用户管理 API
  What to do / Must NOT do: core/rbac.py（get_current_user 依赖、require_role("admin"/"referee"/"player") 依赖、User.role 枚举 admin/referee/player）；api/admin_users.py（仅 admin：GET/PATCH /api/admin/users 列表/封禁/改角色/重置密码）。Must NOT: 角色逻辑不写在业务路由内联判断；不允许越权操作。
  Parallelization: Wave 2 | Blocked by: 4 | Blocks: 7,22
  References (executor has NO interview context - be exhaustive): plan.md §九（RBAC 表）；demo 无鉴权可对照（demo/api/routes.py:14-176 全部无认证）
  Acceptance criteria (agent-executable): pytest tests/test_rbac.py 全绿（player 调 /api/admin/users 403；admin 调 200；未登录 401）；`curl -H "Cookie: <admin-token>" http://127.0.0.1:8000/api/admin/users` 200
  QA scenarios: happy — admin 列表/封禁/改角色成功；failure — player 角色访问 admin 接口 403、无 cookie 401，证据 .omo/evidence/task-5-competition-web.txt
  Commit: Y | feat: 三角色 RBAC 与用户管理

- [x] 6. 队伍模块：Team/TeamMember 模型 + 建队/加人/退队（≤3 人）
  What to do / Must NOT do: models/team.py（Team: id, name unique, captain_id, created_at；TeamMember: team_id, user_id）；api/teams.py（POST /api/teams 建队、POST /api/teams/{id}/members 加人、DELETE 退队）；校验人数 ≤3、队长权限、每人限 1 队。Must NOT: 不实现报名（下一任务）；不做队伍解散审批流。
  Parallelization: Wave 3 | Blocked by: 2,4 | Blocks: 7,8,9
  References (executor has NO interview context - be exhaustive): plan.md §六（数据模型 Team/TeamMember）；§二 2.1（参赛单位模型）
  Acceptance criteria (agent-executable): pytest tests/test_teams.py 全绿（建队成功；第 4 人加队 400；非队长加人 403；用户已在其他队 400）
  QA scenarios: happy — 队长建队并加 2 名队员成功；failure — 第 4 名队员加入返回 400，证据 .omo/evidence/task-6-competition-web.txt
  Commit: Y | feat: 队伍与成员管理

- [x] 7. 报名模块：Registration + 个人/队伍/混合参赛类型 + 人数上限
  What to do / Must NOT do: models/registration.py（Registration: id, competition_id, participant_type(team/individual), team_id nullable, user_id nullable, status(pending/approved/rejected), approved_by）；api/registrations.py（POST 报名、DELETE 撤销、GET 我的报名）；核心逻辑：个人报名创建"1 人参赛单位"，队伍报名校验队伍人数；混合模式下两者都允许；**人数上限（Metis E5 修正）：报名校验 competition.max_participants（默认 50），已批准参赛单位数达到上限返回 400「报名已满」**。Must NOT: 不创建 Competition 模型（下一任务用 mock 或先建表）；报名数上限字段在下一任务才落库，本任务用 config 常量兜底。
  Parallelization: Wave 3 | Blocked by: 6 | Blocks: 10
  References (executor has NO interview context - be exhaustive): plan.md §二 2.1（参赛单位模型）、§六（Registration 实体）；Metis 审查 E5（人数上限未强制，本 todo 固化）
  Acceptance criteria (agent-executable): pytest tests/test_registrations.py 全绿（个人报名成功；队伍报名成功；重复报名 400；撤销后 200；**达到 max_participants 后新报名 400**）
  QA scenarios: happy — 个人+队伍报名均成功入库；failure — 同一用户对同一比赛重复报名 400、满员后报名 400，证据 .omo/evidence/task-7-competition-web.txt
  Commit: Y | feat: 报名与参赛单位

- [x] 8. 比赛管理：Competition 模型 + CRUD + 状态机 + 赛制/玩法/积分配置 + 裁判指派
  What to do / Must NOT do: models/competition.py（Competition: id, name, banner_url, description, participant_type, tournament_format, format_config JSON, points_rule JSON, gameplay_plugin, song_lib JSON, max_participants int 默认 50, referee_ids JSON（裁判组，Metis E3 修正）, status, start_time/end_time, created_by）；状态机 draft→registration→ongoing→finished/cancelled；api/competitions.py（admin CRUD + 状态流转 + GET 公开列表/详情 + **admin 指派裁判 referee_ids**）；创建时校验 tournament_format 与 gameplay_plugin 是合法枚举、referee_ids 均存在且角色为 referee。Must NOT: 不实现赛制引擎（下一任务）；不做报名与比赛的实体关联逻辑（报名任务已建表）；**出线名额/第二阶段不在 scope（Metis S6 移除）**。
  Parallelization: Wave 4 | Blocked by: 7 | Blocks: 10,11
  References (executor has NO interview context - be exhaustive): plan.md §六（Competition 字段）、§七（赛制枚举）、§二 2.2；Metis 审查 E3（裁判指派流程缺失，本 todo 固化 referee_ids）与 E5/S6
  Acceptance criteria (agent-executable): pytest tests/test_competitions.py 全绿（admin 创建成功；player 创建 403；状态非法流转 400；draft 可含全部配置字段；**指派不存在用户或非 referee 角色 400**；**max_participants 默认 50 且可覆盖**）
  QA scenarios: happy — admin 创建含三种赛制配置的比赛成功；failure — 非法 tournament_format 创建 422/400、指派 player 角色当裁判 400，证据 .omo/evidence/task-8-competition-web.txt
  Commit: Y | feat: 比赛管理与状态机

- [x] 9. 分组循环赛引擎 RoundRobinEngine
  What to do / Must NOT do: tournaments/base.py（TournamentEngine ABC: generate_schedule/record_result/standings/is_complete/next_round）；tournaments/round_robin.py（标准轮转法生成组内 1v1 赛程，支持 group_size 配置）；**平局语义（Metis E1）：draw 计双方各 0.5 胜场**；**轮空语义（Metis E2）：组内奇数队伍时标准轮转法自动产生 bye，轮空计 1 胜场、0 净胜分**；**同分决胜（Metis V1）：胜场→净胜分→相互胜负→种子 id 升序**；纯逻辑无 I/O，输入参赛单位 id 列表+配置，输出轮次/对阵/排名。Must NOT: 不写数据库调用；不处理瑞士轮/淘汰赛（各自独立任务）；不做"出线名额"第二阶段（Metis S6：单场单一赛制，出线配置已从 scope 移除）。
  Parallelization: Wave 5 | Blocked by: 7,8 | Blocks: 18
  References (executor has NO interview context - be exhaustive): plan.md §七（RoundRobinEngine 行）；算法标准：循环赛轮转法（固定 1 号位轮转）；Metis 审查 E1/E2/V1（平局/轮空/同分规则，本 todo 已固化决策）
  Acceptance criteria (agent-executable): pytest tests/test_tournaments/test_round_robin.py 全绿（6 队 3 组：每组 3 队轮转 3 轮每轮 1 场；4 队单组：3 轮每轮 2 场；每人每轮恰好 1 场、对阵不重复；奇数 5 队单组：轮空正确分配且计 1 胜；平局计 0.5 胜；排名按 胜场→净胜分→相互胜负→id 决胜；参赛单位不足 2 抛 ValueError）
  QA scenarios: happy — 奇/偶数队伍数编排断言正确、平局对局排名正确；failure — 参赛单位不足 2 抛 ValueError、非法 group_size 抛 ValueError，证据 .omo/evidence/task-9-competition-web.txt
  Commit: Y | feat: 分组循环赛引擎

- [x] 10. 瑞士轮引擎 SwissEngine
  What to do / Must NOT do: tournaments/swiss.py（按积分相近配对、同分优先、不重复对阵；轮数可配默认 **min(ceil(log2(n))+1, 7)**——与 plan.md 建议 5~6 轮对齐的上限约束，Metis C3 修正）；**平局语义：draw 双方各 0.5 分**；**轮空语义：奇数队轮空计 1 分（视为胜）**；**同分决胜：积分→对手分(Buchholz)→净胜分→种子 id**；实现 record_result 后自动推进下一轮。Must NOT: 不做种子/淘汰逻辑；不做数据库持久化；不引入随机配对（必须确定性算法）。
  Parallelization: Wave 5 | Blocked by: 7,8 | Blocks: 18
  References (executor has NO interview context - be exhaustive): plan.md §七（SwissEngine 行，默认轮数建议）；Metis 审查 C3（推荐轮数与公式冲突，已加上限修正）与 E1/E2
  Acceptance criteria (agent-executable): pytest tests/test_tournaments/test_swiss.py 全绿（8 队 4 轮：每轮 4 场不重复；积分相近优先配对；奇数队轮空处理且计 1 分；draw 计 0.5；轮数耗尽 is_complete=True；n=50 时默认轮数 = 7 不超上限）
  QA scenarios: happy — 8 队跑完 4 轮排名合理（冠军全胜）；failure — 轮数配置为 0 抛 ValueError、同分对局重复配对被拒绝，证据 .omo/evidence/task-10-competition-web.txt
  Commit: Y | feat: 瑞士轮引擎

- [x] 11. 单败淘汰引擎 SingleElimEngine
  What to do / Must NOT do: tournaments/single_elim.py（标准签表：2 的幂补位 bye 轮空、种子排序可选、可配季军赛；record_result 推进；半决赛前种子 1/2 分列两端）；**平局语义（Metis E1）：单败淘汰不接受 draw——若插件返回 draw，由裁判在 API 层指定胜者（必填 winner 参数），引擎校验 winner ∈ {a,b}**；胜者晋级、败者出局（除季军赛）。Must NOT: 不做种子算法的复杂变体；不做复活赛；不支持 draw 结果。
  Parallelization: Wave 5 | Blocked by: 7,8 | Blocks: 18
  References (executor has NO interview context - be exhaustive): plan.md §七（SingleElimEngine 行）；Metis 审查 E1（draw 语义固化：单败淘汰不允许 draw，裁判必填胜者）
  Acceptance criteria (agent-executable): pytest tests/test_tournaments/test_single_elim.py 全绿（8 队→7 场决出冠军；5 队→bye 正确补位；季军赛存在时多 1 场；轮次推进正确；传 draw 结果被拒绝且要求 winner 必填）
  QA scenarios: happy — 5 队含 bye 的完整签表按结果推进到冠军；failure — 对已淘汰队伍 record_result 抛错、draw 结果被拒绝，证据 .omo/evidence/task-11-competition-web.txt
  Commit: Y | feat: 单败淘汰引擎

- [ ] 12. 玩法插件规范与注册表（后端契约）
  What to do / Must NOT do: plugins/base.py（GameplayPlugin ABC: name/version/create_session/get_state/submit_result/validate_result/end_session）；plugins/registry.py（启动时扫描 plugins/ 目录下含 manifest.json 的包并注册、自动挂载 /api/gameplay/<name>/* 路由）；plugins/registry_test 辅助验证。Must NOT: 不实现任何具体玩法；注册表不自动加载非插件目录。
  Parallelization: Wave 6 | Blocked by: 10,11 | Blocks: 15,18
  References (executor has NO interview context - be exhaustive): plan.md §八 8.1（插件规范代码骨架）、§五（plugins/ 目录）
  Acceptance criteria (agent-executable): pytest tests/test_plugins/test_registry.py 全绿（扫描空目录无注册；放入最小假插件 manifest 后注册成功且路由 /api/gameplay/fake/* 可访问；manifest 缺 name/version 抛错）
  QA scenarios: happy — 假插件注册后 GET /api/gameplay/fake/health 200；failure — manifest.json 缺 version 字段注册失败并有明确错误，证据 .omo/evidence/task-12-competition-web.txt
  Commit: Y | feat: 玩法插件规范与注册表

- [ ] 13. 玩法插件 triangle_occupy 后端改造
  What to do / Must NOT do: 新建 plugins/triangle_occupy/（manifest.json + plugin.py + controller/）；把 demo 的 controller/game.py、rules.py、song_lib.py、task_gen.py 复制进来；plugin.py 实现 GameplayPlugin：create_session 用歌曲库生成 cells 初始化、get_state 调 to_state_dict、submit_result 处理 occupy 请求并映射 participant→阵营（defender/attacker）、validate_result 校验身份/时间窗/频率/值域、end_session 调 end_game 返回胜者。**写权限模型（用户 2026-08-02 最终确认，覆盖早前 Metis C1 修正）：只有 referee/admin 可执行 submit_result（occupy/cancel/reoccupy/end），选手只读观看——裁判替双方操作棋盘（符合"赛时控制器"用法：选手在各自设备打音游，裁判在棋盘记录对局状态）**；**cancel 授权（随写权限模型简化）：取消/重占/收局仅限 referee/admin，无需阵营级校验（裁判全权）**；**歌曲库来源（Metis C4/E11 修正）：create_session 的 config 携带 song_lib 数据（demo /api/songs 的 body 格式），不再依赖全局 _songs**；**会话恢复（Metis E9 修正）：state_json 额外保存 elapsed 分钟数，恢复时重建 cells 后设置 `game._start_ts = time.time() - elapsed*60` 避免时钟跳变导致立即超时**；**成绩防刷边界（Metis E7）：validate_result 只做值域/顺序/频率校验，不做分数真实性核验（无服务端模拟器），L1 挑战结果返回 challenge_ok 字段区分**。Must NOT: 不修改 GameController 规则逻辑（game.py 核心方法零改动）；不引入 demo 的 api/routes.py（会话路由由 registry 提供）；选手端不提供任何写操作端点。
  Parallelization: Wave 6 | Blocked by: 10,11 | Blocks: 15,18
  References (executor has NO interview context - be exhaustive): demo/controller/game.py:39-412（GameController 全部方法签名）；demo/api/routes.py:69-163（init/occupy/cancel/reoccupy/end/time_limit 参数与响应格式）；demo/config/rules.json（游戏规则配置）；demo/test_songs.json（歌曲库样例）；demo/controller/song_lib.py:111-112（歌曲数下限 ≥23）；用户 2026-08-02 最终确认：对局操作仅 referee/admin，选手只读（覆盖 Metis C1 修正）
  Acceptance criteria (agent-executable): pytest tests/test_plugins/test_triangle_occupy.py 全绿（create_session 后 get_state 含 board/scores；referee/admin submit_result 合法占领返回 ok；**player 调 submit_result 403**；阵营映射正确；非法 cell_id/队伍 400；**restore 后 elapsed 连续不跳变**；end_session 返回 winner 与比分；**config 带 song_lib 时可 random 初始化，缺 song_lib 抛 400**）
  QA scenarios: happy — 模拟 referee/admin 交替为 defender/attacker 占领后结束，winner 正确；failure — 无会话 id 调用 submit_result 404、选手调 submit_result 403、重复占领被忽略不抛错、恢复会话后不立即超时，证据 .omo/evidence/task-13-competition-web.txt
  Commit: Y | feat: 三角占领玩法插件（demo 适配层）

- [ ] 14. 对局生命周期与玩法会话服务
  What to do / Must NOT do: models/match.py（Match: id, competition_id, round_id, participant_a/b, status, result, **result_type(win/draw，Metis E1/V2 修正)**, referee_id, scheduled_at；GameSession: id, match_id, plugin_name, config JSON, state_json, started_at/ended_at）；services/match_service.py（开对局→创建玩法会话→收局写结果→推进赛制引擎）；api/matches.py（referee 权限：POST /api/matches/**{id}/start**、/end、GET 列表/详情；**对局由赛制引擎 generate_schedule 生成，referee 不手工创建对局（Metis C7 修正）**）；收局后调用对应 TournamentEngine.record_result；**referee 必须是比赛 referee_ids 成员（service 层校验，Metis E3 修正）**；**draw 结果仅在 round_robin/swiss 允许，single_elim 收局时 winner 必填（Metis E1）**。Must NOT: 不实现 WS 推送（下一任务）；不提供对局手工创建端点。
  Parallelization: Wave 7 | Blocked by: 9,12,13 | Blocks: 15,18,19
  References (executor has NO interview context - be exhaustive): plan.md §六（Match/GameSession 字段）、§十三 API 概要 matches 行、§九（referee 权限范围）；Metis 审查 E1/C7（对局来源与 draw 传播，本 todo 固化）
  Acceptance criteria (agent-executable): pytest tests/test_matches.py 全绿（referee 对已编排对局 start→session 生成；end 后 match.result 与 result_type 写入且引擎排名推进；player 调 start 403；非 referee_ids 成员 403；**single_elim 对局 end 传 draw 被拒 400 要求 winner**）
  QA scenarios: happy — 完整 对局 start→玩法→end→排名推进 链；failure — 未开始对局直接 end 400、非指派裁判 start 403，证据 .omo/evidence/task-14-competition-web.txt
  Commit: Y | feat: 对局生命周期与玩法会话

- [x] 15. WebSocket 实时推送 + 对局状态订阅
  What to do / Must NOT do: core/ws_manager.py（连接管理器：连接/断开、按 match_id 订阅、broadcast_state 单进程广播）；api/ws.py（/ws/matches/{match_id} 端点：**Cookie 鉴权（Metis E13 修正）：仅参赛双方成员、该比赛 referee_ids 裁判、admin 可订阅；拒绝其他用户 403**，推送 GameSession.state_json 变更）；玩法会话状态变更时触发广播（service 层回调）。Must NOT: 不做多进程/Redis 方案；不广播敏感管理数据；**不做匿名 WS 连接**。
  Parallelization: Wave 7 | Blocked by: 11,14 | Blocks: 16,18
  References (executor has NO interview context - be exhaustive): demo/api/routes.py:21-41（broadcast_state 模式）、165-176（WS 端点模式）；Metis 审查 E13（WS 无鉴权风险，本 todo 固化 Cookie 鉴权+订阅白名单）
  Acceptance criteria (agent-executable): pytest tests/test_ws.py 全绿（用 TestClient websocket_connect 带登录 Cookie 连接 /ws/matches/{id} 收到初始 state 帧；状态变更后收到更新帧；**未登录 401、非参赛/非裁判用户 403**）
  QA scenarios: happy — 两参赛客户端订阅同一对局都收到广播；failure — 未鉴权连接被拒 401、局外用户被拒 403，证据 .omo/evidence/task-15-competition-web.txt
  Commit: Y | feat: WebSocket 对局实时推送

- [ ] 16. 限流与审计（异常流量检测后端）
  What to do / Must NOT do: core/ratelimit.py（slowapi 集成：/api/auth/login+register 每 IP 每账号 10 次/15 分钟，超限 429；全局 100 次/分/IP；**连续失败 5 次锁定账号 15 分钟——统一为 5 次（Metis C2 修正，plan.md 验收清单 6 次改为 5 次）**；**WS 消息频率限制（Metis E13 修正）：每连接每秒 ≤10 条订阅消息，超限断开**）；models/audit_log.py（AuditLog: id, user_id, action, ip, user_agent, detail, created_at）；core/audit.py（写审计日志装饰器：登录失败/注册/改角色/改分/对局操作）；api/admin_traffic.py（admin 聚合查询：异常登录 TOP、高频 IP、锁定列表）。Must NOT: 不做 WAF/DDoS；不加 Redis 计数（slowapi 内存即可）。
  Parallelization: Wave 7 | Blocked by: 4,15 | Blocks: 17,20,21
  References (executor has NO interview context - be exhaustive): plan.md §十（四件套）、§二 2.4（规模定位）；Metis 审查 C2（锁定阈值 5 vs 6 矛盾，统一 5）与 E13（WS 洪泛）
  Acceptance criteria (agent-executable): pytest tests/test_ratelimit.py + tests/test_audit.py 全绿（同 IP 连输 5 次密码后账号锁定、第 6 次即使密码正确也 423/403；超限 429；审计日志落库；admin 聚合接口 200 且 player 403；**WS 超频连接被断开**）
  QA scenarios: happy — 登录失败 5 次→锁定→admin 后台可见；failure — 超限请求返回 429 而非 200，证据 .omo/evidence/task-16-competition-web.txt
  Commit: Y | feat: 限流、账号锁定与审计日志

- [ ] 17. 积分与排行榜后端：双轨积分流水 + 自动结算 + 排行榜 API
  What to do / Must NOT do: models/point.py（PointTransaction: id, user_id, amount ±, kind(competition/activity/manual), ref_competition_id, reason, created_by）；services/points_service.py（比赛结束按 points_rule 自动结算到参赛单位成员；admin 手动发活动积分；查询用户流水）；api/points.py（GET /api/points/me、GET /api/points/leaderboard 按维度聚合、POST /api/admin/points 发放 admin-only）；api/rankings.py（GET /api/rankings/competition/{id} 场次排名、GET /api/rankings/global）。**队伍积分归属（Metis C6/E15 修正）：队伍获奖时每位成员各得该名次全额积分（不拆分），reason 注明「比赛名次·队伍<队名>」；全局榜按用户聚合**。Must NOT: 流水只能由系统操作产生（无直接改库 API）；结算不可重复执行（幂等）。
  Parallelization: Wave 8 | Blocked by: 16 | Blocks: 20,21
  References (executor has NO interview context - be exhaustive): plan.md §十一（双轨积分+流水）、§六（PointTransaction 字段）；Metis 审查 C6/E15（队伍积分按成员全额入账，本 todo 固化）
  Acceptance criteria (agent-executable): pytest tests/test_points.py + tests/test_rankings.py 全绿（比赛结算后流水生成且再结算不重复；**3 人队夺冠 → 3 名成员各 +100**；活动积分发放/回滚；场次排名与全局榜排序正确；player 调 admin 发放 403）
  QA scenarios: happy — 完赛自动给冠军队成员各 +100；failure — 重复触发结算流水不翻倍，证据 .omo/evidence/task-17-competition-web.txt
  Commit: Y | feat: 双轨积分、结算与排行榜 API

- [ ] 18. 对局玩法前端组件（triangle_occupy 面板）
  What to do / Must NOT do: frontend/src/plugins/triangle-occupy/ 组件（对局面板：棋盘渲染、实时状态订阅 /ws、**referee/admin 操作按钮（occupy/cancel/reoccupy/end，替双方操作棋盘）+ 选手/观众只读视图（无操作按钮，用户 2026-08-02 最终确认）**、倒计时）；对局页 /competitions/:id/matches/:mid 集成（referee/admin 视图+player 只读视图）；用 WS 连接管理器。Must NOT: 不重写 demo 玩法规则（只做视图层）；组件不做数据持久化；不做 iframe 过渡方案（Metis S2：直接组件化，避免双写）。
  Parallelization: Wave 7 | Blocked by: 12,13,15 | Blocks: 19
  References (executor has NO interview context - be exhaustive): demo/frontend/board.js、panel.js、ws.js、events.js、index.html、style.css（全部视图逻辑参照）；demo/api/routes.py:69-137（接口契约）；用户 2026-08-02 最终确认（仅 referee/admin 操作棋盘，选手只读）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 成功；对局页手动冒烟：npm run dev + 后端启动后访问 /competitions/:id/matches/:mid 渲染棋盘组件（可用 Playwright 截图存 .omo/evidence/task-18-competition-web.png 验证非空白）；referee/admin 登录显示操作按钮、选手登录无操作按钮
  QA scenarios: happy — referee 点击占领后棋盘更新且 WS 收到推送；failure — 无鉴权访问对局页跳登录、选手登录看不到操作按钮（即便手工调 API 也 403），证据 .omo/evidence/task-18-competition-web.txt
  Commit: Y | feat: 三角占领对局前端组件

- [ ] 19. 管理后台页面（选手/权限/比赛/积分/流量监控/玩法模板）
  What to do / Must NOT do: frontend/src/views/admin/ 各页面（users.vue 选手管理与角色分配、competitions.vue 比赛 CRUD 与配置表单（赛制/玩法/积分规则）、points.vue 活动积分发放、traffic.vue 流量监控（审计聚合表格+简单图表）、plugins.vue 玩法模板列表）；路由守卫仅 admin 可进；全部调 /api/admin/*。Must NOT: 不实现后台的玩法编辑（只展示模板列表）；不做审计详情页的过度可视化（表格足够）。
  Parallelization: Wave 9 | Blocked by: 3,15,18 | Blocks: 22
  References (executor has NO interview context - be exhaustive): plan.md §十二（管理后台页面清单）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 成功；admin 登录后各页面路由可访问（Playwright 冒烟截图存 .omo/evidence/task-19-competition-web.png）；player 访问 /admin 被守卫重定向
  QA scenarios: happy — admin 在后台创建比赛并发放积分成功；failure — player 登录访问 /admin 跳转 /login 或 403 提示，证据 .omo/evidence/task-19-competition-web.txt
  Commit: Y | feat: 管理后台前端

- [ ] 20. 首页与比赛展示页（宣传插画/赛制安排/报名入口/场次排名）
  What to do / Must NOT do: frontend/src/views/Home.vue（宣传插画轮播位 placeholder 图片、当前/即将比赛卡片、报名入口按钮）、CompetitionDetail.vue（赛制说明、报名按钮（个人/队伍选择）、参赛名单、赛程/签表可视化、场次排名表）；个人中心 Profile.vue（资料/我的队伍/我的报名/积分流水）。Must NOT: 不接真实插画素材（用占位图，后台可换）；不做轮播动画框架依赖（手写轻量轮播或 Element Carousel）。
  Parallelization: Wave 9 | Blocked by: 3,8,17 | Blocks: 22
  References (executor has NO interview context - be exhaustive): plan.md §十二（页面清单）、§一（需求 1 展示要求）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 成功；首页/比赛详情/个人中心路由可达（Playwright 截图 .omo/evidence/task-20-competition-web.png）；详情页报名按钮按登录态显示
  QA scenarios: happy — 未登录点报名跳登录；已登录个人报名成功跳转个人中心显示记录；failure — 报名已满（≥50 参赛单位）显示提示不可再报，证据 .omo/evidence/task-20-competition-web.txt
  Commit: Y | feat: 首页、比赛详情与个人中心

- [ ] 21. 排行榜页与积分流水展示
  What to do / Must NOT do: frontend/src/views/Rankings.vue（全局榜：用户维度，比赛积分/活动积分/合计筛选 tab；场次榜入口）；积分流水展示组件（时间/类型/金额/原因）。Must NOT: 不做实时排行榜（页面刷新拉取即可）。
  Parallelization: Wave 9 | Blocked by: 16,17,18 | Blocks: 22
  References (executor has NO interview context - be exhaustive): plan.md §十一、§十二（排行榜页）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 成功；排行榜页渲染数据（Playwright 截图 .omo/evidence/task-21-competition-web.png）
  QA scenarios: happy — 完赛后全局榜顺序正确；failure — 空数据时显示空态而非报错，证据 .omo/evidence/task-21-competition-web.txt
  Commit: Y | feat: 排行榜与积分流水页

- [ ] 22. 登录/注册/对局页路由与导航整合
  What to do / Must NOT do: 完成登录注册页（Login.vue/Register.vue 与 /api/auth 对接、cookie 会话）；Router 全局守卫（未登录→登录页、referee/admin 路由区分）；导航栏（首页/比赛/排行榜/后台/个人中心）；axios 拦截器统一处理 401/403/429 提示。Must NOT: 不把 token 存 localStorage（保持 cookie）；不做忘记密码。
  Parallelization: Wave 9 | Blocked by: 3,19,20,21 | Blocks: 23
  References (executor has NO interview context - be exhaustive): plan.md §十二（登录/注册）、§十三（/auth）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 成功；未登录访问受保护路由被守卫重定向 /login；登录后回跳原页面（Playwright 冒烟）
  QA scenarios: happy — 注册→自动登录→访问个人中心 200；failure — 429 限流时 axios 拦截器弹出友好提示，证据 .omo/evidence/task-22-competition-web.txt
  Commit: Y | feat: 前端路由守卫与会话整合

- [ ] 23. 管理后台完善：权限分配界面 + 流量监控可视化
  What to do / Must NOT do: admin/users.vue 增强（角色下拉分配、封禁/解封、重置密码按钮）；admin/traffic.vue 增强（登录失败趋势简单图表（可选 ECharts）、锁定列表、高频 IP 表格、按时间过滤）。Must NOT: 权限分配不允许 admin 给自己降级到 player（防锁死）。
  Parallelization: Wave 9 | Blocked by: 3,19,22 | Blocks: 24
  References (executor has NO interview context - be exhaustive): plan.md §十二（管理后台）、§十（流量监控内容）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 成功；admin 给用户改角色后该用户权限即时生效（Playwright 冒烟 + 后端 pytest 已覆盖权限逻辑）；流量页展示测试产生的审计数据
  QA scenarios: happy — 改角色后重新登录权限变化；failure — 最后一个 admin 尝试把自己降级被后端 400 拒绝，证据 .omo/evidence/task-23-competition-web.txt
  Commit: Y | feat: 权限分配与流量监控页面

- [ ] 24. 种子数据与开发环境脚本
  What to do / Must NOT do: backend/seed.py（幂等种子：admin 账号 admin/admin123（仅开发）、referee 账号、8 个 player 账号、2 支队伍、1 场演示比赛（分组循环+三角占领+积分规则））；backend/run_dev.py 或 scripts/dev.md 说明（后端启动 + 前端启动顺序）。Must NOT: 种子脚本不覆盖已有数据（检测到 admin 存在即跳过）；admin 默认密码仅限开发环境（README 醒目警示）。
  Parallelization: Wave 10 | Blocked by: 全部 1-23 | Blocks: 25
  References (executor has NO interview context - be exhaustive): plan.md §十五 15.2 M10（联调验收前置）
  Acceptance criteria (agent-executable): `cd backend && python seed.py && pytest tests/test_seed.py -q` 全绿（幂等：跑两遍数据不翻倍；admin 存在）
  QA scenarios: happy — 空库跑 seed 后 8+ 账号与演示比赛就绪；failure — 已初始化库再跑 seed 不产生重复，证据 .omo/evidence/task-24-competition-web.txt
  Commit: Y | feat: 种子数据与开发脚本

- [ ] 25. 本地全链路联调验收（M10 验收清单）
  What to do / Must NOT do: 启动前后端，按 plan.md §十五 15.3 验收清单逐项走通：注册×6→组 2 支 3 人队→admin 建比赛（混合参赛、分组循环+三角占领）→个人+队伍报名→referee 开对局→**referee/admin 在玩法页替双方操作棋盘（occupy/cancel/end），选手登录只读（用户 2026-08-02 最终确认）**→收局→引擎推进→赛制结束→自动积分→排行榜正确→活动积分发放→流水可查→**连错密码 5 次锁定（Metis C2 修正：统一 5 次，非 6 次）**+流量页可见→admin 解封→再建瑞士轮与单败淘汰各一场验证→**瑞士轮奇数参赛单位轮空、单败淘汰平局裁判指定胜者（Metis E1/E2 演练）**→备份脚本跑通；产出验收记录 .omo/evidence/task-25-competition-web.md（每项 ✓/✗）。Must NOT: 不跳过任何验收项；验收发现问题回修对应 todo 后再验。
  Parallelization: Wave 10 | Blocked by: 全部 1-24 | Blocks: 26
  References (executor has NO interview context - be exhaustive): plan.md §十五 15.3（验收清单逐项）；Metis 审查 C2（锁定阈值统一 5 次）与 E1/E2（平局/轮空演练）；用户 2026-08-02 最终确认（仅 referee/admin 操作棋盘）
  Acceptance criteria (agent-executable): 验收记录文件全部 ✓ 且 pytest 全量 `cd backend && pytest -q` 通过（0 failed）；前端 npm run build 成功
  QA scenarios: happy — 完整 6 人演练链全 ✓；failure — 任一验收项 ✗ 则记录原因并回修，证据 .omo/evidence/task-25-competition-web.md
  Commit: Y | feat: 全链路联调验收通过

- [ ] 26. 部署上线：国内轻量服务器单机部署（Docker Compose 或 systemd）+ Caddy + 备份 + 文档
  What to do / Must NOT do: deploy/Dockerfile（多阶段：node 构建前端 → python 运行 uvicorn 托管静态）；deploy/docker-compose.yml（单服务 + SQLite 卷挂载 + 环境变量 SECRET_KEY 等）；deploy/Caddyfile（HTTPS 反代配置模板）；deploy/backup.sh（sqlite3 .backup + 保留最近 7 份）；**backup_restore_test.sh（Metis E18 修正：恢复演练——从备份文件恢复到临时目录并用 sqlite3 校验表行数，备份必须可恢复才合格）**；docs/部署手册.md（**目标环境：国内轻量服务器（腾讯云/阿里云香港 2C2G 优先，免备案），观众主要在国内，不使用 Cloudflare Pages——2026-08-02 决策**；A=Docker Compose / B=systemd 裸跑两方案；Caddy 自动 HTTPS；如需域名则提醒国内服务器 ICP 备案、香港节点免备案；密钥管理）；docs/玩法模板开发规范.md（§八规范文档化）。Must NOT: 不在本任务实际部署到公网服务器（服务器由用户按部署手册购置）；不提交真实密钥到 git；不写 Cloudflare Pages 部署步骤（已决策不用）。
  Parallelization: Wave 11 | Blocked by: 25 | Blocks: —
  References (executor has NO interview context - be exhaustive): plan.md §十四（14.3 A/B 方案、14.4 上线清单）、§八 8.3（模板规范文档化）；Metis 审查 E18（备份无恢复演练，本 todo 固化恢复测试）；2026-08-02 用户决策：观众主要在国内 → 国内轻量服务器单机部署，弃用 Cloudflare Pages（Pages 无常驻进程/Python 生态受限/WebSocket 需付费 Durable Objects/SQLite 文件不可用，详见会话记录）
  Acceptance criteria (agent-executable): 本机无 Docker 则验证文件齐全 + `docker compose config` 语法可解析（若用户装 Docker 后执行 `docker compose up -d --build` 冒烟）；**backup.sh 在本机对测试 db 执行一次生成备份文件，backup_restore_test.sh 从备份恢复并校验行数一致**；部署手册含步骤序号与国内服务器购置指引（腾讯云/阿里云香港轻量 2C2G）
  QA scenarios: happy — backup.sh 执行后备份文件存在且含数据，恢复演练通过；failure — 服务器无 Docker 时文档给出 B 方案完整步骤（不依赖 Docker 命令）、恢复演练失败则脚本非零退出，证据 .omo/evidence/task-26-competition-web.txt
  Commit: Y | docs: 部署方案、备份恢复脚本与玩法模板开发规范

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit
- [ ] F2. Code quality review
- [ ] F3. Real manual QA
- [ ] F4. Scope fidelity

## Commit strategy
- Conventional Commits：`feat:` 功能、`fix:` 修复、`test:` 测试、`docs:` 文档、`chore:` 杂项；scope 用模块名（auth、teams、tournaments、plugins、admin、frontend、deploy）
- 分支模型：`main`（稳定可部署）+ `dev`（集成）+ `feature/<milestone>-<desc>`（开发）；每个 todo 独立 feature 分支 → merge dev → 里程碑验收后 merge main
- 每个 todo 完成后必须：pytest 全绿 + commit；每完成一个里程碑打 tag `v0.x`（M0→v0.0、M4→v0.1、M6→v0.2、M8→v0.3、M10→v0.4、M11→v1.0）
- 禁止把 `.env`、`*.db`、`node_modules/`、`.venv/` 提交进 git（.gitignore 已含）
- 单个 commit 只做一件事；不要混合无关改动

## Success criteria
- 本地 `cd backend && pytest -q` 全部通过（含赛制引擎、插件、认证、限流、CSRF、积分全量测试，0 failed）
- `cd frontend && npm run build` 构建成功，`npm run dev` 可联调后端
- 全链路验收 100% ✓（todo 25 验收记录 .omo/evidence/task-25-competition-web.md）：6 人注册→2 支 3 人队→建比赛（分组循环+三角占领）→混合报名→对局进行中（referee/admin 操作棋盘，选手只读）→收局→引擎推进→自动积分→排行榜→活动积分→流水→锁定（5 次）+流量监控→解封→瑞士轮/单败各验一场（含平局/轮空演练）
- 三种赛制引擎均有独立 pytest 覆盖（编排、推进、排名、平局、轮空、同分决胜边界）
- triangle_occupy 插件可作为模板在比赛中配置并完整跑通一局（demo 规则逻辑零改动）
- 管理后台四块齐备：选手管理、权限分配（三角色+比赛裁判组）、活动积分、异常流量监控
- 部署产物齐全：Dockerfile + docker-compose.yml + Caddyfile + backup.sh + backup_restore_test.sh + 部署手册（A/B 两方案）+ 玩法模板开发规范
- 全部代码在 git 仓库中，main 分支可部署，里程碑 tag 存在

## Execution ledger

- 2026-08-03 todo 8: {"event":"task-completed-claim","plan":".omo/plans/competition-web.md","task":8,"session_id":"codex:competition-web-start-work","commands":["pytest","uvicorn","curl"],"artifact":".omo/evidence/task-8-competition-web.txt","adversarial_classes":{"misleading_success_output":"pytest/curl real output","flaky_tests":"pytest twice","hung_or_long_commands":"uvicorn killed"},"cleanup":["uvicorn killed","smoke db deleted"]}
- 2026-08-03 todo 9: {"event":"task-completed-claim","plan":".omo/plans/competition-web.md","task":9,"session_id":"codex:competition-web-start-work","commands":["pytest"],"artifact":".omo/evidence/task-9-competition-web.txt","adversarial_classes":{"misleading_success_output":"pytest real output","flaky_tests":"pytest twice"},"cleanup":[]}
