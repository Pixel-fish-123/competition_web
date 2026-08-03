# Core 层（backend/app/core/）

## OVERVIEW
安全与横切关注点：JWT/bcrypt、RBAC 依赖、CSRF、限流、账号锁定、审计写入、WS 连接管理；被 api/ 与 services/ 复用，不依赖业务路由。

## MODULES
| 模块 | 职责 | 关键函数 |
|------|------|----------|
| security | JWT 签发/解码 + bcrypt 密码哈希 | `create_access_token`(HS256,7天,sub=str(uid)+role)、`decode_access_token`(抛 InvalidTokenError)、`hash_password`/`verify_password` |
| rbac | 当前用户解析 + 角色门 | `get_current_user`(cookie "token"→DB 用户，role 以 DB 为准)、`require_role(*roles)` 工厂、`require_admin`/`require_referee` 实例 |
| csrf | CSRF 中间件 | `CSRFMiddleware`：非 GET/HEAD/OPTIONS 且带 Origin 时校验同源或白名单，否则 403 |
| ratelimit | slowapi 全局限流 | `limiter`：默认 100/min，auth 10/min、admin 60/min 显式覆盖；429 统一 JSON |
| lockout | 登录爆破防护 | `record_failed_login`(5 次→锁 15min)、`locked_until`/`is_locked`、`reset_lockout`(成功登录/解封)、`locked_accounts`/`failed_count`/`ip_failed_count`(监控) |
| audit | 审计日志写入 | `log_audit(db, user_id, action, ip, user_agent, detail)`：db 可传 None（自动开独立会话）；detail 存 JSON 列 |
| ws_manager | WS 连接登记与广播 | `manager`：`connect`/`disconnect`/`broadcast`(put_nowait 入队)、`active_connections`；队列满断开慢消费者 |

## CONVENTIONS
- 中间件栈顺序（main.py 最后 add 的在外层）：CORS → CSRF → SlowAPI。CSRF 先于限流拒伪造来源。
- `get_current_user` 401 detail 统一 `"未登录或登录已失效"`（无 cookie/坏 JWT/未知用户/非 active 全归 401）；`require_role` 403 detail 统一 `"权限不足"`。
- JWT 的 role 声明不用于授权，只作 cookie 载体；授权一律读 DB 实时 role。
- lockout 双维度：`by_username` 管锁定，`by_ip` 只统计（IP 拦截交给 slowapi）；单进程内存态 + `threading.Lock`。
- `log_audit` 复用请求的 db 会话（`Depends(get_db)` 注入），失败/匿名动作 user_id 传 None。
- ws_manager 线程安全：`connect`/`disconnect`/`broadcast` 可在事件循环线程或同步工作线程调用；广播只 `put_nowait`，实际发送由各连接发送任务在事件循环执行。

## ANTI-PATTERNS
- **不要在 ws_manager 里加鉴权**（Metis E13）：它只做连接登记与推送；鉴权/订阅白名单/频率限制全在 api/ws.py 端点内。
- 不要在 ws_manager 广播敏感管理数据（只推对局状态帧）。
- 不要用 passlib 做密码哈希（本项目用 bcrypt 直连）。

## TRAPS
- `decode_access_token` 抛 `jwt.InvalidTokenError`（基类，含 ExpiredSignatureError），调用方须捕获；`verify_password` 对畸形哈希返回 False 而非抛错。
- `require_referee = require_role("admin","referee")`：裁判端点同时放行 admin，比赛级校验（referee_ids）在 services 层补。
- lockout 过期自动解锁（`_expire_if_due` 在查询时惰性清理）；`reset_lockout` 在登录成功与 admin 改状态时都要调。
- `broadcast` 遇 `asyncio.QueueFull` 直接 `disconnect` 该连接（慢消费者保护），无连接时静默跳过。
- CSRF 白名单 `ALLOWED_ORIGINS` 含 localhost:5173/127.0.0.1:5173；同源判定会归一化默认端口（:80/:443）。
