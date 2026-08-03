"""账号锁定管理（todo 16）：连续失败 5 次 → 锁定 15 分钟（Metis C2：统一 5 次）。

单进程内存态即可（SQLite 单进程部署），用 threading.Lock 保护共享 dict。
双维度：``by_username`` 负责账号锁定；``by_ip`` 记录每个 IP 的失败次数
（IP 维度的拦截交给 slowapi 的限流，这里只做统计供流量监控使用）。
"""

import threading
import time

MAX_FAILED = 5
LOCKOUT_SECONDS = 15 * 60

_lock = threading.Lock()
# username -> {"count": int, "locked_until": float | None}
_by_username: dict[str, dict] = {}
# ip -> 连续失败次数
_by_ip: dict[str, int] = {}


def record_failed_login(username: str, ip: str) -> None:
    """记录一次登录失败；同一账号累计达到 MAX_FAILED 次时锁定 15 分钟。"""
    with _lock:
        entry = _by_username.setdefault(username, {"count": 0, "locked_until": None})
        entry["count"] += 1
        _by_ip[ip] = _by_ip.get(ip, 0) + 1
        if entry["count"] >= MAX_FAILED:
            entry["locked_until"] = time.time() + LOCKOUT_SECONDS


def _expire_if_due(entry: dict) -> None:
    """锁定期已过则自动解锁并清零失败计数。"""
    if entry["locked_until"] is not None and time.time() >= entry["locked_until"]:
        entry["locked_until"] = None
        entry["count"] = 0


def is_locked(username: str) -> bool:
    """账号是否处于锁定期（过期自动解锁）。"""
    with _lock:
        entry = _by_username.get(username)
        if entry is None:
            return False
        _expire_if_due(entry)
        return entry["locked_until"] is not None


def locked_until(username: str) -> float | None:
    """锁定截止时间戳；未锁定或已过期返回 None（过期自动解锁）。"""
    with _lock:
        entry = _by_username.get(username)
        if entry is None:
            return None
        _expire_if_due(entry)
        return entry["locked_until"]


def reset_lockout(username: str) -> None:
    """清除某账号的锁定与失败计数（登录成功 / 管理员解封时调用）。"""
    with _lock:
        _by_username.pop(username, None)


def failed_count(username: str) -> int:
    """某账号当前连续失败次数（供流量监控展示）。"""
    with _lock:
        entry = _by_username.get(username)
        return entry["count"] if entry else 0


def ip_failed_count(ip: str) -> int:
    """某 IP 累计失败次数（供流量监控展示）。"""
    with _lock:
        return _by_ip.get(ip, 0)


def locked_accounts() -> list[dict]:
    """当前处于锁定期的账号列表：[{"username": ..., "locked_until": float}]。"""
    with _lock:
        now = time.time()
        return [
            {"username": username, "locked_until": entry["locked_until"]}
            for username, entry in _by_username.items()
            if entry["locked_until"] is not None and entry["locked_until"] > now
        ]


def reset_all() -> None:
    """清空全部锁定/失败状态（测试隔离用）。"""
    with _lock:
        _by_username.clear()
        _by_ip.clear()
