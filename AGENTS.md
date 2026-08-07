# ROOT KNOWLEDGE BASE — 萌新杯音游比赛网站

**Scope:** 仓库根级导航 + 已验证的当前状态。分层细节见各子目录 AGENTS.md（下面 NAVIGATION）。旧的根级知识库在 `docs/archive/AGENTS.md`（已归档，多处过时，勿引用）。

## OVERVIEW
音游社区比赛运营平台：FastAPI + SQLAlchemy/SQLite + Vue3 单体架构，单进程单端口（后端托管前端产物）。Windows 优先的开发环境（`.venv\Scripts\python.exe`、`start.ps1`）。无 CI、无 alembic、前端无单测。

## COMMANDS（精确命令）
```powershell
# 一键启动（Windows；双击 启动服务.bat 等价）——自动建 venv/装依赖/seed/双窗口/开浏览器；
# 启动前检测 8000/5173 端口占用，已占用则跳过对应服务（防双进程，issue 2）
powershell -ExecutionPolicy Bypass -File start.ps1

# 后端全部测试（工作目录 backend；当前约 230 个）
cd backend; .\.venv\Scripts\python.exe -m pytest tests -q

# 单个测试文件
.\.venv\Scripts\python.exe -m pytest tests\test_ws.py -q

# 前端唯一质量检查（vue-tsc -b && vite build；无单元测试；strictPort 5173）
cd frontend; npm run build

# 后端单独启动（backend/ 下）
.\.venv\Scripts\python.exe seed.py   # 幂等种子数据（演示赛为瑞士轮）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 完全重置数据库（先停 uvicorn：WAL 文件锁会触发 PermissionError）
.\.venv\Scripts\python.exe reset_db.py --yes
```

## NAVIGATION（各层 AGENTS.md 是真正的细节来源）
| 任务 | 位置 |
|------|------|
| 路由/端点权限/审计/限流 | `backend/app/api/AGENTS.md` |
| 安全栈（JWT/RBAC/CSRF/限流/锁定/WS） | `backend/app/core/AGENTS.md` |
| 对局编排（排表/开赛/记分/瑞士轮推进） | `backend/app/services/AGENTS.md` |
| 两赛制引擎（swiss/single_elim，纯逻辑） | `backend/app/tournaments/AGENTS.md` |
| 测试隔离机制（三层） | `backend/tests/AGENTS.md` |
| 前端（全局 + 页面职责） | `frontend/AGENTS.md` + `frontend/src/views/AGENTS.md` |
| 部署（Docker/systemd 两方案） | `docs/部署手册.md` |

## CURRENT STATE（以代码为准，下面几点已与 README/子文档冲突）
- **玩法插件系统已整体删除**（issue 5/16）：`backend/app/plugins/`、`/api/admin/plugins`、前端玩法模板页、GameSession 模型、`docs/玩法模板开发规范.md` 全部移除；对局由裁判手工管理，demo 玩法日志经 `/api/matches/{id}/gameplay-log` 导入判定展示。
- **积分纯手动**：进 finished 不自动结算，`settle_competition_points` 已整体删除（issue 6 用户确认）；积分唯一来源 = admin 手动发放（`POST /api/admin/points`，kind=activity/manual）。
- **赛制只剩两种**（issue 7）：swiss + single_elim；round_robin 引擎/测试/选项已删。瑞士轮默认轮数 = `ceil(log2 n)+1`（无 7 轮上限，随参赛人数动态调整），排名展示 胜/负/平（StandingRow.wins/losses/draws/points，issue 9/11）。
- **无 alembic**：schema 演进必须在 main.py `_ensure_schema_upgrades()`（PRAGMA 检测 + ALTER 补列/DROP COLUMN）追加；当前补 `users.nickname`、`matches.gameplay_log`、`matches.result_locked`（issue 14），并 DROP `competitions.gameplay_plugin/points_rule/song_lib`。
- **对局结果锁定**（issue 14）：`POST /result` 带 `lock:true` 保存并锁定，`result_locked` 后任何再记分 400；前端判定流程 = 导入日志 → 自动判定 → 人工微调 → 保存结果。
- **删除规则**：比赛任意状态可删（issue 1，级联清理）；选手随时可删（issue 3，未完结对局判对手获胜 0:0）；`/status` 加 `force:true` 强制结束（issue 8，未完成对局作废 abandoned 不参与排名）。
- **阵营约定（用户确认）**：守护者=defender=蓝方=participant_b，掠夺者=attacker=红方=participant_a；页面统一标注「掠夺者/守护者」。
- **静态托管目录是 `frontend/dist`**（main.py:121），不是 `frontend-dist`；仅目录存在时挂载，`app.frontend("/")` 支持 SPA 深链回退 index.html。
- 未知 `/api/*` → lifespan 尾部追加的 JSON 404 兜底（先 `_drop_tail_routes` 再 include，保证排在全部真实路由之后）。
- 中间件顺序（后 add 者在外层）：CORS → CSRF → SlowAPI（main.py:89 注释）。
- 认证：JWT 存 httpOnly cookie `token`；**角色以 DB 为准，不信任 JWT 声明**。

## CONVENTIONS / TRAPS
- 注释编号体系：`todo N`（功能归属）、`Metis C/E/V{n}`（需求/验收约束），改动时保持引用可追溯。
- 后端 docstring/HTTP error `detail` 统一中文；requirements.txt 未锁版本；Python 3.14（或 3.12+）。
- 前端禁止 `as any` / `@ts-ignore`；tsconfig 严格（noUnusedLocals 等）；`npm run build` 即类型检查。
- 测试永不碰 `backend/competition.db`：conftest 在 import app 前把 `DATABASE_URL` 指到按 PID 命名的临时库，autouse fixture 每测试重置 limiter/lockout 内存态。
- 数据库：`backend/competition.db`（SQLite WAL；备份须连同 `-wal`/`-shm`），`DATABASE_URL` 可覆盖。
- 种子账号（仅开发）：admin/admin123、referee/referee123、player1-8/player123；部署前必须改。
- Vite dev 代理 `/api` 与 `/ws` → `http://127.0.0.1:8000`（仅 dev；生产由后端托管 `frontend/dist`）。
- 分支：main（稳定）+ dev + feature/*；里程碑 tag v0.x。
