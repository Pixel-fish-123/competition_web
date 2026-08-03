# competition-web-fixes - Work Plan

## TL;DR (For humans)

**What you'll get:** 一个一键重置数据库的开发工具脚本，以及把"对局玩法操作跑不通"这个核心问题彻底修好的完整修复。修复后，裁判/admin 能在对局页正常替双方选手操作三角占领棋盘（占领/取消/重占/结束对局），并能完整走通"结束对局 → 记录结果"链路；前端对局页不再写死单一玩法组件；网站静态页面能被后端正常托管。

**Why this approach:** 评审确认"操作跑不通"是**一串连环 bug**，不止一处：①前端把嵌套的接口响应整个当扁平数据用，导致对局信息字段全部读不到；②参赛者 ID 被硬编码成 0，后端校验必然拒绝；③WS 推送的对局状态是嵌套结构，前端棋盘渲染空白；④结束对局后前端清空状态，"记录结果"按钮消失。这些必须一起修，链路才能真正打通。重置脚本优先交付，方便你测试前随时回到干净数据。

**What it will NOT do:** 不做新玩法插件；不给重置脚本加备份功能（你已确认无需备份）；不重构赛制引擎/积分/排行榜/认证；不改 demo 游戏规则核心逻辑；不改变插件契约方法签名与返回形状（get_state 仍返回嵌套视图，前端负责解包）；不做 CI/CD。

**Effort:** Short
**Risk:** Low - 核心 bug 根因链已定位（前端数据解包错误 + participant_id 硬编码 + WS 状态嵌套 + 会话结束状态丢失），改动集中在 MatchPlay.vue 与 match_service/routes 少量后端行，回归由现有 252 个 pytest + 前端 build 兜底
**Decisions I made for you:** ① 重置脚本=完全重置、无备份、CLI 带确认，锁检测改为"删除时捕获 PermissionError"（WAL 下 PRAGMA 检测无效）；② 玩法操作修复=前端解包嵌套响应 + 推导"被操作的参赛方 id" + 后端 start_match 回写解析出的参赛者；③ WS 状态=后端 get_state 保持嵌套契约不变，前端解包 controller_state（最小改动）；④ 前端插件化=动态组件 + 插件名映射表（不引入动态 import）；⑤ 静态目录统一为 frontend/dist；⑥ _sessions 保留作缓存（DB 桥已就位），仅收敛注释；⑦ 每个修复补回归测试。

Your next move: 批准后运行 `$start-work competition-web-fixes` 开始执行（或先要求高精度评审）。完整执行细节见下文。

---

> TL;DR (machine): Short effort, Low risk - 7 todos（重置脚本优先 + 对局操作链路连环修复[数据解包/participant_id/WS状态/会话结束/参赛者回写] + 前端插件化 + 静态目录对齐 + admin 插件接口 + 全量回归），改动集中 MatchPlay.vue + 少量后端，pytest 全绿 + 前端 build 兜底。

## Scope
### Must have
- backend/reset_db.py：可复用数据库重置脚本（完全重置、无备份、CLI 带确认/--yes 跳过），供用户测试前一键回到干净种子数据
- 对局操作链路修复（核心，连环 bug）：前端 loadMatch 解包嵌套响应、WS state 解包 controller_state、participant_id 按替操作方推导、session_ended 保留状态以显示"记录结果"；后端 start_match 回写解析出的参赛者、end_session 广播附最终状态、路由/插件注释语义更新
- 前端 MatchPlay.vue 插件化：按 gameplay_plugin 名动态解析玩法组件（当前仅 triangle_occupy）
- 静态托管目录对齐：main.py `frontend-dist` → `frontend/dist`
- admin Plugins 管理接口：GET /api/admin/plugins 列出已注册插件，前端 Plugins.vue 改为调接口渲染
- 每个修复补回归测试（后端 pytest + 前端 build）

### Must NOT have (guardrails, anti-slop, scope boundaries)
- 不做新玩法插件（只修现有 triangle_occupy 链路）
- 重置脚本不做备份功能（用户明确"完全重置,无需备份"）；不加 --backup 选项
- 不重构赛制引擎/积分/排行榜/认证（不在 bug 范围）
- 不改 demo GameController 规则逻辑（AGENTS.md：规则零改动）
- 不改变 GameplayPlugin 契约方法签名与 get_state 返回形状（嵌套 controller_state 保持不变，前端解包）
- 不引入动态 import() 做插件化（当前单玩法，映射表足够）
- 不做玩法会话的完全 DB 化（_sessions 保留作缓存，DB 桥已就位）
- 不做前端单元测试框架（沿用 npm run build 验证）
- 不做 CI/CD、不改 .github workflows

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: tests-after（先修 bug，再补回归测试）+ pytest（后端）+ npm run build（前端 vue-tsc + vite build）
- Evidence: .omo/evidence/task-<N>-competition-web-fixes.<ext>（本项目统一 .omo/evidence/，不使用 ulw-loop）
- 每个 todo 的 Acceptance criteria 必须能通过命令行断言验证（pytest 指定文件、curl 指定端点+期望码、前端 build 退出码、grep 断言）
- QA 场景一律给出精确工具调用（pytest 指定文件、curl 指定端点、node 脚本断言），happy + failure 双路径，产出证据文件

## Execution strategy
### Parallel execution waves
> Wave 1（后端独立 + 前端核心链路，可并行）：1,2,3,5,6
> Wave 2（前端插件化，依赖 2 与 3 的字段）：4
> Wave 3（全量回归）：7

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | — | 7 | 2,3,5,6 |
| 2 | — | 4,7 | 1,3,5,6 |
| 3 | — | 4,7 | 1,2,5,6 |
| 4 | 2,3 | 7 | — |
| 5 | — | 7 | 1,2,3,6 |
| 6 | — | 7 | 1,2,3,5 |
| 7 | 1,2,3,4,5,6 | — | — |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [ ] 1. backend/reset_db.py：可复用数据库重置脚本（完全重置、无备份、CLI 带确认）
  What to do / Must NOT do: 新建 backend/reset_db.py，实现可调用函数 `reset_db(confirm: bool = True) -> dict` 与 CLI 入口。流程：①打印开发密码警告（复用 seed.py 的 _DEV_PASSWORD_WARNING 文案）+ 提示"将删除 backend/competition.db 并重建种子数据"；②`confirm=True` 时 `input()` 等待回车确认（EOFError/非交互环境自动视为确认），`--yes` 参数跳过确认；③`Base.metadata.drop_all(bind=engine)` 清表；④`engine.dispose()` 关闭全部连接；⑤解析 `settings.DB_PATH`（config.py:7，相对 backend/ 工作目录）为绝对路径，删除 `competition.db` 及 `-wal`/`-shm` 伴生文件：**用 try/except PermissionError 包裹 Path.unlink（缺失用 missing_ok=True 忽略），捕获到 PermissionError 时打印"数据库被占用，请先停止后端服务（uvicorn）后重试"并 sys.exit(1)**——WAL 模式下 PRAGMA quick_check 检测不到其他进程占用，真正的检测点是删除时的文件锁；⑥`Base.metadata.create_all(bind=engine)` 重建表；⑦调 `seed_all()`（seed.py:80）灌入种子数据；⑧打印创建摘要（复用 seed_all 返回的 summary）。CLI 用法：`cd backend && .venv\Scripts\python reset_db.py`（确认后执行）、`.venv\Scripts\python reset_db.py --yes`（跳过确认）。Must NOT: 不调用 seed.py 的 `main()`（它只 create_all+seed_all，不含 drop/删文件）；不删除了 competition.db 及伴生文件以外的任何文件；不添加备份逻辑（用户明确无需备份）；不改动 config.py/db.py/seed.py 现有代码。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 7
  References (executor has NO interview context - be exhaustive): backend/seed.py:51-59（_DEV_PASSWORD_WARNING 文案）、:80-227（seed_all 幂等实现与摘要格式）、:233-238（main()=create_all+seed_all，作为对比参考）；backend/app/config.py:6-7（DATABASE_URL/DB_PATH 默认值，相对路径语义）；backend/app/db.py:10-23（engine/SessionLocal/Base，WAL PRAGMA）；backend/tests/conftest.py:22-28（drop_all+create_all 重置标准做法）；backend/seed.py:46-49（_DEFAULT_SONG_LIB_CANDIDATES：曲库路径来自 repo 外 demo/ 或 backend/demo/，reset 后 seed 依赖它存在）
  Acceptance criteria (agent-executable): `cd backend && $env:DATABASE_URL="sqlite:///./_reset_test.db"; $env:DB_PATH="./_reset_test.db"; .venv\Scripts\python -c "import reset_db; r = reset_db(confirm=False); assert r['skipped'] is False"` 返回成功且 `_reset_test.db` 存在；再次运行同命令 `assert r['skipped'] is True`（幂等：seed_all 检测 admin 已存在跳过）；`Test-Path backend/_reset_test.db-wal` / `-shm` 为 False（伴生文件已删）；删除 `_reset_test.db*` 清理。
  QA scenarios (name the exact tool + invocation): happy — `cd backend && .venv\Scripts\python reset_db.py --yes` 在真实 competition.db 上执行，随后 `.\.venv\Scripts\python -c "from app.db import SessionLocal; from app.models.user import User; db=SessionLocal(); print(db.query(User).filter(User.username=='admin').count())"` 输出 1，证据 .omo/evidence/task-1-competition-web-fixes.txt；failure — 用另一进程保持对 competition.db 的连接不关闭（`.venv\Scripts\python -c "import sqlite3,time; c=sqlite3.connect('competition.db'); c.execute('BEGIN EXCLUSIVE'); time.sleep(30)"` 后台运行）后运行 reset_db.py，脚本打印"数据库被占用"提示且 exit 非 0，证据同上。Commit: Y | chore(db): 新增可复用数据库重置脚本 reset_db.py

- [ ] 2. 修复对局操作核心链路（连环 bug）：前端数据解包 + participant_id 推导 + WS 状态解包 + 会话结束保留状态
  What to do / Must NOT do: 前端 frontend/src/views/MatchPlay.vue 四处修改：①**loadMatch 解包**（:174-181）：`GET /api/matches/{mid}` 返回嵌套 `MatchDetailOut`（= `{match: MatchOut, session: GameSessionOut|null}`，见 matches.py:155），当前 `match.value = data` 把整个包裹对象当扁平 MatchInfo 用，导致 `match.value.participant_a/status/id` 全部 undefined；改为定义 `interface MatchDetailResp { match: MatchInfo; session: { id: number; state: Record<string, unknown> | null } | null }` 并 `match.value = data.match`。②**WS state 解包**（:145-164 onmessage）：WS 帧 `state` 是 `get_state` 的嵌套视图 `{controller_state: {board, scores, encircled, encirclement_active, l1, elapsed, time_limit, events, game_over, winner, win_type}, elapsed_minutes, sides, game_over, winner}`（见 plugin.py:185-196），而 TriangleState 期望扁平字段；解包为 `state.value = raw.controller_state ? { ...raw.controller_state, ...raw } : raw`。③**participant_id 推导**（:187-207 submitAction）：删除硬编码 `participant_id: 0`，新增 `actingSide = ref<'defender' | 'attacker'>('defender')` 与 UI 切换（el-radio-group，放在 TriangleControls 旁），发送时 `participant_id = actingSide === 'defender' ? match.value?.participant_a : match.value?.participant_b`（与 start_match 构造 sides 映射一致，match_service.py:225）；该侧 participant 为 null 时 ElMessage.warning("该侧参赛者未确定，请先开赛") 并 return。④**session_ended 保留状态**（:156-160）：不再清空 `state.value`——若帧带 `state` 用之（含 game_over=true），否则保留旧值只清 `sessionId`，保证"记录结果"按钮（v-if="isRefereeOrAdmin && state.game_over"）可见。后端 backend/app/plugins/routes.py：⑤end_session（:199-225）广播 `session_ended` 时附带最终公开视图：先 `view = plugin.get_state(session_id, session["state"])` 再 `manager.broadcast(..., {"type": "session_ended", "session_id": session_id, "state": view})`。后端 backend/app/plugins/triangle_occupy/plugin.py 与 backend/app/plugins/routes.py：⑥更新 validate_result/submit_action 相关 docstring/注释，明确 `participant_id` 语义 = "被操作的参赛单位 id（裁判替该方操作）"，sides 校验=校验该参赛单位是否为合法阵营成员，操作者身份由路由层 require_referee 保证；逻辑代码零改动。Must NOT: 不把权限校验移到插件层（身份校验留在路由层 require_referee）；不改 GameplayPlugin 方法签名；不改变 get_state 返回形状（保持嵌套，前端解包）；不删除 sides 校验（用于阵营映射）；不改 demo GameController。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 4,7
  References (executor has NO interview context - be exhaustive): frontend/src/views/MatchPlay.vue:145-172（onmessage/onclose WS 处理）、:174-181（loadMatch 现状——嵌套响应未解包，核心 bug ①）、:187-207（submitAction 硬编码 participant_id: 0，核心 bug ③）、:252-275（onRecordResult 依赖 state.value.winner/scores 与 match.value?.participant_a）；backend/app/api/matches.py:131-155（get_match_detail 返回 MatchDetailOut 嵌套结构）；backend/app/schemas/match.py:58-62（MatchDetailOut = {match, session} 确认）；backend/app/plugins/triangle_occupy/plugin.py:185-196（get_state 嵌套视图形状）、:198-220（validate_result）、:222-281（submit_result，:227 `if participant_id not in sides`、:247 `team = sides[participant_id]`）；backend/app/plugins/routes.py:167-197（submit_action，:171 require_referee 依赖）、:199-225（end_session，:221-224 session_ended 广播现状）；backend/app/services/match_service.py:222-226（start_match 构造 sides：participant_a→defender, participant_b→attacker）；backend/app/plugins/routes.py:65-97（_load_db_session 已做 sides int 键规范化）
  Acceptance criteria (agent-executable): `cd backend && .venv\Scripts\python -m pytest tests/test_plugins/test_triangle_occupy.py tests/test_matches.py -q` 全绿（新增/既有用例覆盖：referee 以 participant_a 为 participant_id 调 submit_result 成功且操作落在 defender 阵营；以 participant_b 成功且落在 attacker；以 0 或非 sides 键被拒 400）；`cd frontend && npm run build` 退出码 0（vue-tsc 严格检查，含新 MatchDetailResp 类型）；`grep -n "participant_id: 0" frontend/src/views/MatchPlay.vue` 无匹配；`grep -n "match.value = data" frontend/src/views/MatchPlay.vue` 无匹配（改为 data.match）。
  QA scenarios (name the exact tool + invocation): happy — 新增 pytest：构造 GameSession + sides={3:'defender',4:'attacker'}，referee 身份调 POST /api/gameplay/triangle_occupy/session/{id}/action 传 `{"participant_id": 3, "payload": {"action": "occupy", "cell_id": 1}}` 返回 200 且 state.controller_state.board[1].owner=='defender'；再传 participant_id=4 占领 cell 2 落在 attacker；failure — 同端点传 `{"participant_id": 0, ...}` 返回 400 detail="非法操作"；end_session 后 WS 帧（TestClient websocket_connect 断言）收到 `session_ended` 且带 `state.game_over == true`，证据 .omo/evidence/task-2-competition-web-fixes.txt。Commit: Y | fix(gameplay): 修复对局操作链路（响应解包/participant_id/WS状态/会话结束）

- [ ] 3. 后端数据回写与字段补齐：start_match 回写解析参赛者 + _match_out 补 gameplay_plugin
  What to do / Must NOT do: ①backend/app/services/match_service.py start_match（:206-216）：单败淘汰后续轮次经 `engine._resolve_participants` 解析出 participant_a/b 后，**回写到 Match 行**（`match.participant_a = participant_a; match.participant_b = participant_b`），随 :242 的 commit 一并落库——否则前端 match 接口永远读到 null，无法推导 participant_id；②backend/app/api/matches.py `_match_out`（:102-109）与 backend/app/schemas/match.py MatchOut（:27-44）：补 `gameplay_plugin: str | None = None` 字段，_match_out 中 `db.get(Competition, match.competition_id).gameplay_plugin` 填充（供前端 MatchPlay 插件化按插件名解析组件）。Must NOT: 不改 _resolve_participants 引擎方法本身；不改 MatchOut 其他字段；不回写 engine_match_id；不破坏 _replay_finished 的重放逻辑（回写仅影响 participant 展示，重放仍按 engine_match_id + result）。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 4,7
  References (executor has NO interview context - be exhaustive): backend/app/services/match_service.py:206-216（participant 解析到局部变量但未回写——核心缺口）、:232-242（GameSession 创建与 commit）；backend/app/api/matches.py:102-109（_match_out 现状：仅 model_validate + participant 名称）、:131-155（get_match_detail）；backend/app/schemas/match.py:27-44（MatchOut 字段清单，无 gameplay_plugin）；backend/app/models/match.py:39-63（Match 模型 participant_a/b 可空列）；backend/app/models/competition.py（Competition.gameplay_plugin 字段）
  Acceptance criteria (agent-executable): 新增 pytest（放 tests/test_matches.py）：构造单败淘汰比赛 + 前序对局已完赛，对后续轮次对局调 POST /api/matches/{id}/start 成功后，`db.get(Match, id).participant_a/b` 非 None 且等于引擎解析结果；`GET /api/matches/{id}` 响应 `data.match.gameplay_plugin == "triangle_occupy"`（或该比赛配置的插件名）；`cd backend && .venv\Scripts\python -m pytest tests/test_matches.py -q` 全绿。
  QA scenarios (name the exact tool + invocation): happy — pytest 断言 start 后 Match 行回写 + 详情接口带 gameplay_plugin；failure — 未开赛的后续轮次对局 GET 详情 participant_a/b 为 null（不回写场景），前端应显示"待开赛"而非报错，证据 .omo/evidence/task-3-competition-web-fixes.txt。Commit: Y | fix(matches): start_match 回写解析参赛者 + 详情补 gameplay_plugin 字段

- [ ] 4. 前端插件化：MatchPlay 按 gameplay_plugin 名动态解析玩法组件
  What to do / Must NOT do: frontend/src/views/MatchPlay.vue：①新增插件组件映射表 `const PLUGIN_COMPONENTS: Record<string, { board: Component; controls: Component | null }> = { triangle_occupy: { board: TriangleBoard, controls: TriangleControls } }`（保留静态 import TriangleBoard/TriangleControls，不做动态 import——单玩法映射表足够）；②模板改为 `<component :is="boardComp" :state="state" :selectable="..." @select="onSelectCell" />` 与 `<component :is="controlsComp" v-if="isRefereeOrAdmin && controlsComp" ... />`；③`boardComp/controlsComp` 由 `PLUGIN_COMPONENTS[match.value?.gameplay_plugin ?? '']` 计算（gameplay_plugin 来自 todo 3 补的 _match_out 字段）；④未知插件名时渲染降级提示（el-alert "该玩法暂未支持前端组件"）。Must NOT: 不引入 `defineAsyncComponent`/动态 import()（当前单玩法）；不重构 TriangleBoard/TriangleControls 内部；不改 router；不影响选手只读视图逻辑。
  Parallelization: Wave 2 | Blocked by: 2,3 | Blocks: 7
  References (executor has NO interview context - be exhaustive): frontend/src/views/MatchPlay.vue:73（当前硬编码 import）、:32-58（模板中 TriangleBoard/TriangleControls 用法）、:105（isRefereeOrAdmin）；frontend/src/plugins/triangle-occupy/index.ts（组件导出形态，TriangleBoard/TriangleControls 具名导出）；frontend/AGENTS.md TRAPS（"MatchPlay.vue 硬编码 import TriangleBoard/Controls，未按插件名动态解析组件"——本 todo 消除该反模式）；todo 3 补的 MatchOut.gameplay_plugin 字段
  Acceptance criteria (agent-executable): `cd frontend && npm run build` 退出码 0；`grep -n "<TriangleBoard\|<TriangleControls" frontend/src/views/MatchPlay.vue` 无匹配（模板不再直接用组件标签，改用 `<component :is>`）；`grep -n "PLUGIN_COMPONENTS" frontend/src/views/MatchPlay.vue` 有匹配；后端 `cd backend && .venv\Scripts\python -m pytest tests/test_matches.py -q` 全绿。
  QA scenarios (name the exact tool + invocation): happy — npm run build 成功 + 对局页渲染棋盘；failure — 把比赛 gameplay_plugin 临时改为不存在的名字 "ghost_plugin"，对局页显示降级提示（el-alert 文案"该玩法暂未支持前端组件"）而非白屏（Playwright 或手动冒烟断言），改回后恢复，证据 .omo/evidence/task-4-competition-web-fixes.txt。Commit: Y | refactor(frontend): MatchPlay 按插件名动态解析玩法组件

- [ ] 5. 静态托管目录对齐：main.py frontend-dist → frontend/dist
  What to do / Must NOT do: backend/app/main.py:108 将 `_frontend_dist` 的路径从 `"frontend-dist"` 改为 `"frontend"` 子目录下的 `"dist"`（即 `os.path.join(..., "frontend", "dist")`，与 frontend/README、根 README、Vite 默认构建产物一致）。Must NOT: 不创建 frontend-dist 目录；不改前端构建输出目录配置（保持 Vite 默认 dist）；不改其他静态相关逻辑。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 7
  References (executor has NO interview context - be exhaustive): backend/app/main.py:106-110（_frontend_dist 拼接与挂载条件：`os.path.isdir` 才挂载）；frontend/vite.config.ts（构建输出目录，确认默认 dist）；根 README.md 部署章节（frontend/dist 表述）；frontend/AGENTS.md TRAPS（"生产由后端托管 frontend-dist/（与 README 的 frontend/dist 需对齐"））
  Acceptance criteria (agent-executable): `cd frontend && npm run build`（产物生成 frontend/dist/index.html）；`cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000` 启动后 `curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/` 返回 200 且 `curl -s http://127.0.0.1:8000/ | Select-String "index"` 命中 HTML；启动后 `Test-Path backend/frontend-dist` 为 False（不再查找旧目录）。
  QA scenarios (name the exact tool + invocation): happy — 上述 curl 200 + HTML 命中；failure — 临时把 frontend/dist 改名 frontend/dist.bak 后重启 uvicorn，curl 根路径返回 404（静态未挂载时的行为），改回后恢复，证据 .omo/evidence/task-5-competition-web-fixes.txt。Commit: Y | fix(deploy): 统一静态托管目录为 frontend/dist

- [ ] 6. 内存 _sessions 注释收敛 + admin 玩法插件列表接口
  What to do / Must NOT do: 后端 backend/app/plugins/routes.py：①更新模块 docstring（:13-14）与 `_sessions` 定义注释（:35-37），从"todo 14 换 DB 持久化"改为"GameSession DB 桥已实现（_load_db_session 回退装载 + _persist_session 回写），_sessions 仅作进程内缓存加速"；②新增 GET /api/admin/plugins 端点：**追加到现有 admin 路由模块 backend/app/api/admin_users.py（避免新建文件后遗漏 main.py 的 include_router 注册）**，require_admin 依赖，返回 `[{"name": p.name, "version": p.version} for p in registry.all()]`（registry 为 `app.plugins.registry.registry` 单例，all() 方法已存在，registry.py:58）。前端 frontend/src/views/admin/Plugins.vue：改为 onMounted 调 GET /api/admin/plugins 渲染列表（当前为静态硬编码 triangle_occupy 展示）。Must NOT: 不删除 _sessions/内存缓存层（插件直建路径与测试依赖）；不改 registry.py 的 PluginRegistry 接口；不给该端点加业务逻辑（仅列表）；不新建 api/admin_plugins.py（除非同时在 main.py 注册 include_router——推荐直接追加到 admin_users.py 避免遗漏）。
  Parallelization: Wave 1 | Blocked by: — | Blocks: 7
  References (executor has NO interview context - be exhaustive): backend/app/plugins/routes.py:13-14（模块 docstring 的 todo 14 表述）、:35-38（_sessions 定义与注释）、:65-97（_load_db_session DB 桥）、:110-129（_persist_session）；backend/app/plugins/registry.py:58-60（registry.all() 存在）；backend/app/api/admin_users.py（admin 路由模块模式参考：require_admin 依赖、_request_meta、审计）；frontend/src/views/admin/Plugins.vue（当前静态展示）；frontend/views/AGENTS.md（"admin/Plugins.vue 仅静态展示内置 triangle_occupy，无管理接口"——本 todo 消除）
  Acceptance criteria (agent-executable): `cd backend && .venv\Scripts\python -m pytest tests/test_plugins/test_registry.py -q` 全绿；新增 pytest：admin 调 GET /api/admin/plugins 返回 200 且 body 含 `{"name": "triangle_occupy"}`；player 调同端点 403；`cd frontend && npm run build` 退出码 0。
  QA scenarios (name the exact tool + invocation): happy — admin 登录 curl `-b cookies.txt http://127.0.0.1:8000/api/admin/plugins` 返回 200 JSON 含 triangle_occupy；failure — player 登录 curl 同端点返回 403，证据 .omo/evidence/task-6-competition-web-fixes.txt。Commit: Y | feat(admin): 玩法插件列表接口 + 内存会话注释收敛

- [ ] 7. 全量回归验证（后端 pytest 全绿 + 前端 build + 核心链路冒烟）
  What to do / Must NOT do: ①`cd backend && .venv\Scripts\python -m pytest tests -q` 全量跑（252 个既有 + 本计划新增），0 failed；②`cd frontend && npm run build` 退出码 0；③核心链路冒烟（**必须走前端 UI 路径而非仅 curl**）：`cd backend && .venv\Scripts\python reset_db.py --yes`（验证 todo 1）→ 启动 uvicorn + 前端 dev → admin/referee 登录 → 打开演示赛对局页 → 断言：状态标签显示正确（非"未开始"兜底）、双方昵称显示（非"选手A/选手B"兜底）、棋盘渲染非空白（有 21+ 格）、referee 选格点"占领"成功且棋盘更新、结束对局后"记录结果"按钮可见、点击后结果落库；④产出验收记录 .omo/evidence/task-7-competition-web-fixes.md 逐项 ✓/✗（含截图）。Must NOT: 不修复本次回归中新发现的非计划内问题（记录到验收记录"遗留问题"区，由用户决定是否进下一轮计划）；不跳过任何验收项；冒烟不得用 curl 代替前端 UI 路径（核心 bug 本就是前端数据解包问题）。
  Parallelization: Wave 3 | Blocked by: 1,2,3,4,5,6 | Blocks: —
  References (executor has NO interview context - be exhaustive): backend/tests/AGENTS.md（三层隔离机制，252 个测试）；frontend/AGENTS.md（无单测，质量保障=npm run build）；.omo/plans/competition-web.md todo 25（M10 联调验收先例与记录格式）；backend/README.md（默认账号 admin/admin123、referee/referee123、player1-8/player123 供冒烟登录）；frontend/src/views/MatchPlay.vue（冒烟断言点：状态标签/昵称/棋盘格/记录按钮）
  Acceptance criteria (agent-executable): `cd backend && .venv\Scripts\python -m pytest tests -q` 输出 "N passed" 且 0 failed；`cd frontend && npm run build` 退出码 0；验收记录文件全部 ✓（含对局页 UI 冒烟断言项）。
  QA scenarios (name the exact tool + invocation): happy — 全量 pytest 0 failed + 对局页 UI 冒烟全 ✓；failure — 任一验收项 ✗ 则记录原因并回修对应 todo 后重验，证据 .omo/evidence/task-7-competition-web-fixes.md。Commit: Y | test: 全量回归与对局链路验收通过

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit
- [ ] F2. Code quality review
- [ ] F3. Real manual QA
- [ ] F4. Scope fidelity

## Commit strategy
- Conventional Commits：`fix(gameplay):` 对局操作链路、`fix(matches):` 参赛者回写与字段补齐、`fix(deploy):` 静态托管、`feat(admin):` 插件接口、`refactor(frontend):` 插件化、`chore(db):` 重置脚本、`test:` 回归
- 单 commit 只做一件事；不混合无关改动
- 禁止提交 `.env`、`*.db`、`node_modules/`、`.venv/`（.gitignore 已含）
- 每个 todo 完成即 commit；全部完成后可打 tag `v0.5`（修复里程碑）

## Success criteria
- `cd backend && .venv\Scripts\python reset_db.py --yes` 一键回到干净种子数据（admin/referee/player1-8 + 2 队 + 演示赛），重复运行幂等；后端运行中执行时给出友好占用提示
- 对局操作链路 UI 全通：referee/admin 在对局页看到正确状态标签与双方昵称（非兜底文案）、棋盘渲染 21+ 格非空白、选格"占领"成功且棋盘实时更新、结束对局后"记录结果"按钮可见、点击后结果落库；选手无操作按钮且直接调 API 被 403/400 拒
- 单败淘汰后续轮次：开赛后前端能读到已解析的参赛者并正常操作
- `cd backend && .venv\Scripts\python -m pytest tests -q` 全部通过（0 failed）
- `cd frontend && npm run build` 构建成功
- 静态托管：前端构建产物放 frontend/dist 后，后端单端口 8000 直接托管网站首页
- admin 后台玩法模板页从静态展示变为调 GET /api/admin/plugins 动态渲染
- MatchPlay.vue 不再硬编码 participant_id=0、不再把嵌套响应整体赋值给 match、不再直接用 TriangleBoard/TriangleControls 组件标签（映射表驱动）
