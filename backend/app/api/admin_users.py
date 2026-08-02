"""Admin-only user management endpoints (todo 5): list users, change
role/status, reset password.

Every route is gated by ``require_admin`` at the router level (403 for
non-admins, 401 for unauthenticated/banned users).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import require_admin
from app.core.security import hash_password
from app.db import get_db
from app.models.user import User
from app.schemas.user import UserOut, UserPatchRequest

router = APIRouter(dependencies=[Depends(require_admin)])

VALID_ROLES = {"admin", "referee", "player"}
VALID_STATUSES = {"active", "banned"}


@router.get("/api/admin/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    """List all users, ordered by id."""
    return db.query(User).order_by(User.id).all()


@router.patch("/api/admin/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserPatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Partially update a user: role, status and/or password (all optional)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    if payload.role is not None:
        if payload.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="无效的角色")
        # Last-admin guard: an admin must not demote themselves away from
        # admin when no other admin remains (count all admins).
        if user.id == current_user.id and user.role == "admin" and payload.role != "admin":
            admin_count = db.query(User).filter(User.role == "admin").count()
            if admin_count == 1:
                raise HTTPException(status_code=400, detail="不能降级最后一个管理员")
        user.role = payload.role

    if payload.status is not None:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="无效的状态")
        user.status = payload.status

    if payload.password is not None:
        user.password_hash = hash_password(payload.password)

    db.commit()
    db.refresh(user)
    return user
