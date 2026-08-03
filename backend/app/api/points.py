"""积分 API（todo 17）：我的流水 / 全局榜 / 管理员发放。

路由：
- GET  /api/points/me            任意登录用户：我的流水 + 余额
- GET  /api/points/leaderboard   任意登录用户：按用户聚合的全局榜（?kind= 过滤）
- POST /api/admin/points         仅 admin：发放活动/手动积分（写审计日志）

流水只能由系统产生（比赛结算自动 / 管理员发放），无直接改库端点
（plan.md todo 17 Must NOT）。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.rbac import get_current_user, require_admin
from app.db import get_db
from app.models.point import PointTransaction
from app.models.user import User
from app.schemas.point import (
    LeaderboardRow,
    MyPointsOut,
    PointTransactionOut,
    PointsGrantIn,
)
from app.services import points_service

router = APIRouter()


def _request_meta(request: Request) -> tuple[str, str | None]:
    ip = request.client.host if request.client else "unknown"
    return ip, request.headers.get("user-agent")


@router.get("/api/points/me", response_model=MyPointsOut)
def my_points(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """我的流水（最新在前）+ 当前余额。"""
    transactions = (
        db.query(PointTransaction)
        .filter(PointTransaction.user_id == user.id)
        .order_by(PointTransaction.id.desc())
        .all()
    )
    return {
        "transactions": transactions,
        "balance": points_service.get_user_points(db, user.id),
    }


@router.get("/api/points/leaderboard", response_model=list[LeaderboardRow])
def leaderboard(
    kind: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """全局榜：按用户聚合，total 降序；?kind=competition|activity 过滤类别。"""
    return points_service.get_leaderboard(db, kind=kind)


@router.post("/api/admin/points", response_model=PointTransactionOut)
def grant_points(
    payload: PointsGrantIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """管理员发放活动/手动积分（competition 类仅系统结算产生）。

    校验目标用户存在；落库后写审计日志 action="points_grant"。
    """
    if db.get(User, payload.user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    transaction = PointTransaction(
        user_id=payload.user_id,
        amount=payload.amount,
        kind=payload.kind,
        reason=payload.reason,
        created_by=admin.id,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        admin.id,
        "points_grant",
        ip,
        user_agent,
        {
            "user_id": payload.user_id,
            "amount": payload.amount,
            "kind": payload.kind,
            "reason": payload.reason,
        },
    )
    return transaction
