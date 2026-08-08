"""Admin-only IP 黑名单管理端点（恶意登录防护）。

- GET    /api/admin/ip-bans             黑名单列表（最新在前）
- POST   /api/admin/ip-bans             手动拉黑（校验 IPv4/IPv6 格式）
- DELETE /api/admin/ip-bans/{ban_id}    解封

自动拉黑由 auth 登录失败路径触发（24h 内失败登录 ≥20 次），
见 app/api/auth.py。本地回环地址（127.0.0.1/::1）永远豁免。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.ip_ban import ban_ip, list_bans, unban
from app.core.ratelimit import limiter
from app.core.rbac import require_admin
from app.db import get_db
from app.models.user import User
from sqlalchemy.orm import Session

router = APIRouter(dependencies=[Depends(require_admin)])


class IpBanCreate(BaseModel):
    ip: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=200)


@router.get("/api/admin/ip-bans")
@limiter.limit("60/minute")
def get_ip_bans(request: Request, db: Session = Depends(get_db)):
    rows = list_bans(db)
    return [
        {
            "id": r.id,
            "ip": r.ip,
            "reason": r.reason,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/api/admin/ip-bans")
@limiter.limit("60/minute")
def add_ip_ban(
    payload: IpBanCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from app.core.ip_ban import LOOPBACK, _normalize_ip

    if payload.ip.strip() in LOOPBACK:
        raise HTTPException(status_code=400, detail="本地回环地址不可拉黑")
    normalized = _normalize_ip(payload.ip)
    if normalized is None:
        raise HTTPException(status_code=400, detail="IP 格式不正确（仅支持 IPv4/IPv6）")
    row = ban_ip(db, normalized, payload.reason.strip(), admin.id)
    return {"ok": True, "banned": row is not None, "ip": normalized}


@router.delete("/api/admin/ip-bans/{ban_id}")
@limiter.limit("60/minute")
def delete_ip_ban(
    ban_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not unban(db, ban_id):
        raise HTTPException(status_code=404, detail="黑名单条目不存在")
    return {"ok": True}
