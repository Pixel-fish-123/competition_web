"""IP 黑名单核心：内存集合 + DB 同步。

- 启动时 ``load_blacklist(db)`` 从 ip_bans 表加载全部 IP 到内存集合
  （单进程 SQLite 部署，内存集合适配，避免每请求查库）。
- ``is_banned(ip)`` 供全局中间件拦截（黑名单 IP 全站 403）。
- ``ban_ip`` / ``unban`` 同时更新内存与 DB。
- 本地回环地址（127.0.0.1 / ::1）永远豁免：不自动拉黑、不被拦截，
  避免误封自己后无法登录后台。
"""

import ipaddress
import threading

from sqlalchemy.orm import Session

from app.models.ip_ban import IpBan

LOOPBACK = ("127.0.0.1", "::1", "localhost")

_lock = threading.Lock()
_banned: set[str] = set()


def _normalize_ip(ip: str) -> str | None:
    """校验并规范化 IP（IPv4/IPv6）；非法或本地回环返回 None。"""
    if ip in LOOPBACK:
        return ip
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


def load_blacklist(db: Session) -> None:
    """启动时从 DB 加载黑名单到内存。"""
    with _lock:
        rows = db.query(IpBan.ip).all()
        _banned.clear()
        _banned.update(row[0] for row in rows)


def is_banned(ip: str) -> bool:
    """该 IP 是否被拉黑（本地回环永远放行）。"""
    if ip in LOOPBACK:
        return False
    with _lock:
        return ip in _banned


def ban_ip(db: Session, ip: str, reason: str, created_by: int | None) -> IpBan | None:
    """拉黑一个 IP（内存 + DB）。本地回环拒绝拉黑；重复拉黑幂等。"""
    if ip in LOOPBACK:
        return None
    with _lock:
        if ip in _banned:
            return None
    existing = db.query(IpBan).filter(IpBan.ip == ip).first()
    if existing is not None:
        return existing
    row = IpBan(ip=ip, reason=reason[:200], created_by=created_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    with _lock:
        _banned.add(ip)
    return row


def unban(db: Session, ban_id: int) -> bool:
    """解封一个黑名单条目（内存 + DB）。"""
    row = db.get(IpBan, ban_id)
    if row is None:
        return False
    with _lock:
        _banned.discard(row.ip)
    db.delete(row)
    db.commit()
    return True


def list_bans(db: Session) -> list[IpBan]:
    """全部黑名单条目（最新在前）。"""
    return db.query(IpBan).order_by(IpBan.id.desc()).all()


def reset_blacklist() -> None:
    """清空内存黑名单（测试隔离用；DB 行由测试重建表处理）。"""
    with _lock:
        _banned.clear()
