# TESTS — pytest 测试套件

## OVERVIEW
后端 pytest 252 个测试全绿；前端**无**测试（靠 vue-tsc + build）。conftest 三层隔离保证测试互不污染、不碰真实开发库。

## ISOLATION（三层机制，重点）
1. **进程级**：conftest 在导入任何 app 模块**之前**把 `DATABASE_URL` 指向 `tempfile` 下 `competition_test_{PID}.db`（文件名含 PID，并发 pytest 进程互不干扰），并设 `DB_PATH`。测试永不触碰 `backend/competition.db`。
2. **用例级**：`client` fixture 每测试 `drop_all + create_all` 重建表，再 `with TestClient(app)` 触发 lifespan（建表/迁移/插件注册）。
3. **autouse `_reset_traffic_state`**：每测试 `limiter.reset()` + `reset_lockout_all()` 清内存态，防限流/锁定计数跨测试泄漏（如某测试的登录尝试锁死用户名或耗尽 10/min 预算）。

`admin_client`：独立 TestClient（独立 cookie jar，不与 `client` 的选手 cookie 冲突）+ 直写 DB 翻 `role="admin"`；两 client 共享同一模块级 engine / 临时库文件。

## SUBDIRS
- `test_tournaments/`：三引擎（round_robin / swiss / single_elim）纯算法测试，**无 DB**。
- `test_plugins/`：registry / 内置玩法（triangle_occupy）/ `fixtures/fake_plugin/`（fake 插件 fixture）。

## DATA-SEEDING PATTERNS
- **混合模式**：用户注册/报名走 API（`client` 自动登录）；审批/角色翻转**直插 DB**（`SessionLocal` 直写 `status="approved"` / `role`）。
- `_seed_players_and_approve` 在 `test_matches` / `test_points` / `test_rankings` / `test_ws` 重复定义，**未共享到 conftest**（已知重复，勿误以为缺失而重构）。
- 私有 helper 一律 `_` 前缀。

## RUN
```bash
cd backend && .venv\Scripts\python -m pytest tests -q
```
