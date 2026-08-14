# TESTS — pytest 测试套件

## OVERVIEW
后端 pytest 241 个测试全绿（数量随用例增减浮动，以 `pytest tests -q` 实际输出为准）；前端**无**测试（靠 vue-tsc + build）。conftest 三层隔离保证测试互不污染、不碰真实开发库。

## ISOLATION（三层机制，重点）
1. **进程级**：conftest 在导入任何 app 模块**之前**把 `DATABASE_URL` 指向 `tempfile` 下 `competition_test_{PID}.db`（文件名含 PID，并发 pytest 进程互不干扰），并设 `DB_PATH`。测试永不触碰 `backend/competition.db`。
2. **用例级**：`client` fixture 每测试 `drop_all + create_all` 重建表，再 `with TestClient(app)` 触发 lifespan（建表/迁移）。
3. **autouse `_reset_traffic_state`**：每测试 `limiter.reset()` + `reset_lockout_all()` 清内存态，防限流/锁定计数跨测试泄漏（如某测试的登录尝试锁死用户名或耗尽 10/min 预算）。

`admin_client`：独立 TestClient（独立 cookie jar，不与 `client` 的选手 cookie 冲突）+ 直写 DB 翻 `role="admin"`；两 client 共享同一模块级 engine / 临时库文件。

## SUBDIRS
- `test_tournaments/`：两引擎（swiss / single_elim）纯算法测试，**无 DB**。round_robin 引擎与其测试已随 issue 7 删除。

## DATA-SEEDING PATTERNS
- **混合模式**：用户注册/报名走 API（`client` 自动登录）；审批/角色翻转**直插 DB**（`SessionLocal` 直写 `status="approved"` / `role`）。
- `_seed_players_and_approve` 在 `test_matches` / `test_points` / `test_rankings` / `test_ws` 重复定义，**未共享到 conftest**（已知重复，勿误以为缺失而重构）。
- **打完全部对局**：`_play_all_matches` 是循环实现（拉到无未完成对局为止）——瑞士轮逐轮物化（打完一轮后调用 `/rounds/{id}/complete`「开始下一轮」），单败后续轮次 start 后需重新 GET 详情取解析出的 participant_a 再提交 result。
- 私有 helper 一律 `_` 前缀。

## KEY AREAS（本轮新增/改动）
- `test_competitions.py`：任意状态可删（issue 1）、force-finish 作废对局（issue 8）、无 points_rule/gameplay_plugin/song_lib 字段。
- `test_matches.py`：`result_locked` 锁定后再记分 400（issue 14）；`randomize-sides` 随机选边（issue 2，含 403/400 边界、轮空对局拒绝、顺序可交换性）。
- `test_announcements.py`：公告发布/列表/详情/附件下载/删除（上传目录 monkeypatch 到 tmp_path，issue 4）。
- `test_gameplay_log.py`：demo 真实导出格式判定（「游戏结束 - 防守方获胜 (防85 : 攻72)」system 事件 + 顶端直胜 victory 事件；**兼容改名前的旧格式「守护者/掠夺者」**；防守方=participant_b，攻击方=participant_a）。
- `test_admin_users_crud.py`：删除未完结对局选手 → 对手获胜（issue 3）；无封禁 status 选项（issue 4）。
- `test_rankings.py` / `test_swiss.py`：standings 含 wins/losses/draws/points（issue 9/11）；swiss 默认轮数 `ceil(log2 n)+1`。
- `test_points.py`：积分纯手动（结算已删除，issue 6）。

## RUN
```bash
cd backend && .venv\Scripts\python -m pytest tests -q
```
