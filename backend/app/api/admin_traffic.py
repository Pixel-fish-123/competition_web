"""Admin-only 流量监控聚合接口（todo 16）。

数据源：AuditLog 表（历史动作聚合）+ core/lockout.py（实时锁定态）。
四个端点全部挂在 router 级 ``require_admin`` 依赖下，非 admin → 403、
未登录/被封禁 → 401。每个端点额外限流 60 次/分/IP。
"""

import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.lockout import locked_accounts
from app.core.ratelimit import limiter
from app.core.rbac import require_admin
from app.db import get_db
from app.models.audit_log import AuditLog

router = APIRouter(dependencies=[Depends(require_admin)])


def _detail_username(detail) -> str | None:
    """从 detail（JSON 列，可能已是 dict）中取出 "username" 字段。"""
    if not detail:
        return None
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except (TypeError, ValueError):
            return None
    if isinstance(detail, dict):
        return detail.get("username")
    return None


@router.get("/api/admin/traffic/summary")
@limiter.limit("60/minute")
def traffic_summary(request: Request, db: Session = Depends(get_db)):
    """最近 24h / 7d 的登录尝试、失败登录、注册数及按动作类型分布。"""
    now = datetime.now(timezone.utc)

    def bucket(since: datetime) -> dict:
        rows = db.query(AuditLog).filter(AuditLog.created_at >= since).all()
        by_type = Counter(r.action for r in rows)
        return {
            "login_attempts": by_type.get("login", 0) + by_type.get("login_failed", 0),
            "failed_logins": by_type.get("login_failed", 0),
            "registrations": by_type.get("register", 0),
            "actions_by_type": dict(by_type),
        }

    return {
        "since_24h": bucket(now - timedelta(hours=24)),
        "since_7d": bucket(now - timedelta(days=7)),
    }


@router.get("/api/admin/traffic/failed-logins")
@limiter.limit("60/minute")
def failed_logins(request: Request, db: Session = Depends(get_db)):
    """TOP 失败登录 IP 与 TOP 失败登录用户名（各取前 20）。"""
    rows = db.query(AuditLog).filter(AuditLog.action == "login_failed").all()
    ip_counter: Counter = Counter(r.ip for r in rows if r.ip)
    username_counter: Counter = Counter(
        u for r in rows if (u := _detail_username(r.detail)) is not None
    )
    return {
        "top_ips": [{"ip": ip, "count": c} for ip, c in ip_counter.most_common(20)],
        "top_usernames": [
            {"username": u, "count": c} for u, c in username_counter.most_common(20)
        ],
    }


@router.get("/api/admin/traffic/locked")
@limiter.limit("60/minute")
def locked(request: Request):
    """当前处于锁定期的账号列表（实时，来自 core/lockout.py）。"""
    now_ts = datetime.now(timezone.utc).timestamp()
    items = []
    for acc in locked_accounts():
        until = datetime.fromtimestamp(acc["locked_until"], tz=timezone.utc)
        items.append(
            {
                "username": acc["username"],
                "locked_until": until.isoformat(),
                "remaining_seconds": max(0, int(acc["locked_until"] - now_ts)),
            }
        )
    return items


@router.get("/api/admin/traffic/logs")
@limiter.limit("60/minute")
def audit_logs(
    request: Request,
    action: str | None = Query(default=None),
    username: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """最近审计日志，支持按 action / username 过滤，分页返回。"""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    rows = query.order_by(AuditLog.id.desc()).all()
    if username:
        rows = [r for r in rows if _detail_username(r.detail) == username]
    total = len(rows)
    start = (page - 1) * page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "action": r.action,
                "ip": r.ip,
                "user_agent": r.user_agent,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows[start : start + page_size]
        ],
    }
