# PLUGINS — 玩法插件系统 + triangle_occupy

## OVERVIEW
玩法模板插件化：`GameplayPlugin` 契约 + registry 自动发现注册 + 动态挂载 `/api/gameplay/<name>/*` 路由；内置 demo「三角占领」为完整业务子系统。

## LAYERS

### contract — base.py
- `GameplayPlugin` ABC：`create_session` / `get_state` / `submit_result` / `validate_result` / `end_session` + 类属性 `name` / `version`。
- 方法收到服务端持久化的 `state`（dict），返回新状态，**不得修改传入 state**。
- 非法输入统一抛 `ValueError`，路由层转 HTTP 400。
- **Metis E7**：`validate_result` 只做值域/身份/时间窗等结构性校验，禁止校验「得分真实性」。

### registry — registry.py
- `PluginRegistry`：进程内 `name -> GameplayPlugin`；同名重复注册抛 ValueError。
- `discover_plugins`：扫描目录直接子目录（不递归、不加载自身），含 `manifest.json` 的子包经 importlib 动态导入 `plugin.py` 取 `plugin` 属性。
- 强制校验：继承 GameplayPlugin、manifest 非空 name/version、plugin.py 暴露 `plugin` 实例、plugin.name 与 manifest 一致；缺失即 ValueError（带目录路径）。
- 无 manifest.json 的目录静默跳过。
- `register_default_plugins` 幂等：已注册同名跳过，供 main.py lifespan 调用。
- 默认扫描目录 = 本包目录，可用环境变量 `GAMEPLAY_PLUGINS_DIR` 覆盖（测试/部署用）。

### routes — routes.py
- `mount_gameplay_routes(app)` 为每个已注册插件挂载 `/api/gameplay/<name>/*`（幂等，`_mounted_plugins` 去重）。
- 每插件四端点：POST `/session`（建会话）、GET `/session/{id}/state`（任意登录，选手只读）、POST `/session/{id}/action`（先 validate 后 submit）、POST `/session/{id}/end`。
- **权限模型（用户确认）**：仅 admin/referee 可操作棋盘（`require_referee`），选手只读。
- 跨层：路由定义在 plugins/ 而非 api/。
- 内存 `_sessions` 是临时反模式（重启丢失）；`_load_db_session` 从 `models/match.GameSession` 回退装载（DB 桥），操作后 `_persist_session` 回写 state_json。
- 玩法操作后经 `manager.broadcast` 推送 `state_update` / `session_ended` 给该对局 WS 订阅者。

### plugin — triangle_occupy/plugin.py
- 适配层：`controller/` 从 demo 原样复制（规则逻辑零改动），本文件只做契约适配。
- `_CONTROLLERS`（`id(state) -> GameController`）模块级持有活实例，跨 submit_result 保持同一实例；不随 state 序列化。
- `_restore_controller` 从序列化 state 重建棋盘并校准时钟（Metis E9：`_start_ts = now - elapsed*60`）。
- `_resolve_sides` 把 JSON 字符串键规范化为 int，保证与路由层 participant_id 一致。

### controller — triangle_occupy/controller/
- 完整业务子系统：`game.py`（GameController 主控）、`rules.py`、`board.py`、`song_lib.py`（歌曲库解析）、`task_gen.py`（21 格任务生成）。
- `config/rules.json` 配置规则。

## ADDING A NEW GAMEPLAY
1. 在 `plugins/` 下建子目录 `my_plugin/`，含 `manifest.json`（非空 name/version）+ `plugin.py`。
2. `plugin.py` 继承 `GameplayPlugin` 实现五个抽象方法，末尾暴露 `plugin = MyPlugin()` 实例。
3. 方法只做值域校验（Metis E7），不校验得分真实性；非法输入抛 ValueError。
4. 重启应用：lifespan 自动 discover + register + mount 路由。
5. 前端在 `frontend/src/plugins/<name>/` 放对应组件（命名对称）。

## TRAPS
- **song_lib 至少 23 首**：建赛/开赛若歌曲库不足 23 首，`generate_tasks_from_songs` 抛 `ValueError("歌曲库至少需要 23 首")`，经路由转 400。
- 内存 `_sessions` 重启丢失：新会话读写应走 GameSession DB（todo 14），勿依赖内存态。
- 插件不得持全局状态（契约约束）；活控制器实例仅内存持有，重启靠 `_restore_controller` 重建。
- JSON 往返后 dict 键变字符串：sides / cells 的 int 键需规范化，否则 validate_result 匹配失败。
