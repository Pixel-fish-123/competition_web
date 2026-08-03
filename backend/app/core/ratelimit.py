"""slowapi 全局限流（todo 16）。

- 全局默认：``100/minute`` / IP —— 应用到所有未显式装饰的路由
  （slowapi 中间件在路由层检查默认限额）。
- ``/api/auth/login``、``/api/auth/register``：``10/minute`` / IP
  （显式 ``@limiter.limit``，覆盖默认值）。账号维度由 core/lockout.py
  承担 → 双重维度（IP + 账号）。
- ``/api/admin/*``：``60/minute`` / IP（管理端点更严格）。
- 超限统一返回 429 JSON ``{"detail": "请求过于频繁，请稍后再试"}``
  （处理器注册在 app/main.py）。
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
)
