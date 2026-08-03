---
slug: competition-web-fixes
status: reviewed
intent: unclear
review_required: true
plan_path: .omo/plans/competition-web-fixes.md
plan_sha256: null
review_round_id: round-1
pending-action: handoff to user for $start-work
review:
  momus:
    status: done
    result: APPROVE-with-changes - 确认 registry.all()/config.py/main.py:108 等引用属实；发现 ① MatchPlay 把嵌套 MatchDetailOut 整体赋给 match（participant_id 推导前提失效）② 单败淘汰后续轮次 start_match 未回写解析参赛者 ③ 新 admin 路由文件需在 main.py 注册（改为追加到 admin_users.py）④ reset_db 锁检测（PRAGMA quick_check）在 WAL 下无效、Windows 删文件 PermissionError 未处理
  independent:
    status: done
    result: REQUEST CHANGES - ①【CRITICAL】WS state 为 get_state 嵌套视图（controller_state 内含 board/scores），TriangleState 期望扁平字段 → 前端棋盘渲染空白，onRecordResult 读 state.value.scores 崩 ②【CRITICAL】session_ended 后前端清空 state → "记录结果"按钮消失，链路断在最后一步 ③【MAJOR】match.value=嵌套响应导致 participant_a/b 全 undefined ④【MAJOR】reset_db 锁检测机制无效 ⑤【MINOR】admin_plugins 新文件需 main.py 注册
plan_fixes_applied: "todo2 扩展为对局操作链路连环修复（loadMatch 解包+WS state 解包+participant_id 推导+session_ended 保留状态+end_session 广播附 state）；新增 todo3（start_match 回写解析参赛者+_match_out 补 gameplay_plugin）；todo4 前端插件化依赖 2,3；todo1 锁检测改 PermissionError 捕获；todo6 明确追加到 admin_users.py 避免 main.py 注册遗漏；todo7 冒烟必须走前端 UI 路径"
review:
  momus:
    status: pending
    workspace_root: null
    runtime_home: null
    target: .omo/plans/competition-web-fixes.md
    round_id: null
    plan_sha256: null
    launch_id: null
    session: null
    result: null
  independent:
    status: pending
    workspace_root: null
    runtime_home: null
    target: .omo/plans/competition-web-fixes.md
    round_id: null
    plan_sha256: null
    session: null
    result: null
approach: "todo1=可复用数据库重置脚本(reset_db.py,完全重置无备份); todo2=修复玩法操作 participant_id 硬编码0+插件层裁判身份校验矛盾(核心bug,操作跑不通根因); todo3=前端插件化动态解析; todo4=静态托管目录对齐(frontend-dist vs frontend/dist); todo5=内存_sessions反模式清理+admin Plugins接口。重置脚本优先,bug修复按依赖序。"
---

# Draft: competition-web-fixes

## Components (topology ledger)
| id | outcome | status | evidence |
|----|---------|--------|----------|
| C1 | 可复用 reset_db.py:删库→create_all→seed,用户测试前一键重置 | active | backend/seed.py:80,233; backend/app/main.py:39,55; backend/app/db.py:10,23 |
| C2 | 玩法操作链路打通:前端传正确 participant_id + 插件层裁判身份放行 | active | frontend/src/views/MatchPlay.vue:200; backend/app/plugins/triangle_occupy/plugin.py:205,227; backend/app/plugins/routes.py:167 |
| C3 | 前端插件化:MatchPlay 按 gameplay_plugin 名动态解析组件 | active | frontend/src/views/MatchPlay.vue:73; frontend/AGENTS.md TRAPS |
| C4 | 静态托管目录对齐:main.py 与 README 统一为 frontend/dist | active | backend/app/main.py:108; README.md |
| C5 | 内存 _sessions 反模式收敛 + admin Plugins 管理接口 | active | backend/app/plugins/routes.py:38; frontend/src/views/admin/Plugins.vue |

## Open assumptions (announced defaults)
| assumption | adopted default | rationale | reversible? |
|------------|-----------------|-----------|-------------|
| 重置脚本是否备份 | 完全重置,无备份 | 用户明确选择"完全重置,无需备份"(2026-08-03) | 是(脚本可加 --backup 选项) |
| 重置脚本形态 | 独立 Python 脚本 backend/reset_db.py | 与 seed.py 同级,复用 Base/engine/seed_all,CLI 可重复运行 | 是 |
| 重置脚本是否检测服务运行 | 检测并警告(SQLite 文件锁),不强制阻止 | Windows 下无法可靠 kill 进程,警告+让用户确认 | 是 |
| 玩法操作 participant_id 修复方向 | 前端从 match.participant_a/b + 选中阵营推导;后端插件层对 referee/admin 放行身份校验 | 权限模型已是"裁判操作棋盘",插件层 sides 校验与权限模型矛盾;裁判替双方操作 | 是(保留 sides 用于阵营映射) |
| 前端插件化方案 | 用动态组件 <component :is> + 插件名→组件映射表 | 当前只有 triangle_occupy 一个玩法,映射表足够;不引入动态 import 复杂度 | 是 |
| 静态托管目录统一方向 | 统一为 frontend/dist(npm run build 默认产物路径) | README 与 Vite 默认都是 dist;改 main.py 一处 | 是 |
| 内存 _sessions 处理 | 保留作为缓存(DB 桥已实现 _load_db_session),清理注释+补 admin Plugins 列表接口 | 完全移除内存层会破坏插件直建路径(测试用);DB 桥已就位 | 是 |
| bug 修复是否补测试 | 是,每个 bug 修复补回归测试(pytest 后端 + 前端 build) | AGENTS.md 要求 TDD/测试后;防止回归 | 是 |

## Findings (cited - path:lines)
1. **核心 bug(操作跑不通根因)**: `frontend/src/views/MatchPlay.vue:200` 硬编码 `participant_id: 0`;后端 `backend/app/plugins/triangle_occupy/plugin.py:205` `validate_result` 检查 `participant_id not in state["sides"]`,sides 键是真实参赛者 id(如 3,4)→ **所有棋盘操作 100% 被 validate_result 拒绝返回 "非法操作"**。
2. **深层设计矛盾**: 权限模型已改为"裁判操作棋盘"(routes.py:171 `require_referee`),但插件层 plugin.py:205,227 仍要求 `participant_id in sides`(裁判 user_id 不在 sides)→ 即使前端传裁判真实 id 也会被拒。裁判替双方操作的设计与插件层身份校验冲突。
3. **前端插件化半成品**: `MatchPlay.vue:73` 硬编码 `import { TriangleBoard, TriangleControls } from '../plugins/triangle-occupy'`,未按 gameplay_plugin 名动态解析(frontend/AGENTS.md TRAPS 明确标注)。
4. **静态托管目录不一致**: `main.py:108` 找 `frontend-dist/`,README 写 `frontend/dist`→ 构建产物放 dist 但后端找不到,静态托管失效(AGENTS.md NOTES)。
5. **内存 _sessions 反模式**: `plugins/routes.py:38` `_sessions` 内存 dict 重启丢失;已有 `_load_db_session` DB 桥(routes.py:65)作为回退,但注释仍标 "todo 14 换 DB"(AGENTS.md ANTI-PATTERNS)。
6. **admin Plugins.vue 静态展示**: `frontend/src/views/admin/Plugins.vue` 仅静态展示 triangle_occupy,无后端管理接口(views/AGENTS.md)。
7. **数据库机制(重置脚本依据)**: config.py:6 `DATABASE_URL=sqlite:///./competition.db`(相对 backend/ 工作目录);main.py:58 `Base.metadata.create_all` 建表;seed.py:80 `seed_all()` 幂等(admin 存在即跳过);seed.py:233 `main()`=建表+seed;conftest.py:26 测试用 `drop_all+create_all` 重建(重置标准做法)。
8. **当前库文件**: `backend/competition.db` 存在,无 -wal/-shm(无进程持有或已 checkpoint)。

## Decisions (with rationale)
1. **重置脚本 = backend/reset_db.py,完全重置无备份**: 用户明确选择。脚本流程:检测文件锁→drop_all→删 db 文件(含 -wal/-shm)→create_all→seed_all。复用 seed.py 的 main() 逻辑但加 drop+删文件步骤。CLI: `python reset_db.py`,带 `--yes` 跳过确认。
2. **玩法操作修复 = 双端协同**: 前端 MatchPlay 从 match.participant_a/b + UI 选中阵营(defender/attacker)推导 participant_id 传给后端;后端插件层 validate_result/submit_result 对 referee/admin 放行 sides 身份校验(裁判全权替双方操作,符合 2026-08-02 确认的权限模型)。保留 sides 用于阵营映射(occupy 时 team=sides[participant_id])。
3. **前端插件化 = 动态组件 + 映射表**: MatchPlay 用 `<component :is="boardComp">` / `<component :is="controlsComp">`,维护 `pluginName → { board, controls }` 映射表(当前仅 triangle_occupy)。从 match/competition 的 gameplay_plugin 字段取插件名。
4. **静态目录统一为 frontend/dist**: 改 main.py:108 `frontend-dist` → `frontend/dist`(与 README、Vite 默认一致)。
5. **_sessions 保留为缓存 + 补 admin Plugins 接口**: DB 桥已就位,_sessions 作缓存合理;清理过时注释。补 GET /api/admin/plugins 列出 registry 已注册插件(供 Plugins.vue 调用)。
6. **每个 bug 修复补回归测试**: 后端 pytest(玩法操作身份放行、静态目录、plugins 接口)+ 前端 npm run build。

## Scope IN
- backend/reset_db.py:可复用数据库重置脚本(完全重置,无备份,CLI 带确认)
- 修复玩法操作 participant_id 硬编码 + 插件层裁判身份放行(核心 bug)
- 前端 MatchPlay 插件化动态解析组件
- 静态托管目录统一(frontend-dist → frontend/dist)
- 内存 _sessions 注释清理 + admin Plugins 列表接口
- 每项修复补回归测试

## Scope OUT (Must NOT have)
- 不做新玩法插件(只修现有 triangle_occupy 链路)
- 不做重置脚本的备份功能(用户明确无需备份)
- 不重构赛制引擎/积分/排行(不在 bug 范围)
- 不做 CI/CD(单人项目)
- 不做前端单元测试框架(沿用 npm run build 验证)
- 不改 demo GameController 规则逻辑(AGENTS.md:规则零改动)
- 不做玩法会话的完全 DB 化(保留 _sessions 缓存层)

## Open questions
无(用户已确认:重置脚本优先、完全重置无备份、bug 范围由我基于代码审查确定)。

## Approval gate
status: awaiting-approval
approach: 见上方 approach 字段。
next-action: 用户批准后,运行 scaffold 脚本(无 --draft-only)生成 .omo/plans/competition-web-fixes.md,然后 APPEND 完整 todo 批次(重置脚本 todo1 + bug 修复 todo2-6 + 最终验证波),再运行 momus + Oracle 高精度评审。
