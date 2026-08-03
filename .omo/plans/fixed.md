# fixed - Work Plan

## TL;DR (For humans)

**What you'll get:** 一个彻底修好且补全的比赛运营平台。核心是让"三角占领对局玩法"真正跑通——裁判/admin 能在对局页正常替双方操作棋盘（占领/取消/结束），完整走通"开赛→操作→记录结果"链路；同时补齐安全权限（堵住裁判越权、admin 增删账号）、业务调整（删除已结束比赛、积分改纯手动）、前端体验（首页纯宣传+独立比赛列表页、赛程图可视化、路由竞态修复、清理 as any）、以及部署上线全套产物（Docker/备份/手册）。修完后平台可一键重置数据、单端口托管、随时部署到服务器。

**Why this approach:** "对局跑不通"是一串连环 bug（前端把嵌套响应当扁平用 + 参赛者 id 硬编码 + WS 状态嵌套 + 会话结束丢状态 + 后端不回写参赛者），必须一起修链路才通；权限/积分/删除/部署是用户已确认的方向，整合到一个计划一次到位，避免多轮返工。

**What it will NOT do:** 不做新玩法插件；不改 demo 游戏规则核心逻辑；不改变插件契约方法签名与 get_state 返回形状（前端负责解包）；不引入动态 import 做插件化；不做积分历史数据迁移；不做账号软删除/回收站；不重构赛制引擎算法；不做 CI/CD；不做前端单元测试框架。

**Effort:** XL
**Risk:** Medium - 核心是前端数据解包连环 bug（根因已定位，改动集中 MatchPlay.vue）+ 赛程图可视化（新增组件）+ 部署产物（无服务器实测，本机验证文件齐全+语法）；回归由 252 个 pytest + 前端 build 兜底
**Decisions to sanity-check:** ① 积分=完全移除自动结算，全部 admin 手动发放（用户确认 ①A）；② 账号删除=硬删除+级联清理（用户确认 ②A）；③ 赛程图=单败淘汰 bracket 签表 + 循环/瑞士轮次对阵表（用户确认 ③B）；④ 裁判=保留全局角色但所有端点强制 per-competition referee_ids 校验（用户确认 ④A）；⑤ 重置脚本=完全重置无备份。

Your next move: 高精度评审（momus + Oracle）已自动运行，评审通过后运行 `$start-work fixed` 开始执行。完整执行细节见下文。

---

> TL;DR (machine): XL effort, Medium risk - 15 implementation todos + 4 verification tasks；对局链路连环 bug 修复（前端解包+participant_id+WS state+会话结束+后端回写+广播）+ 前端插件化 + 权限加固（裁判越权+admin 增删）+ 业务调整（删除 finished 比赛+积分手动化）+ 前端体验（首页改版+赛程图+竞态+as any）+ 部署补全（Docker/备份/手册）+ 全量回归。

## Scope
### Must have
- backend/reset_db.py：可复用数据库重置脚本（完全重置、无备份、CLI 带确认/--yes 跳过）
- 对局操作链路修复（核心连环 bug）：前端 loadMatch 解包嵌套响应、WS state 解包 controller_state、participant_id 按替操作方推导、session_ended 保留状态；后端 end_session 广播附最终状态
- 后端字段补齐：start_match 回写解析出的参赛者到 Match 行 + MatchOut/MatchDetailOut 补 gameplay_plugin 字段
- 前端 MatchPlay.vue 插件化：按 gameplay_plugin 名动态解析玩法组件（映射表）
- 静态托管目录对齐：main.py frontend-dist → frontend/dist
- 内存 _sessions 注释收敛 + admin 玩法插件列表接口 GET /api/admin/plugins
- 权限模型补全：admin 增 POST 创建账号 + DELETE 硬删除账号（级联清理）+ 玩法路由 submit_action/end_session 补 per-competition referee_ids 校验（堵越权）
- 允许删除 finished 比赛 + 级联清理 Match/GameSession/PointTransaction
- 积分合并：移除 finished 自动结算 + 单一积分 admin 手动发放 + 排行榜合并为单一 total
- 首页改版：移除比赛卡片纯宣传 + 比赛列表迁移到 Competitions.vue
- 比赛详情竞态修复：补 watch(route.params.cid) + loading 初值 true
- 赛程图可视化：单败淘汰 bracket 签表 + 循环/瑞士轮次对阵表
- 清理 4 处 as any（Home/CompetitionDetail/admin Competitions/Traffic）
- 部署补全：Dockerfile + docker-compose.yml + Caddyfile + backup.sh + backup_restore_test.sh + 部署手册 + 玩法模板开发规范
- 每项补回归测试 + 全量回归验证

### Must NOT have (guardrails, anti-slop, scope boundaries)
- 不做新玩法插件（只修现有 triangle_occupy 链路）
- 不改 demo GameController 规则逻辑（AGENTS.md：规则零改动）
- 不改变 GameplayPlugin 契约方法签名与 get_state 返回形状（嵌套 controller_state 保持不变，前端解包）
- 不引入 defineAsyncComponent/动态 import() 做前端插件化（当前单玩法，映射表足够）
- 不做积分历史数据迁移（保留 kind 列，新流水统一 kind="manual"）
- 不做账号删除的软删除/回收站（用户确认硬删除）
- 不重构赛制引擎算法本身（只加赛程图可视化）
- 不做 CI/CD、不改 .github workflows
- 不做前端单元测试框架（沿用 npm run build 验证）
- 不做多语言/国际化（赛程图 UI 中文）
- 重置脚本不做备份功能（用户明确"完全重置,无需备份"）；不加 --backup 选项
- 不在本计划实际部署到公网服务器（服务器由用户按部署手册购置）
- 不提交真实密钥到 git

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: tests-after（先修 bug/加功能，再补回归测试）+ pytest（后端）+ npm run build（前端 vue-tsc + vite build）
- Evidence: .omo/evidence/task-<N>-fixed.<ext>（本项目统一 .omo/evidence/，不使用 ulw-loop）
- 每个 todo 的 Acceptance criteria 必须能通过命令行断言验证（pytest 指定文件、curl 指定端点+期望码、前端 build 退出码、grep 断言）
- QA 场景一律给出精确工具调用（pytest 指定文件、curl 指定端点、node 脚本断言），happy + failure 双路径，产出证据文件
- 核心 bug（todo 2）必须走前端 UI 路径冒烟（非仅 curl），因为 bug 本就是前端数据解包问题

## Execution strategy
### Parallel execution waves
> Wave 1（阻塞性 bug + 独立后端/前端项，可并行）：1,2,3,4,5
> Wave 2（前端插件化，依赖 3 的 gameplay_plugin 字段）：6
> Wave 3（安全/权限/业务，可并行）：7,8,9
> Wave 4（前端体验，可并行）：10,11,12,13
> Wave 5（部署补全）：14
> Wave 6（全量回归）：15

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | — | 15 | 2,3,4,5 |
| 2 | — | 6,15 | 1,3,4,5 |
| 3 | — | 6,15 | 1,2,4,5 |
| 4 | — | 15 | 1,2,3,5 |
| 5 | — | 15 | 1,2,3,4 |
| 6 | 2,3 | 15 | 7,8,9,10,11,12,13 |
| 7 | — | 15 | 6,8,9,10,11,12,13,14 |
| 8 | — | 15 | 6,7,9,10,11,12,13,14 |
| 9 | — | 15 | 6,7,8,10,11,12,13,14 |
| 10 | — | 15 | 6,7,8,9,11,12,13,14 |
| 11 | — | 15 | 6,7,8,9,10,12,13,14 |
| 12 | — | 15 | 6,7,8,9,10,11,13,14 |
| 13 | — | 15 | 6,7,8,9,10,11,12,14 |
| 14 | — | 15 | 6,7,8,9,10,11,12,13 |
| 15 | 1-14 | — | — |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. backend/reset_db.py：可复用数据库重置脚本（完全重置、无备份、CLI 带确认）
  What to do / Must NOT do: 新建 backend/reset_db.py，实现可调用函数 `reset_db(confirm: bool = True) -> dict` 与 CLI 入口。**关键：文件顶部必须 import 全部 ORM 模型（参照 main.py:14-20，import app.models.audit_log/competition/match/point/registration/team/user），否则 Base.metadata.drop_all 只 drop seed.py 已 import 的 5 个表（User/Competition/Registration/Team/TeamMember），遗漏 Match/GameSession/PointTransaction/AuditLog，导致"完全重置"静默失效**。流程（**顺序敏感，锁检测必须前置**）：①打印开发密码警告（复用 seed.py 的 _DEV_PASSWORD_WARNING 文案）+ 提示"将删除 backend/competition.db 并重建种子数据"；②`confirm=True` 时 `input()` 等待回车确认（EOFError/非交互环境自动视为确认），`--yes` 参数跳过确认；③`engine.dispose()` 先关闭本进程全部连接；④解析 `settings.DB_PATH`（config.py，相对 backend/ 工作目录）为绝对路径，**先尝试删除** `competition.db` 及 `-wal`/`-shm` 伴生文件：**用 try/except PermissionError 包裹 Path.unlink（缺失用 missing_ok=True 忽略），捕获到 PermissionError 时打印"数据库被占用，请先停止后端服务（uvicorn）后重试"并 sys.exit(1)**——WAL 模式下 PRAGMA quick_check 检测不到其他进程占用，真正的检测点是删除时的文件锁；**锁检测必须在任何 drop_all 之前**，否则其他进程持有 BEGIN EXCLUSIVE 时 drop_all 会先抛 sqlite3.OperationalError（busy timeout 5s）而非友好提示，且 drop_all 成功而 unlink 失败会留下半空库污染其他连接；⑤删除成功后 `Base.metadata.create_all(bind=engine)` 重建全部表（删文件已清空所有数据，drop_all 冗余故省略）；⑥调 `seed_all()`（seed.py）灌入种子数据；⑦打印创建摘要（复用 seed_all 返回的 summary）。CLI 用法：`cd backend && .venv\Scripts\python reset_db.py`（确认后执行）、`.venv\Scripts\python reset_db.py --yes`（跳过确认）。Must NOT: 不调用 seed.py 的 `main()`（它只 create_all+seed_all，不含删文件）；不删除 competition.db 及伴生文件以外的任何文件；不添加备份逻辑；不改动 config.py/db.py/seed.py 现有代码；**不在 unlink 之前调 drop_all**（顺序错误会导致失败路径走不到友好提示）。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): backend/seed.py:51-59（_DEV_PASSWORD_WARNING 文案）、:80-227（seed_all 幂等实现与摘要格式，返回 {"skipped": bool, ...}）、:233-238（main()=create_all+seed_all，作为对比参考，勿调用）；backend/app/config.py（DATABASE_URL/DB_PATH 默认值，相对路径语义）；backend/app/db.py:10-23（engine/SessionLocal/Base，WAL PRAGMA）；backend/tests/conftest.py:22-28（drop_all+create_all 重置标准做法）；backend/seed.py:46-49（_DEFAULT_SONG_LIB_CANDIDATES：曲库路径来自 repo 外 demo/ 或 backend/demo/，reset 后 seed 依赖它存在）
  Acceptance criteria (agent-executable): `cd backend && $env:DATABASE_URL="sqlite:///./_reset_test.db"; $env:DB_PATH="./_reset_test.db"; .venv\Scripts\python -c "import reset_db; r = reset_db.reset_db(confirm=False); assert r['skipped'] is False"` 返回成功且 `_reset_test.db` 存在；再次运行同命令 `assert r['skipped'] is True`（幂等：seed_all 检测 admin 已存在跳过）；`Test-Path backend/_reset_test.db-wal` / `-shm` 为 False（伴生文件已删）；**完全重置验证**：先在测试库插入一条 Match 行再 reset，断言 reset 后 `db.query(Match).count()==0` 且 `db.query(GameSession).count()==0` 且 `db.query(PointTransaction).count()==0`（证明全部模型表都被清，而非只清 5 张 seed 表）；删除 `_reset_test.db*` 清理。
  QA scenarios (name the exact tool + invocation): happy — `cd backend && .venv\Scripts\python reset_db.py --yes` 在真实 competition.db 上执行，随后 `.\.venv\Scripts\python -c "from app.db import SessionLocal; from app.models.user import User; db=SessionLocal(); print(db.query(User).filter(User.username=='admin').count())"` 输出 1，证据 .omo/evidence/task-1-fixed.txt；failure — 用另一进程保持对 competition.db 的连接不关闭（`.venv\Scripts\python -c "import sqlite3,time; c=sqlite3.connect('competition.db'); c.execute('BEGIN EXCLUSIVE'); time.sleep(30)"` 后台运行）后运行 reset_db.py，脚本打印"数据库被占用"提示且 exit 非 0，证据同上。Commit: Y | chore(db): 新增可复用数据库重置脚本 reset_db.py

- [x] 2. 修复对局操作核心链路（连环 bug）：前端数据解包 + participant_id 推导 + WS 状态解包 + 会话结束保留状态 + 后端广播附 state
  What to do / Must NOT do: 前端 frontend/src/views/MatchPlay.vue 五处修改：①**loadMatch 解包**（当前 :174-181 `match.value = data` 把整个嵌套 `MatchDetailOut={match, session}` 当扁平 MatchInfo 用，导致 participant_a/status/id 全 undefined）：定义 `interface MatchDetailResp { match: MatchInfo; session: { id: number; state: Record<string, unknown> | null } | null }` 并 `const { data } = await http.get<MatchDetailResp>(...); match.value = data.match`，同时若 `data.session` 存在则初始化 `sessionId.value = data.session.id`。②**WS state 解包**（当前 :145-164 onmessage `state.value = frame.state as TriangleState`）：WS 帧 `state` 是 get_state 的嵌套视图 `{controller_state: {board, scores, ...}, elapsed_minutes, sides, game_over, winner}`（见 plugin.py:185-196），而 TriangleState 期望扁平字段；解包为 `const raw = frame.state; state.value = (raw.controller_state ? { ...raw.controller_state, ...raw } : raw) as TriangleState`（controller_state 字段优先，外层 elapsed_minutes 等覆盖；JSON.parse 返回 any 故 spread 后 as TriangleState 类型安全）。③**participant_id 推导**（当前 :187-207 submitAction 硬编码 `participant_id: 0`）：删除硬编码，新增 `const actingSide = ref<'defender' | 'attacker'>('defender')` 与 UI 切换（el-radio-group，放在 TriangleControls 旁，label"替哪一方操作"），发送时 `const pid = actingSide.value === 'defender' ? match.value?.participant_a : match.value?.participant_b`；**pid 为 null/undefined 时 ElMessage.warning("该侧参赛者未确定，请先开赛") 并 return**（不传 0 兜底，避免无意义请求；即便漏传后端 validate_result 也会以 400 拒绝 0）。④**session_ended 保留状态**（当前 :156-160 清空 state.value）：不再清空——若帧带 `state` 用之（含 game_over=true），否则保留旧 state 值只清 sessionId 与置 noSession=false（保证"记录结果"按钮 v-if="isRefereeOrAdmin && state.game_over" 可见，棋盘仍显示最终状态）。⑤**WS 重连终止守卫**（当前 :166-171 onclose 无限 3s 重连）：新增 `let unmounted = false`（onBeforeUnmount 置 true 并清 ws），onclose 重连前检查 `if (unmounted) return`；**close.code === 1008 时（对局/比赛被删除等权限/资源不存在）停止重连**并 ElMessage.info("对局已关闭")，避免 todo 8 删除 finished 比赛后残留订阅者无限重连。后端 backend/app/plugins/routes.py：⑥**end_session（:199-225）广播 session_ended 附带正确的最终状态——关键：必须在 plugin.end_session 之前捕获活控制器，否则 end_session 内 _drop_controller 后 get_state 从陈旧 controller_state 重建返回 game_over=false**。实现：在 `result = plugin.end_session(...)` 之前先 `controller = plugin._get_controller(session["state"])`（同一活实例），end_session 返回后构造 `final_state = dict(session["state"]); final_state["controller_state"] = controller.to_state_dict(); final_state["elapsed_minutes"] = controller.elapsed()`，再 `view = plugin.get_state(session_id, final_state)`（get_state 的 _get_controller 对新 dict id 未命中 → _restore_controller 从注入的 controller_state 重建 → game_over=true 正确），最后 `manager.broadcast(..., {"type": "session_ended", "session_id": session_id, "state": view})`；同时 persist 块（:210-218）改用同一 final_state 回写 DB（修复既有 stale 持久化 bug）。后端 backend/app/plugins/triangle_occupy/plugin.py 与 backend/app/plugins/routes.py：⑦更新 validate_result/submit_action/end_session 相关 docstring/注释，明确 `participant_id` 语义 = "被操作的参赛单位 id（裁判替该方操作）"，sides 校验=校验该参赛单位是否为合法阵营成员，操作者身份由路由层 require_referee 保证。Must NOT: 不把权限校验移到插件层（身份校验留在路由层 require_referee）；不改 GameplayPlugin 方法签名；不改变 get_state 返回形状（保持嵌套，前端解包）；不删除 sides 校验逻辑；不改 start_match（todo 3 处理回写）；**不在 plugin.end_session 内修改传入 state**（base.py:10 契约"方法自身不得修改传入的 state"——最终状态同步在路由层通过构造 final_state 副本完成，保持插件契约干净）。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 6,15
  References (executor has NO interview context - be exhaustive): frontend/src/views/MatchPlay.vue:145-172（onmessage/onclose WS 处理，session_ended 当前清空 state）、:174-181（loadMatch 现状——嵌套响应未解包，核心 bug ①）、:187-207（submitAction 硬编码 participant_id: 0，核心 bug ③）、:252-275（onRecordResult 依赖 state.value.winner/scores 与 match.value?.participant_a）；backend/app/api/matches.py:131-155（get_match_detail 返回 MatchDetailOut 嵌套结构，response_model=MatchDetailOut）；backend/app/schemas/match.py:58-62（MatchDetailOut = {match: MatchOut, session: GameSessionOut|None} 确认嵌套）；backend/app/plugins/triangle_occupy/plugin.py:185-196（get_state 嵌套视图形状：{match_id, controller_state:{board,scores,encircled,encirclement_active,l1,elapsed,time_limit,events,game_over,winner,win_type}, elapsed_minutes, sides, game_over, winner}）、:198-220（validate_result）、:222-281（submit_result，:227 `if participant_id not in sides`、:247 `team = sides[participant_id]`）；backend/app/plugins/routes.py:167-197（submit_action，:171 require_referee 依赖）、:199-225（end_session，:221-224 session_ended 广播现状不带 state）；backend/app/services/match_service.py:222-226（start_match 构造 sides：participant_a→defender, participant_b→attacker）；backend/app/plugins/routes.py:65-97（_load_db_session 已做 sides int 键规范化）；frontend/src/plugins/triangle-occupy/TriangleBoard.vue:87-99（TriangleState 接口扁平字段定义）
  Acceptance criteria (agent-executable): `cd backend && .venv\Scripts\python -m pytest tests/test_plugins/test_triangle_occupy.py tests/test_matches.py tests/test_ws.py -q` 全绿（新增/既有用例覆盖：referee 以 participant_a 为 participant_id 调 submit_result 成功且操作落在 defender 阵营；以 participant_b 成功且落在 attacker；以 0 或非 sides 键被拒 400；end_session 后 WS 帧收到 session_ended 且带 state.game_over==true）；`cd frontend && npm run build` 退出码 0（vue-tsc 严格检查，含新 MatchDetailResp 类型）；`grep -n "participant_id: 0" frontend/src/views/MatchPlay.vue` 无匹配；`grep -n "match.value = data" frontend/src/views/MatchPlay.vue` 无匹配（改为 data.match）。
  QA scenarios (name the exact tool + invocation): happy — 新增 pytest：构造 GameSession + sides={3:'defender',4:'attacker'}，referee 身份调 POST /api/gameplay/triangle_occupy/session/{id}/action 传 `{"participant_id": 3, "payload": {"action": "occupy", "cell_id": 1}}` 返回 200 且 state.controller_state.board[1].owner=='defender'；再传 participant_id=4 占领 cell 2 落在 attacker；end_session 后 TestClient websocket_connect 断言收到 session_ended 且带 state.game_over==true；failure — 同端点传 `{"participant_id": 0, ...}` 返回 400 detail="非法操作"，证据 .omo/evidence/task-2-fixed.txt。Commit: Y | fix(gameplay): 修复对局操作链路（响应解包/participant_id/WS状态/会话结束广播）

- [x] 3. 后端数据回写与字段补齐：start_match 回写解析参赛者 + MatchOut/MatchDetailOut 补 gameplay_plugin
  What to do / Must NOT do: ①backend/app/services/match_service.py start_match（:206-216）：单败淘汰后续轮次经 `engine._resolve_participants` 解析出 participant_a/b 后，**回写到 Match 行**（在 :214 解析成功后、:218 取 plugin 之前，加 `match.participant_a = participant_a; match.participant_b = participant_b`），随 :242 的 commit 一并落库——否则前端 match 接口永远读到 null，无法推导 participant_id；②backend/app/schemas/match.py MatchOut（:27-44）：补 `gameplay_plugin: str | None = None` 字段；③backend/app/api/matches.py `_match_out`（:102-109）：填充 gameplay_plugin——`db.get(Competition, match.competition_id).gameplay_plugin`（供前端 MatchPlay 插件化按插件名解析组件）。Must NOT: 不改 _resolve_participants 引擎方法本身；不改 MatchOut 其他字段；不回写 engine_match_id；不破坏 _replay_finished 的重放逻辑（回写仅影响 participant 展示，重放仍按 engine_match_id + result）；不在 build_schedule_for_competition 里回写（排表时单败后续轮次本就未知，回写只发生在开赛解析时）。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 6,15
  References (executor has NO interview context - be exhaustive): backend/app/services/match_service.py:165-257（start_match 全文，:206-216 participant 解析到局部变量但未回写——核心缺口，:218-242 plugin 取用与 GameSession 创建 commit）；backend/app/api/matches.py:102-109（_match_out 现状：仅 model_validate + participant 名称填充）、:131-155（get_match_detail 返回 MatchDetailOut）；backend/app/schemas/match.py:27-44（MatchOut 字段清单，无 gameplay_plugin）、:58-62（MatchDetailOut）；backend/app/models/match.py:39-63（Match 模型 participant_a/b 可空列）；backend/app/models/competition.py（Competition.gameplay_plugin 字段）；backend/app/tournaments/single_elim.py:185-213（_resolve_participants 引擎方法，勿改）
  Acceptance criteria (agent-executable): 新增 pytest（放 tests/test_matches.py）：构造单败淘汰比赛 + 前序对局已完赛，对后续轮次对局调 POST /api/matches/{id}/start 成功后，`db.get(Match, id).participant_a/b` 非 None 且等于引擎解析结果；`GET /api/matches/{id}` 响应 `data.match.gameplay_plugin == "triangle_occupy"`（或该比赛配置的插件名）；`cd backend && .venv\Scripts\python -m pytest tests/test_matches.py -q` 全绿。
  QA scenarios (name the exact tool + invocation): happy — pytest 断言 start 后 Match 行回写 + 详情接口带 gameplay_plugin；failure — 未开赛的后续轮次对局 GET 详情 participant_a/b 为 null（不回写场景），前端应显示"待开赛"而非报错，证据 .omo/evidence/task-3-fixed.txt。Commit: Y | fix(matches): start_match 回写解析参赛者 + 详情补 gameplay_plugin 字段

- [x] 4. 静态托管目录对齐：main.py frontend-dist → frontend/dist
  What to do / Must NOT do: backend/app/main.py:108 将 `_frontend_dist` 的路径从 `"frontend-dist"` 改为 `"frontend"` 子目录下的 `"dist"`（即 `os.path.join(..., "frontend", "dist")`，与 frontend/README、根 README、Vite 默认构建产物一致）。Must NOT: 不创建 frontend-dist 目录；不改前端构建输出目录配置（保持 Vite 默认 dist）；不改其他静态相关逻辑；不改 CORS 或中间件。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): backend/app/main.py:106-110（_frontend_dist 拼接与挂载条件：`os.path.isdir` 才挂载，目录不存在则不挂载）；frontend/vite.config.ts（构建输出目录，确认默认 dist）；根 README.md 部署章节（frontend/dist 表述）；AGENTS.md NOTES（"静态托管：main.py 找 frontend-dist/（README 写 frontend/dist，二者需对齐）"——本 todo 消除该不一致）
  Acceptance criteria (agent-executable): `cd frontend && npm run build`（产物生成 frontend/dist/index.html）；`cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000` 启动后 `curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/` 返回 200 且 `curl -s http://127.0.0.1:8000/ | Select-String "index"` 命中 HTML；启动后 `Test-Path backend/frontend-dist` 为 False（不再查找旧目录）。
  QA scenarios (name the exact tool + invocation): happy — 上述 curl 200 + HTML 命中；failure — 临时把 frontend/dist 改名 frontend/dist.bak 后重启 uvicorn，curl 根路径返回 404（静态未挂载时的行为），改回后恢复，证据 .omo/evidence/task-4-fixed.txt。Commit: Y | fix(deploy): 统一静态托管目录为 frontend/dist

- [x] 5. 内存 _sessions 注释收敛 + admin 玩法插件列表接口
  What to do / Must NOT do: 后端 backend/app/plugins/routes.py：①更新模块 docstring（:13-14 附近）与 `_sessions` 定义注释（:35-37），从"todo 14 换 DB 持久化"改为"GameSession DB 桥已实现（_load_db_session 回退装载 + _persist_session 回写），_sessions 仅作进程内缓存加速"；②新增 GET /api/admin/plugins 端点：**追加到现有 admin 路由模块 backend/app/api/admin_users.py（避免新建文件后遗漏 main.py 的 include_router 注册）**，require_admin 依赖，返回 `[{"name": p.name, "version": p.version} for p in registry.all()]`（registry 为 `app.plugins.registry.registry` 单例，all() 方法已存在）。前端 frontend/src/views/admin/Plugins.vue：改为 onMounted 调 GET /api/admin/plugins 渲染列表（当前为静态硬编码 triangle_occupy 展示，含一行 alert"后端 /api/gameplay/* 未实现"——移除该 alert）。Must NOT: 不删除 _sessions/内存缓存层（插件直建路径与测试依赖）；不改 registry.py 的 PluginRegistry 接口；不给该端点加业务逻辑（仅列表）；不新建 api/admin_plugins.py（除非同时在 main.py 注册 include_router——推荐直接追加到 admin_users.py 避免遗漏）。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): backend/app/plugins/routes.py:13-14（模块 docstring 的 todo 14 表述）、:35-38（_sessions 定义与注释）、:65-97（_load_db_session DB 桥）、:110-129（_persist_session）；backend/app/plugins/registry.py:58-60（registry.all() 存在，返回已注册插件列表）；backend/app/api/admin_users.py（admin 路由模块模式参考：require_admin 依赖、_request_meta、审计写法）；backend/app/main.py:96（admin_users_router 已 include_router，追加端点无需改 main.py）；frontend/src/views/admin/Plugins.vue（当前静态展示 + alert）；frontend/src/views/AGENTS.md（"admin/Plugins.vue 仅静态展示内置 triangle_occupy，无管理接口"——本 todo 消除）
  Acceptance criteria (agent-executable): `cd backend && .venv\Scripts\python -m pytest tests/test_plugins/test_registry.py -q` 全绿；新增 pytest：admin 调 GET /api/admin/plugins 返回 200 且 body 含 `{"name": "triangle_occupy"}`；player 调同端点 403；`cd frontend && npm run build` 退出码 0。
  QA scenarios (name the exact tool + invocation): happy — admin 登录 curl `-b cookies.txt http://127.0.0.1:8000/api/admin/plugins` 返回 200 JSON 含 triangle_occupy；failure — player 登录 curl 同端点返回 403，证据 .omo/evidence/task-5-fixed.txt。Commit: Y | feat(admin): 玩法插件列表接口 + 内存会话注释收敛

- [ ] 6. 前端插件化：MatchPlay 按 gameplay_plugin 名动态解析玩法组件
  What to do / Must NOT do: frontend/src/views/MatchPlay.vue：①新增插件组件映射表 `const PLUGIN_COMPONENTS: Record<string, { board: Component; controls: Component | null }> = { triangle_occupy: { board: TriangleBoard, controls: TriangleControls } }`（保留静态 import TriangleBoard/TriangleControls，不做动态 import——单玩法映射表足够）；②模板改为 `<component :is="boardComp" :state="state" :selectable="..." @select="onSelectCell" />` 与 `<component :is="controlsComp" v-if="isRefereeOrAdmin && controlsComp" ... />`；③`boardComp/controlsComp` 由 computed 从 `PLUGIN_COMPONENTS[match.value?.gameplay_plugin ?? '']` 计算（gameplay_plugin 来自 todo 3 补的 _match_out 字段，经 todo 2 的 data.match 解包后可得）；④未知插件名时渲染降级提示（el-alert "该玩法暂未支持前端组件"）。Must NOT: 不引入 defineAsyncComponent/动态 import()（当前单玩法）；不重构 TriangleBoard/TriangleControls 内部；不改 router；不影响选手只读视图逻辑；不破坏 todo 2 的解包与 participant_id 修复。
  Parallelization: Wave 2 | Blocked by: 2,3 | Blocks: 15
  References (executor has NO interview context - be exhaustive): frontend/src/views/MatchPlay.vue:73（当前硬编码 import TriangleBoard/TriangleControls）、:32-58（模板中 TriangleBoard/TriangleControls 用法）、:105（isRefereeOrAdmin）；frontend/src/plugins/triangle-occupy/index.ts（组件导出形态，TriangleBoard/TriangleControls 具名导出）；AGENTS.md（"前端插件化是半成品：MatchPlay.vue 硬编码 import TriangleBoard/Controls，未按插件名动态解析组件"——本 todo 消除该反模式）；todo 3 补的 MatchOut.gameplay_plugin 字段；todo 2 的 data.match 解包（match.value.gameplay_plugin 可用）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 退出码 0；`grep -n "<TriangleBoard\|<TriangleControls" frontend/src/views/MatchPlay.vue` 无匹配（模板不再直接用组件标签，改用 `<component :is>`）；`grep -n "PLUGIN_COMPONENTS" frontend/src/views/MatchPlay.vue` 有匹配；后端 `cd backend && .venv\Scripts\python -m pytest tests/test_matches.py -q` 全绿。
  QA scenarios (name the exact tool + invocation): happy — npm run build 成功 + 对局页渲染棋盘；failure — 把比赛 gameplay_plugin 临时改为不存在的名字 "ghost_plugin"，对局页显示降级提示（el-alert 文案"该玩法暂未支持前端组件"）而非白屏（Playwright 或手动冒烟断言），改回后恢复，证据 .omo/evidence/task-6-fixed.txt。Commit: Y | refactor(frontend): MatchPlay 按插件名动态解析玩法组件

- [ ] 7. 权限模型补全：admin 增删账号（硬删）+ 玩法路由补 per-competition referee_ids 校验（堵越权）
  What to do / Must NOT do: ①backend/app/api/admin_users.py 新增 POST /api/admin/users（admin 创建账号：username/email/password/role，复用 auth 的 hash_password，role 必须是 admin/referee/player 之一，username 唯一冲突 400，写 audit "admin_create_user"）；新增 DELETE /api/admin/users/{id}（硬删除：**级联清理清单（完整版，SQLite FK 仅 metadata 不强制，全靠手工）**——Registration.user_id 删行、PointTransaction.user_id 删行、TeamMember.user_id 删行、Team（该用户任队长的，先删该队全部 TeamMember 再删 Team）、AuditLog.user_id 置 NULL（保留审计追溯）、**Match.referee_id 置 NULL（FK 可空，避免悬空）**；**保护规则**：不允许删除自己、不允许删除最后一个 admin、**不允许删除作为任何比赛 Competition.created_by 的用户**（该字段 FK NOT NULL，删除会悬空且 CompetitionOut 暴露——校验 `db.query(Competition).filter(Competition.created_by==id).count()>0` 时 400"该用户创建了比赛，无法删除"；或改为将 created_by 转移给当前 admin，二选一，推荐拒绝删除更安全）；**可选**：对存在未完结对局（Match.status in pending/in_progress 且 participant_a/b 含该用户）的参赛者拒绝删除或警告（避免打破赛程，推荐拒绝并提示"该用户有未完结对局"）；写 audit "admin_delete_user"（在删除前写，actor 是当前 admin）。②backend/app/plugins/routes.py **所有 require_referee 端点补 per-competition referee_ids 校验（④A 一致性，覆盖 create_session/submit_action/end_session 三处）**：在现有 require_referee 依赖基础上，根据 session/payload→match_id→competition 查 referee_ids，校验 `staff.id in competition.referee_ids or staff.role == 'admin'`，否则 403"非本场比赛裁判"。具体：submit_action/end_session 经 `session["match_id"]`→Match→Competition；**create_session 经 `payload.match_id`**→Match→Competition（补全 ④A"所有端点"，堵非指派裁判替他人比赛建会话）。复用 match_service._require_assigned_referee 的语义，但 plugins/routes 无 service 层（避免 plugins→services 反向依赖，与 AGENTS.md 流向一致），直接在路由内查 DB。前端 frontend/src/views/admin/Users.vue：③新增"创建用户"按钮+对话框（用户名/邮箱/密码/角色表单，调 POST /api/admin/users）；④每行新增"删除"按钮+确认弹窗（调 DELETE /api/admin/users/{id}，删除成功后刷新列表；后端拒绝时展示 detail 错误信息如"该用户创建了比赛，无法删除"）。Must NOT: 不做软删除/回收站（用户确认硬删除）；不改变 require_referee 的全局角色语义（保留全局 referee 角色，仅补比赛级校验）；不把校验逻辑移到插件层；不删除 _require_assigned_referee（match_service 仍用它）；不改 rbac.py；不级联删除 User 本身以外的用户行（只清业务数据）；不清理 Registration.approved_by / PointTransaction.created_by（无 FK，悬空无害，保留追溯）。
  Parallelization: Wave 3 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): backend/app/api/admin_users.py:28-86（现状：仅 GET list + PATCH role/status/password，无 POST/DELETE）、router 级 require_admin 依赖；backend/app/core/rbac.py:63-64（require_admin/require_referee）；backend/app/core/security.py（hash_password 函数，复用）；backend/app/models/user.py（User 模型）、team.py（TeamMember/Team，captain_id 关联）、registration.py（Registration.user_id）、point.py（PointTransaction.user_id）、audit_log.py（AuditLog.user_id 可空）；backend/app/services/match_service.py:109-112（_require_assigned_referee 语义参考：`if referee.id not in (competition.referee_ids or []): raise 403`）；backend/app/plugins/routes.py:167-197（submit_action，:171 require_referee）、:199-225（end_session，:202 require_referee）、:65-97（_load_db_session 返回含 match_id）、:100-107（_get_session）；frontend/src/views/admin/Users.vue:110-230（现状：搜索/改角色/封禁/重置密码，无创建/删除 UI）；frontend/src/views/AGENTS.md（"admin/Users.vue 无创建/删除用户"——本 todo 消除）
  Acceptance criteria (agent-executable): 新增 pytest tests/test_admin_users_crud.py：admin POST 创建账号 200、重复用户名 400、role 非法 400；admin DELETE 删除用户 200 且其 Registration/PointTransaction/TeamMember 被级联清理；DELETE 自己 403/400；DELETE 最后一个 admin 400；player 调两端点 403。新增 pytest tests/test_plugins/test_referee_scope.py：全局 referee（不在某比赛 referee_ids）调该比赛对局的 submit_action/end_session 返回 403；该比赛指派裁判 200；admin 200。`cd frontend && npm run build` 退出码 0。
  QA scenarios (name the exact tool + invocation): happy — admin 创建 referee 账号 → 该账号被指派到比赛 → 能操作该比赛对局；failure — 全局 referee 调非指派比赛的 submit_action 返回 403"非本场比赛裁判"、player 调创建/删除 403、删除最后一个 admin 400，证据 .omo/evidence/task-7-fixed.txt。Commit: Y | feat(rbac): admin 增删账号 + 玩法路由比赛级裁判校验

- [ ] 8. 允许删除 finished 比赛 + 级联清理 Match/GameSession/PointTransaction
  What to do / Must NOT do: ①backend/app/api/competitions.py：`DELETABLE_STATUSES = ("draft", "cancelled", "finished")`（:46，追加 finished）；②delete_competition（:181-198）：级联删除该比赛的所有 Match（含其 GameSession，先查 Match.id 列表 → 删 GameSession where match_id in (...) → 删 Match）、PointTransaction（where ref_competition_id == id）、Registration（已有）；③前端 frontend/src/views/admin/Competitions.vue：`deletable(s)` 函数（:205-207）追加 finished 可删除（`return s === 'draft' || s === 'cancelled' || s === 'finished'`）。Must NOT: 不级联删除 User（只清业务数据）；不删除 cancelled 以外的终态转换（状态机不变）；不改 TRANSITIONS；不软删除比赛；不清理 AuditLog（审计需保留追溯）。
  Parallelization: Wave 3 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): backend/app/api/competitions.py:46（DELETABLE_STATUSES=("draft","cancelled")）、:181-198（delete_competition 现状：仅清 Registration，不清 Match/GameSession/PointTransaction——SQLite FK 仅 metadata 无级联）、:9（docstring 写"draft/cancelled only"需更新）；backend/app/models/match.py:39-80（Match 与 GameSession，GameSession.match_id FK）、point.py:32（PointTransaction.ref_competition_id）；frontend/src/views/admin/Competitions.vue:205-207（deletable 函数）、:188-194（TRANSITIONS 表，finished:[] 终态不变）
  Acceptance criteria (agent-executable): 新增 pytest（放 tests/test_competitions.py）：admin DELETE finished 比赛 200 且该比赛的 Match/GameSession/PointTransaction 全部被清理（count==0）；DELETE ongoing 比赛 400；player DELETE 403。**必须改写的既有测试**：`test_competitions.py:318 test_delete_finished_competition_returns_400`（当前断言 finished 删除返回 400，与本 todo 目标正面冲突）——改写为断言 200 + 级联清理验证。`cd backend && .venv\Scripts\python -m pytest tests/test_competitions.py -q` 全绿。`cd frontend && npm run build` 退出码 0。
  QA scenarios (name the exact tool + invocation): happy — admin 删除已结束比赛后，该比赛的对局/会话/积分流水全清；failure — 删除 ongoing 比赛返回 400"比赛已开始或已结束，无法删除"（错误信息需更新为更准确的"进行中的比赛无法删除"，或保留原文但 finished 放行），证据 .omo/evidence/task-8-fixed.txt。Commit: Y | feat(competitions): 允许删除已结束比赛 + 级联清理

- [ ] 9. 积分合并：移除 finished 自动结算 + 单一积分 admin 手动发放 + 排行榜合并
  What to do / Must NOT do: ①backend/app/api/competitions.py change_status（:157-173）：移除 finished 流转时的 `points_service.settle_competition_points(db, competition)` 调用（保留未完成对局守卫 400）；②backend/app/services/points_service.py：settle_competition_points 函数保留（兼容旧测试）但加 docstring 注明"不再自动调用，仅保留供手动/测试调用"；③backend/app/api/points.py leaderboard：合并为单一 total（移除 competition_sum/activity_sum 分列，或保留但前端不用）；④backend/app/schemas/point.py：leaderboard 响应保留 total，competition_sum/activity_sum 可选；⑤前端 frontend/src/views/admin/Points.vue：移除"类型"下拉（:26-31，统一"积分"），排行榜表格移除 competition_sum/activity_sum 列（:52-53，只留 total）；⑥前端 frontend/src/views/Rankings.vue：三 tab 改为单一"积分排行榜"（移除全局/比赛/活动 tab 切换，或保留全局但移除 kind 参数）；⑦新流水 kind 统一 "manual"（admin 发放时默认 manual，不再区分 activity）。Must NOT: 不做积分历史数据迁移（保留 kind 列与历史 competition 流水）；不删除 settle_competition_points 函数（兼容旧测试）；不改变 PointTransaction 模型；不移除 admin 手动发放的 reason 必填校验。
  Parallelization: Wave 3 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): backend/app/services/points_service.py:64-176（settle_competition_points 自动结算逻辑）、:178+（get_leaderboard/get_user_points）；backend/app/api/competitions.py:157-173（finished 流转自动调 settle）、:171（settle_competition_points 调用点——本 todo 移除）；backend/app/api/points.py（leaderboard 端点，kind 过滤）；backend/app/schemas/point.py（LeaderboardRow schema）；frontend/src/views/admin/Points.vue:26-31（类型下拉 activity/manual）、:52-53（排行榜 competition_sum/activity_sum 列）、:81-86（grant.kind 默认 activity）；frontend/src/views/Rankings.vue:11-13（三 tab）、:70-73（loadLeaderboard 按 kind）；用户确认 ①A（积分改纯手动）
  Acceptance criteria (agent-executable): `cd backend && .venv\Scripts\python -m pytest tests/test_points.py tests/test_rankings.py -q` 全绿（**必须改写的既有测试清单**：`test_points.py:158 test_finish_competition_auto_settles_transactions`——当前断言 finished→自动结算产生流水，与本 todo 直接矛盾，改写为断言 finished 后无自动流水 + admin 手动发放后流水存在；`test_rankings.py:141 test_global_rankings_delegate_to_leaderboard` 与 `:154 test_rankings_global_matches_points_leaderboard`——当前靠 finished→auto-settle 造流水再断言 leaderboard，移除后流水为 0 必红，改写为用 admin 手动发放端点造数；`test_points.py:211/222` 直调 settle 函数则保留绿）；新增 pytest：比赛 finished 后查询 PointTransaction 无新增 competition 流水（count 不变）；admin 手动发放仍正常。`cd frontend && npm run build` 退出码 0；`grep -n "competition_sum\|activity_sum" frontend/src/views/admin/Points.vue` 无匹配（列已移除）。**同步更新 README.md 功能特性第 5 条"比赛结束自动结算"表述**（移除"自动"，改为"admin 手动发放"）。
  QA scenarios (name the exact tool + invocation): happy — 比赛 finished 后查询 PointTransaction 无新增 competition 流水；admin 手动发放后排行榜 total 更新；failure — 重复手动发放流水翻倍（验证幂等性未被破坏——若原幂等逻辑在 settle 而非手动发放，需确认手动发放的幂等性），证据 .omo/evidence/task-9-fixed.txt。Commit: Y | refactor(points): 移除自动结算 + 单一积分手动发放

- [ ] 10. 首页改版：移除比赛卡片纯宣传 + 比赛列表迁移到 Competitions.vue
  What to do / Must NOT do: ①frontend/src/views/Home.vue：移除比赛卡片区（:74 前模板区的比赛列表 + :186-198 loadCompetitions + :97-99 competitions ref），保留宣传轮播（slides）+ CTA 按钮（"立即报名"/"查看比赛"——"查看比赛"跳转 /competitions）；②frontend/src/views/Competitions.vue：从空壳改为完整比赛列表页（复用 Home.vue 移除的列表逻辑：GET /competitions、卡片渲染、状态标签、跳转详情、空态）；③导航栏确保 /competitions 入口可达（router/index.ts 已有路由，确认导航栏链接存在）。Must NOT: 不删除宣传轮播 slides 与 SVG 插画；不改路由路径（/competitions 已存在）；不引入轮播框架依赖；不移除 Home 的"立即报名"CTA（可跳 /competitions 或 /login）。
  Parallelization: Wave 4 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): frontend/src/views/Home.vue:74-198（比赛卡片区模板 + loadCompetitions + competitions ref + STATUS_LABELS/STATUS_TYPES）、:102-142（slides 宣传轮播数据，保留）、:178-184（scrollToList/goDetail，goDetail 迁移）；frontend/src/views/Competitions.vue:1-8（当前空壳仅标题）；frontend/src/router/index.ts（/competitions 路由已存在）；frontend/src/views/AGENTS.md（"Competitions.vue 是空壳，列表逻辑在 Home.vue"——本 todo 消除职责错位）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 退出码 0；`grep -n "loadCompetitions" frontend/src/views/Home.vue` 无匹配（已迁移）；`grep -n "loadCompetitions" frontend/src/views/Competitions.vue` 有匹配（已接收）；首页 Playwright 冒烟截图只含宣传轮播无比赛卡片（.omo/evidence/task-10-fixed.png）；/competitions 页渲染比赛列表。
  QA scenarios (name the exact tool + invocation): happy — 首页纯宣传 + /competitions 显示列表 + 点卡片跳详情；failure — /competitions 空数据时显示空态而非报错，证据 .omo/evidence/task-10-fixed.txt。Commit: Y | refactor(frontend): 首页纯宣传 + 比赛列表独立页

- [ ] 11. 比赛详情竞态修复：补 watch(route.params.cid) + loading 初值
  What to do / Must NOT do: frontend/src/views/CompetitionDetail.vue：①新增 `watch(() => route.params.cid, async (newCid) => { if (newCid) { await loadCompetition(); await loadRegistrations(); await loadMatches(); await loadRankings(); } })`（与 onMounted 内容一致，避免组件复用时参数变化不重载）；②`loading` ref 初值改为 true（:247 `const loading = ref(false)` → `ref(true)`，避免加载前 el-empty 闪现"比赛不存在"）；③404 时区分"加载中/不存在"：模板中 `v-if="loading"` 显示加载中、`v-else-if="!competition"` 显示不存在、`v-else` 显示内容（当前 :3 el-empty 可能未区分）。Must NOT: 不改 loadCompetition 等函数内部逻辑；不引入额外的状态管理；不影响 admin 审批/报名等其他功能；不改 API 调用。
  Parallelization: Wave 4 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): frontend/src/views/CompetitionDetail.vue:244（cid = computed(() => Number(route.params.cid))）、:247（loading ref(false)）、:368-378（loadCompetition）、:477-484（onMounted 加载全部数据，无 watch）、:3 附近（el-empty"比赛不存在"显示条件）；frontend/src/views/MatchPlay.vue（同类问题：缺 watch mid，但本 todo 聚焦 CompetitionDetail，MatchPlay 的 watch 可选——若 MatchPlay 也有组件复用场景则一并补，否则留到后续）；Vue 3 watch 与 onMounted 共用的标准模式
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 退出码 0；`grep -n "watch(() => route.params.cid" frontend/src/views/CompetitionDetail.vue` 有匹配；`grep -n "const loading = ref(true)" frontend/src/views/CompetitionDetail.vue` 有匹配；Playwright 冒烟：从 /competitions/1 导航到 /competitions/2（若存在）详情页内容更新（非陈旧）。
  QA scenarios (name the exact tool + invocation): happy — 切换 cid 后页面显示新比赛数据；failure — 不加 watch 时切换 cid 显示旧数据（验证 bug 存在），加 watch 后修复，证据 .omo/evidence/task-11-fixed.txt。Commit: Y | fix(frontend): 比赛详情路由参数变化重载 + loading 初值

- [ ] 12. 赛程图可视化：单败淘汰 bracket 签表 + 循环/瑞士轮次对阵表
  What to do / Must NOT do: 新增前端组件 frontend/src/components/ScheduleChart.vue（或 frontend/src/plugins/schedule/）：①**单败淘汰 bracket**：树状签表，按轮次从左到右（或从上到下）展示对阵，胜者连线晋级，bye 标注轮空，季军赛单独分支；数据源 GET /api/competitions/{cid}/matches（MatchOut 列表含 participant_a/b、status、result、round_id）；用 CSS grid 或 flex 布局手写（不引入 bracket 库）；②**循环赛/瑞士轮**：按 round_id 分组的对阵表（轮次为列/行，每轮若干对阵卡片，显示双方名称与比分/状态）；③集成进 CompetitionDetail.vue：替换或增强现有赛程卡片区（:132-161），按 tournament_format 选择渲染 bracket 还是轮次表；④未知 format 降级为现有卡片列表。Must NOT: 不引入 bracket/树图第三方库（手写 CSS，保持轻量）；不改后端赛制引擎；不改 GET /matches 接口；不做实时 WS 更新赛程图（页面刷新拉取即可）；不做拖拽/编辑功能（只读展示）。
  Parallelization: Wave 4 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): frontend/src/views/CompetitionDetail.vue:132-161（现有赛程卡片区，按 round_id 分组）、:212-221（MatchInfo 接口：id/round_id/participant_a/b/status/result）、:394-408（loadMatches 按 round_id 分组为 RoundGroup[]）、:244（cid）；backend/app/api/matches.py:112-128（GET /api/competitions/{cid}/matches 返回 list[MatchOut]）；backend/app/schemas/match.py:27-44（MatchOut 字段：participant_a/b、participant_a_name/b_name、status、result、result_type、round_id）；backend/app/tournaments/single_elim.py（bracket 结构：_build_schedule 生成 rounds，_match_position 记录位置——供理解数据形状，不改引擎）；用户确认 ③B（三赛制赛程图）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 退出码 0；Playwright 冒烟：单败淘汰比赛详情页渲染 bracket（至少显示首轮对阵 + 连线，.omo/evidence/task-12-fixed.png）；循环赛详情页渲染轮次对阵表；未知 format 降级显示卡片列表不白屏。
  QA scenarios (name the exact tool + invocation): happy — 三种赛制各有对应可视化；failure — 空赛程（比赛未进 ongoing）显示空态"暂无赛程"而非白屏，证据 .omo/evidence/task-12-fixed.txt。Commit: Y | feat(frontend): 赛程图可视化（bracket + 轮次对阵表）

- [ ] 13. 清理 4 处 as any（Home/CompetitionDetail/admin Competitions/Traffic）
  What to do / Must NOT do: 清理违反项目"禁止 as any"约定的处：①frontend/src/views/Home.vue:163 `return (STATUS_TYPES[s] as any) || 'info'` → STATUS_TYPES 已声明 `Record<string, string>`，改为 `return STATUS_TYPES[s] || 'info'`（索引访问 string 返回 string，无需断言）；②frontend/src/views/CompetitionDetail.vue:286 同模式同样清理；③frontend/src/views/admin/Competitions.vue:200 同模式同样清理；④frontend/src/views/admin/Traffic.vue:278 `data.items.map((it: any) => ...)` → 定义 LogItem 接口（id/action/username/ip/user_agent/detail/created_at 等字段，参照后端 AuditLog 模型与 admin_traffic 响应），改为 `(it: LogItem)`；⑤frontend/src/components/PointsTransactions.vue:79（第 5 处 as any，在 views/ 之外）同样清理。Must NOT: 不改变运行时行为（纯类型清理）；不引入额外的类型导入（LogItem 就地定义）；**不清理 `catch (e: any)` 模式**（views/ 下 20+ 处，views/AGENTS.md 明确列为共享模式，属合理类型断言，非 as any 反模式）；不清理非 as any 的合理类型断言（如 catch 块的 `e as {response?...}`）。
  Parallelization: Wave 4 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): frontend/src/views/Home.vue:163（STATUS_TYPES[s] as any）、frontend/src/views/CompetitionDetail.vue:286（同）、frontend/src/views/admin/Competitions.vue:200（同）、frontend/src/views/admin/Traffic.vue:278（it: any）、frontend/src/components/PointsTransactions.vue:79（第 5 处，views/ 之外）；AGENTS.md ANTI-PATTERNS（"前端禁止 as any / @ts-ignore——类型错误必须真修"）；backend/app/models/audit_log.py（AuditLog 字段供 LogItem 接口定义参考）；backend/app/api/admin_traffic.py（响应结构参考）；frontend/tsconfig.app.json（noUnusedLocals 等严格 lint）；frontend/src/views/AGENTS.md（catch (e: any) 共享模式说明，本 todo 不清理此类）
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 退出码 0（vue-tsc 严格通过）；`grep -rn "as any" frontend/src/` 无匹配（5 处全清，含 components/）；`grep -n "it: any" frontend/src/views/admin/Traffic.vue` 无匹配。**注意**：不要求 `grep ": any"` 无匹配（catch (e: any) 共享模式保留）。
  QA scenarios (name the exact tool + invocation): happy — build 成功 + grep "as any" 无匹配；failure — 故意改回一处 as any 后 build 应报错（验证 tsconfig 严格性），证据 .omo/evidence/task-13-fixed.txt。Commit: Y | chore(frontend): 清理 as any 类型断言

- [ ] 14. 部署补全：Dockerfile + docker-compose.yml + Caddyfile + backup.sh + backup_restore_test.sh + 部署手册 + 玩法模板开发规范
  What to do / Must NOT do: ①deploy/Dockerfile（多阶段：node 构建前端 → python 运行 uvicorn 托管静态，基础镜像 python:3.14-slim + node:20-alpine，COPY requirements.txt → pip install → COPY backend → 前端构建产物放 frontend/dist）；②deploy/docker-compose.yml（单服务 app + SQLite 卷挂载 ./data:/app/backend + 环境变量 SECRET_KEY/DATABASE_URL 等 + 端口映射 8000:8000）；③deploy/Caddyfile（HTTPS 反代配置模板，反代 :8000，自动 HTTPS）；④deploy/backup.sh（sqlite3 .backup 或 python 脚本，备份到 ./backups/，保留最近 7 份，cron 友好）；⑤deploy/backup_restore_test.sh（**恢复演练**：从备份文件恢复到临时目录并用 sqlite3 校验表行数，备份必须可恢复才合格，非零退出）；⑥docs/部署手册.md（**目标环境：国内轻量服务器（腾讯云/阿里云香港 2C2G 优先，免备案），观众主要在国内，不使用 Cloudflare Pages**；A=Docker Compose / B=systemd 裸跑两方案；Caddy 自动 HTTPS；如需域名则提醒国内服务器 ICP 备案、香港节点免备案；密钥管理；SQLite WAL 备份注意事项——连同 -wal/-shm 一起拷）；⑦docs/玩法模板开发规范.md（GameplayPlugin 规范文档化：manifest.json 必填字段、plugin.py 暴露 plugin 实例、五方法契约、validate_result 只做值域校验 Metis E7、前端组件对称命名）。Must NOT: 不在本任务实际部署到公网服务器（服务器由用户按手册购置）；不提交真实密钥到 git；不写 Cloudflare Pages 部署步骤（已决策不用）；不引入 nginx（用 Caddy）。
  Parallelization: Wave 5 | Blocked by: — | Blocks: 15
  References (executor has NO interview context - be exhaustive): AGENTS.md NOTES（"里程碑 tag v0.0-v0.4 对应 M0-M10；M11 部署待用户验收后执行"——本 todo 执行 M11）；backend/app/main.py:106-110（静态托管 frontend/dist，todo 4 已对齐）；backend/requirements.txt（依赖清单）；frontend/package.json（构建命令 npm run build）；backend/app/config.py（SECRET_KEY/DATABASE_URL 环境变量）；.omo/plans/competition-web.md todo 26（原部署计划，本 todo 继承其 Metis E18 恢复演练要求与国内服务器决策）；2026-08-02 用户决策（观众主要在国内 → 国内轻量服务器单机部署，弃用 Cloudflare Pages）；backend/seed.py:51-59（默认密码警告，部署手册需强调修改）
  Acceptance criteria (agent-executable): 本机无 Docker 则验证文件齐全 + `docker compose config` 语法可解析（若用户装 Docker 后执行 `docker compose up -d --build` 冒烟）；**backup.sh 在本机对测试 db 执行一次生成备份文件，backup_restore_test.sh 从备份恢复并校验行数一致**；部署手册含步骤序号与国内服务器购置指引（腾讯云/阿里云香港轻量 2C2G）；玩法规范含 manifest/plugin/五方法说明。
  QA scenarios (name the exact tool + invocation): happy — backup.sh 执行后备份文件存在且含数据，恢复演练通过；failure — 服务器无 Docker 时文档给出 B 方案完整步骤（不依赖 Docker 命令）、恢复演练失败则脚本非零退出，证据 .omo/evidence/task-14-fixed.txt。Commit: Y | docs(deploy): 部署方案、备份恢复脚本与玩法模板开发规范

- [ ] 15. 全量回归验证（后端 pytest 全绿 + 前端 build + 核心链路 UI 冒烟）
  What to do / Must NOT do: ①`cd backend && .venv\Scripts\python -m pytest tests -q` 全量跑（252 个既有 + 本计划新增），0 failed；②`cd frontend && npm run build` 退出码 0；③核心链路 UI 冒烟（**必须走前端 UI 路径而非仅 curl**）：`cd backend && .venv\Scripts\python reset_db.py --yes`（验证 todo 1）→ 启动 uvicorn + 前端 dev → admin/referee 登录 → 打开演示赛对局页 → 断言：状态标签显示正确（非"未开始"兜底）、双方昵称显示（非"选手A/选手B"兜底）、棋盘渲染非空白（有 21+ 格）、referee 选 actingSide 后点格子"占领"成功且棋盘更新、结束对局后"记录结果"按钮可见、点击后结果落库；④权限/积分/删除冒烟：admin 创建/删除账号、全局 referee 操作非指派比赛对局被 403、删除 finished 比赛后数据清理、比赛 finished 无自动积分流水；⑤产出验收记录 .omo/evidence/task-15-fixed.md 逐项 ✓/✗（含截图）。Must NOT: 不修复本次回归中新发现的非计划内问题（记录到验收记录"遗留问题"区，由用户决定是否进下一轮计划）；不跳过任何验收项；冒烟不得用 curl 代替前端 UI 路径（核心 bug 本就是前端数据解包问题）。
  Parallelization: Wave 6 | Blocked by: 1-14 | Blocks: —
  References (executor has NO interview context - be exhaustive): backend/tests/AGENTS.md（三层隔离机制，252 个测试）；frontend/AGENTS.md（无单测，质量保障=npm run build）；.omo/plans/competition-web.md todo 25（M10 联调验收先例与记录格式）；backend/README.md（默认账号 admin/admin123、referee/referee123、player1-8/player123 供冒烟登录）；frontend/src/views/MatchPlay.vue（冒烟断言点：状态标签/昵称/棋盘格/记录按钮/actingSide 切换）；frontend/src/views/admin/Users.vue（创建/删除按钮）；frontend/src/views/CompetitionDetail.vue（赛程图渲染）
  Acceptance criteria (agent-executable): `cd backend && .venv\Scripts\python -m pytest tests -q` 输出 "N passed" 且 0 failed；`cd frontend && npm run build` 退出码 0；验收记录文件全部 ✓（含对局页 UI 冒烟 + 权限/积分/删除冒烟断言项）。
  QA scenarios (name the exact tool + invocation): happy — 全量 pytest 0 failed + 对局页 UI 冒烟全 ✓ + 权限/积分/删除冒烟全 ✓；failure — 任一验收项 ✗ 则记录原因并回修对应 todo 后重验，证据 .omo/evidence/task-15-fixed.md。Commit: Y | test: 全量回归与对局链路验收通过

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit
- [ ] F2. Code quality review
- [ ] F3. Real manual QA
- [ ] F4. Scope fidelity

## Commit strategy
- Conventional Commits：`fix(gameplay):` 对局链路、`fix(matches):` 参赛者回写与字段补齐、`fix(deploy):` 静态托管、`fix(frontend):` 竞态、`feat(admin):` 插件接口/增删账号、`feat(rbac):` 裁判校验、`feat(competitions):` 删除 finished、`feat(frontend):` 赛程图、`refactor(frontend):` 插件化/首页改版、`refactor(points):` 积分合并、`chore(db):` 重置脚本、`chore(frontend):` as any 清理、`docs(deploy):` 部署产物、`test:` 回归
- 单 commit 只做一件事；不混合无关改动
- 禁止提交 `.env`、`*.db`、`node_modules/`、`.venv/`（.gitignore 已含）
- 每个 todo 完成即 commit；全部完成后可打 tag `v0.5`（修复与补全里程碑）

## Success criteria
- `cd backend && .venv\Scripts\python reset_db.py --yes` 一键回到干净种子数据（admin/referee/player1-8 + 2 队 + 演示赛），重复运行幂等；后端运行中执行时给出友好占用提示
- 对局操作链路 UI 全通：referee/admin 在对局页看到正确状态标签与双方昵称（非兜底文案）、棋盘渲染 21+ 格非空白、选 actingSide 后点格子"占领"成功且棋盘实时更新、结束对局后"记录结果"按钮可见、点击后结果落库；选手无操作按钮且直接调 API 被 403/400 拒
- 单败淘汰后续轮次：开赛后前端能读到已解析的参赛者并正常操作
- `cd backend && .venv\Scripts\python -m pytest tests -q` 全部通过（0 failed）
- `cd frontend && npm run build` 构建成功
- 静态托管：前端构建产物放 frontend/dist 后，后端单端口 8000 直接托管网站首页
- admin 后台：玩法模板页调 GET /api/admin/plugins 动态渲染；可创建/删除账号；删除 finished 比赛后级联清理
- 全局 referee 操作非指派比赛的对局被 403 拒绝（堵越权）
- 比赛 finished 不再自动产生积分流水；admin 手动发放正常；排行榜单一 total
- 首页纯宣传轮播；/competitions 独立列表页；比赛详情切换 cid 正确重载
- 单败淘汰 bracket 签表 + 循环/瑞士轮次对阵表可视化渲染
- frontend/src/views/ 下无 as any / : any
- 部署产物齐全：Dockerfile + docker-compose.yml + Caddyfile + backup.sh + backup_restore_test.sh + 部署手册（A/B 两方案）+ 玩法模板开发规范
- MatchPlay.vue 不再硬编码 participant_id=0、不再把嵌套响应整体赋值给 match、不再直接用 TriangleBoard/TriangleControls 组件标签（映射表驱动）
