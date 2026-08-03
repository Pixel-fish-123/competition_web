# PROJECT KNOWLEDGE BASE

**Generated:** 2026-08-03
**Commit:** 1fb54a9
**Branch:** main

## OVERVIEW
音游比赛运营平台（萌新杯）：FastAPI + Vue3 + SQLite 单进程单体，单端口跑通全站（后端可托管前端产物）。玩法模板插件化，内置 demo「三角占领」。已确认权限模型：对局中仅 referee/admin 可操作棋盘，选手只读。

## STRUCTURE
```
competition_web/
├── start.ps1 / 启动服务.bat   # 一键启动（自动装环境 + 双服务 + 自动开浏览器）
├── backend/                   # FastAPI 后端
│   ├── app/main.py            # 入口：lifespan（建表/迁移/插件注册）+ 中间件栈 + 路由挂载
│   ├── app/{api,core,models,schemas,services,tournaments,plugins}/
│   ├── tests/                 # pytest 252 个，conftest 三层隔离
│   └── seed.py                # 幂等种子数据（admin/admin123 等）
├── frontend/                  # Vue3 前端（无单元测试，靠 vue-tsc + build）
│   └── src/{views(含admin),plugins/triangle-occupy,stores,api,router,components}/
└── .omo/                      # 编排工作区（plans/evidence/boulder，gitignore）
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

## CODE MAP
| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| app | FastAPI | main.py | — | 入口；lifespan 建表+迁移+插件注册 |
| get_current_user / require_admin / require_referee | Dep | core/rbac.py | 9+ | JWT cookie→DB 用户；role 以 DB 为准（不信任 JWT 声明） |
| limiter | obj | core/ratelimit.py | 全局 | slowapi 默认 100/min；auth 10/min；admin 60/min |
| manager | obj | core/ws_manager.py | 3 | match_id 订阅广播；队列 put_nowait 跨线程 |
| TournamentEngine | ABC | tournaments/base.py | 1 | 引擎统一接口（schedule/record_result/standings） |
| RoundRobin/Swiss/SingleElimEngine | cls | tournaments/*.py | 18/13/15 | 三种赛制，纯逻辑无 DB/IO |
| match_service | mod | services/match_service.py | 4 | 排表/开赛/记分；重建+回放引擎 |
| points_service | mod | services/points_service.py | 3 | 积分幂等结算/排行榜 |
| registry / GameplayPlugin | obj/cls | plugins/registry.py, base.py | 多 | 插件发现注册；契约强制校验 |
| http(axios) / useAuthStore | mod/store | frontend/src/api, stores | 多 | baseURL /api；401/403/429 拦截 |

依赖流向（后端）：`api/* → core/* + models + schemas → services/* → tournaments/* + plugins/registry → core/ws_manager`。
前端：`views/* → api/http → Vite proxy(:8000)`；MatchPlay → `new WebSocket(/ws/...)`。

## CONVENTIONS
- **编号引用体系**：注释标注 `todo N`（功能归属）与 `Metis C/E/V{n}`（需求/验收约束），改动时保持引用可追溯。
- 后端 docstring/注释以中文为主；HTTP error `detail` 统一中文。
- requirements.txt 未锁版本；**无 alembic** —— schema 演进用 main.py `_ensure_schema_upgrades()` 幂等补列（PRAGMA 检测 + ALTER）。
- 前端 tsconfig 严格 lint（noUnusedLocals/noUnusedParameters 等）；vite 代理 /api 与 /ws → :8000。
- 插件契约：继承 GameplayPlugin、manifest 非空 name/version、暴露 `plugin` 实例、不持全局状态。
- 参赛单位模型：个体 = 1 人队伍；participant id 升序保证引擎重建确定性。

## ANTI-PATTERNS (THIS PROJECT)
- **Metis E13**：ws_manager 只做连接登记与推送，禁止在其中做任何鉴权。
- **Metis E7**：插件 create_session 只做值域校验，禁止校验「得分真实性」。
- 前端禁止 `as any` / `@ts-ignore`——类型错误必须真修。
- `plugins/routes.py` 内存 `_sessions` 是临时反模式（重启丢失）；会话读写应走 GameSession DB。
- `points_service` 复用 `match_service` 的私有 `_` 助手（`_approved_participant_ids` 等），重构勿破坏其签名。

## UNIQUE STYLES
- **引擎确定性恢复**：开赛/记分按「已批准报名 + 已完结对局」重建引擎并回放结果（单败淘汰后续轮次靠它解析参赛者）。
- 报名状态机：`pending → approved/rejected`（admin 审批端点）；赛程只认 approved。
- WS 广播：同步线程 put_nowait 入队 → 事件循环发送任务出队；满队列断开慢消费者。
- 积分幂等结算：防重复发放；队伍获奖成员各得全额。
- 比赛状态机：`draft → registration → ongoing → finished`（cancelled 特殊）；进 ongoing 自动排表。
- 一键启动：start.ps1（建 venv/装依赖/seed/双窗口/开浏览器）。

## COMMANDS
```bash
# 一键启动（Windows 双击 启动服务.bat）
powershell -ExecutionPolicy Bypass -File start.ps1

# 后端测试（252 个）
cd backend && .venv\Scripts\python -m pytest tests -q

# 前端校验（vue-tsc + build，无单测）
cd frontend && npm run build

# 后端单独启动
cd backend && .venv\Scripts\python seed.py && .venv\Scripts\python -m uvicorn app.main:app --port 8000
```

## NOTES
- 数据库：`backend/competition.db`（SQLite WAL；备份连同 -wal/-shm 一起拷）；可用 DATABASE_URL 环境变量覆盖。
- 默认账号（开发）：admin/admin123、referee/referee123、player1-8/player123；**部署上线前必须改**。
- 静态托管：main.py 找 `frontend-dist/`（README 写 frontend/dist，二者需对齐）；目录不存在则不挂载。
- 前端插件化是半成品：MatchPlay.vue 硬编码 import TriangleBoard/Controls，未按插件名动态解析组件。
- 里程碑 tag v0.0-v0.4 对应 M0-M10；M11 部署（Docker/部署手册）待用户验收后执行。
