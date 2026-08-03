# PROJECT KNOWLEDGE BASE

**Updated:** 2026-08-03
**Branch:** main
**State:** fixed 计划 15/15 完成（对局链路修复 + 权限加固 + 业务调整 + 前端体验 + 部署补全）

## OVERVIEW
音游比赛运营平台（萌新杯）：FastAPI + Vue3 + SQLite 单进程单体，单端口跑通全站（后端托管前端产物）。玩法模板插件化，内置 demo「三角占领」。权限模型：对局中仅 referee/admin 可操作棋盘，选手只读；裁判需被指派到比赛 referee_ids 才可操作（per-competition 校验）。

## STRUCTURE
```
competition_web/
├── start.ps1 / 启动服务.bat   # 一键启动（自动装环境 + 双服务 + 自动开浏览器）
├── backend/                   # FastAPI 后端
│   ├── app/main.py            # 入口：lifespan（建表/迁移/插件注册）+ 中间件栈 + 路由挂载 + 静态托管
│   ├── app/{api,core,models,schemas,services,tournaments,plugins}/
│   ├── tests/                 # pytest 290 个，conftest 三层隔离
│   ├── seed.py                # 幂等种子数据（admin/admin123 等）
│   └── reset_db.py            # 可复用数据库重置脚本（完全重置 + 确认 + 锁检测）
├── frontend/                  # Vue3 前端（无单元测试，靠 vue-tsc + build）
│   └── src/{views(含admin),plugins/triangle-occupy,stores,api,router,components}/
├── deploy/                    # 部署产物（Dockerfile/compose/Caddyfile/backup）
└── docs/                      # 文档（部署手册/玩法规范/archive 演进记录）
```

## WHERE TO LOOK
| 任务 | 位置 |
|------|------|
| 路由/端点（权限/审计模式） | backend/app/api/（见其 AGENTS.md） |
| 安全/限流/审计/WS 连接 | backend/app/core/ |
| 业务编排（排表/开赛/记分/积分） | backend/app/services/ |
| 三赛制引擎（纯逻辑） | backend/app/tournaments/ |
| 玩法插件系统 + 三角占领控制器 | backend/app/plugins/ |
| ORM 模型 | backend/app/models/（简单定义，父级覆盖） |
| Pydantic schema | backend/app/schemas/（同上） |
| 测试基建 / 直插模式 | backend/tests/ |
| 前端页面 / admin 子域 | frontend/src/views/ |
| 前端全局（代理/守卫/插件组件） | frontend/ |
| 赛程图可视化组件 | frontend/src/components/ScheduleChart.vue |
| 部署产物 | deploy/（Dockerfile/compose/Caddyfile/backup.sh/backup_restore_test.sh） |
| 部署手册/玩法规范 | docs/（部署手册.md/玩法模板开发规范.md） |

## CODE MAP
| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| app | FastAPI | main.py | — | 入口；lifespan 建表+迁移+插件注册；app.frontend() 托管 SPA |
| get_current_user / require_admin / require_referee | Dep | core/rbac.py | 9+ | JWT cookie→DB 用户；role 以 DB 为准（不信任 JWT 声明） |
| _require_competition_referee | fn | plugins/routes.py | 3 | per-competition referee_ids 校验（create_session/submit_action/end_session） |
| limiter | obj | core/ratelimit.py | 全局 | slowapi 默认 100/min；auth 10/min；admin 60/min |
| manager | obj | core/ws_manager.py | 3 | match_id 订阅广播；队列 put_nowait 跨线程 |
| TournamentEngine | ABC | tournaments/base.py | 1 | 引擎统一接口（schedule/record_result/standings） |
| RoundRobin/Swiss/SingleElimEngine | cls | tournaments/*.py | 18/13/15 | 三种赛制，纯逻辑无 DB/IO |
| match_service | mod | services/match_service.py | 4 | 排表/开赛/记分；重建+回放引擎；start_match 回写解析参赛者 |
| points_service | mod | services/points_service.py | 3 | 积分幂等结算（保留函数，不再自动调用）/排行榜 |
| registry / GameplayPlugin | obj/cls | plugins/registry.py, base.py | 多 | 插件发现注册；契约强制校验 |
| reset_db | fn | reset_db.py | — | 完全重置数据库（drop+删文件+create+seed，锁检测前置） |
| http(axios) / useAuthStore | mod/store | frontend/src/api, stores | 多 | baseURL /api；401/403/429 拦截 |
| PLUGIN_COMPONENTS | map | MatchPlay.vue | 1 | 玩法名→组件映射表（插件化渲染） |
| ScheduleChart | comp | components/ScheduleChart.vue | 1 | 赛程图（单败淘汰 bracket / 循环瑞士轮次对阵表） |

依赖流向（后端）：`api/* → core/* + models + schemas → services/* → tournaments/* + plugins/registry → core/ws_manager`。
前端：`views/* → api/http → Vite proxy(:8000)`；MatchPlay → `new WebSocket(/ws/...)`。

## CONVENTIONS
- **编号引用体系**：注释标注 `todo N`（功能归属）与 `Metis C/E/V{n}`（需求/验收约束），改动时保持引用可追溯。
- 后端 docstring/注释以中文为主；HTTP error `detail` 统一中文。
- requirements.txt 未锁版本；**无 alembic** —— schema 演进用 main.py `_ensure_schema_upgrades()` 幂等补列（PRAGMA 检测 + ALTER）。
- 前端 tsconfig 严格 lint（noUnusedLocals/noUnusedParameters 等）；vite 代理 /api 与 /ws → :8000。
- 插件契约：继承 GameplayPlugin、manifest 非空 name/version、暴露 `plugin` 实例、不持全局状态。
- 参赛单位模型：个体 = 1 人队伍；participant id 升序保证引擎重建确定性。
- 前端插件化：MatchPlay.vue 按 `match.gameplay_plugin` 名经 PLUGIN_COMPONENTS 映射表动态解析组件（非动态 import）。

## ANTI-PATTERNS (THIS PROJECT)
- **Metis E13**：ws_manager 只做连接登记与推送，禁止在其中做任何鉴权。
- **Metis E7**：插件 create_session 只做值域校验，禁止校验「得分真实性」。
- 前端禁止 `as any` / `@ts-ignore`——类型错误必须真修（`catch (e: any)` 共享模式除外）。
- `plugins/routes.py` 内存 `_sessions` 仅作进程内缓存加速；DB 桥已实现（_load_db_session 回退装载 + _persist_session 回写）。
- `points_service` 复用 `match_service` 的私有 `_` 助手（`_approved_participant_ids` 等），重构勿破坏其签名。
- **GameplayPlugin 契约**：方法不得修改传入的 state（base.py:10）；最终状态同步在路由层通过构造 final_state 副本完成（见 routes.py end_session）。

## UNIQUE STYLES
- **引擎确定性恢复**：开赛/记分按「已批准报名 + 已完结对局」重建引擎并回放结果（单败淘汰后续轮次靠它解析参赛者）；start_match 回写解析出的参赛者到 Match 行。
- 报名状态机：`pending → approved/rejected`（admin 审批端点）；赛程只认 approved。
- WS 广播：同步线程 put_nowait 入队 → 事件循环发送任务出队；满队列断开慢消费者。end_session 广播附最终状态（捕获活控制器注入 final_state，保证 game_over=true）。
- 积分：**已移除 finished 自动结算**（settle_competition_points 保留函数但不再自动调用）；全部积分由 admin 手动发放；排行榜单一 total。
- 比赛状态机：`draft → registration → ongoing → finished`（cancelled 特殊）；进 ongoing 自动排表；finished 可删除（级联清 Match/GameSession/PointTransaction）。
- 权限：admin 可增删账号（硬删 + 级联清理 + 保护规则）；玩法三端点（create_session/submit_action/end_session）强制 per-competition referee_ids 校验。
- 一键启动：start.ps1（建 venv/装依赖/seed/双窗口/开浏览器）；reset_db.py 一键重置（--yes 跳确认）。

## COMMANDS
```bash
# 一键启动（Windows 双击 启动服务.bat）
powershell -ExecutionPolicy Bypass -File start.ps1

# 后端测试（290 个）
cd backend && .venv\Scripts\python -m pytest tests -q

# 前端校验（vue-tsc + build，无单测）
cd frontend && npm run build

# 后端单独启动
cd backend && .venv\Scripts\python seed.py && .venv\Scripts\python -m uvicorn app.main:app --port 8000

# 数据库重置（完全重置，无备份）
cd backend && .venv\Scripts\python reset_db.py --yes
```

## NOTES
- 数据库：`backend/competition.db`（SQLite WAL；备份连同 -wal/-shm 一起拷）；可用 DATABASE_URL 环境变量覆盖。
- 默认账号（开发）：admin/admin123、referee/referee123、player1-8/player123；**部署上线前必须改**。
- 静态托管：main.py 经 `app.frontend("/", fallback="index.html")` 托管 `frontend/dist`（SPA 深链回退）；目录不存在则不挂载。
- 部署产物齐全：deploy/（Dockerfile + docker-compose.yml + Caddyfile + backup.sh + backup_restore_test.sh）+ docs/部署手册.md（A=Docker / B=systemd 两方案）+ docs/玩法模板开发规范.md。
- 里程碑 tag v0.0-v0.4 对应 M0-M10；v0.5 对应 fixed 修复里程碑；M11 部署产物已就绪（待实际部署到服务器）。
- 项目演进记录见 `docs/archive/项目演进记录.md`（合并自原始方案 + 3 个执行计划）。
