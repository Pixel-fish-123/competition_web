"""Admin-only user management endpoints (todo 5/7): list users, create
accounts, hard-delete accounts (with manual cascade cleanup), change
role/status, reset password.

Every route is gated by ``require_admin`` at the router level (403 for
non-admins, 401 for unauthenticated/banned users). Audit logging on
role/status changes, account create/delete, lockout reset when an account
is re-activated, and a 60/minute per-IP rate limit.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.ratelimit import limiter
from app.core.rbac import require_admin
from app.core.security import hash_password
from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.competition import Competition
from app.models.match import Match
from app.models.point import PointTransaction
from app.models.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User
from app.schemas.user import EMAIL_RE, UserOut, UserPatchRequest

router = APIRouter(dependencies=[Depends(require_admin)])

VALID_ROLES = {"admin", "referee", "player"}


class UserCreateRequest(BaseModel):
    """Admin-created account payload (todo 7): username/email/password/role.

    Email policy mirrors ``RegisterRequest``; password length policy matches
    the register / reset-password endpoints.
    """

    username: str = Field(min_length=2, max_length=30)
    email: str
    password: str = Field(min_length=6, max_length=64)
    role: str
    nickname: str | None = Field(default=None, min_length=2, max_length=30)
    qq: str | None = Field(default=None, max_length=20)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        value = value.strip()
        if len(value) > 120 or not EMAIL_RE.match(value):
            raise ValueError("邮箱格式不正确")
        return value

    @field_validator("qq")
    @classmethod
    def _validate_qq(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not value.isdigit() or len(value) > 20:
            raise ValueError("QQ 号应为纯数字")
        return value


@router.get("/api/admin/users", response_model=list[UserOut])
@limiter.limit("60/minute")
def list_users(request: Request, db: Session = Depends(get_db)):
    """List all users, ordered by id."""
    return db.query(User).order_by(User.id).all()


@router.post("/api/admin/users", response_model=UserOut)
@limiter.limit("60/minute")
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """创建账号（admin only，todo 7）：角色/密码直接指定，创建后立即可登录。

    role 必须是 admin/referee/player 之一；username/email 唯一（与注册一致）。
    """
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="无效的角色")
    if db.query(User).filter(User.username == payload.username).first() is not None:
        raise HTTPException(status_code=400, detail="用户名已存在")
    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname,
        qq=payload.qq,
        role=payload.role,
        status="active",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="用户名或邮箱已存在")
    db.refresh(user)

    ip = request.client.host if request.client else "unknown"
    log_audit(
        db,
        current_user.id,
        "admin_create_user",
        ip,
        request.headers.get("user-agent"),
        {"username": user.username, "role": user.role},
    )
    return user


@router.delete("/api/admin/users/{user_id}")
@limiter.limit("60/minute")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """硬删除用户（todo 7）：未完结对局判对手胜 + 手工级联清理其业务数据。

    SQLite 的 FK 仅 metadata（无 ON DELETE CASCADE 触发），删除前必须按
    子行在前顺序手工清理：Registration/PointTransaction/TeamMember 删行、
    队长所属队伍先清成员再删队、AuditLog.user_id 与 Match.referee_id 置 NULL
    （保留审计追溯、避免悬空）。保护规则见下方注释。

    issue 3：选手随时可删 —— 该选手的未完结对局不再阻塞删除，而是按
    「轮空计算」直接判对手获胜（0:0，result_type=win）；对手不存在
    （轮空行等异常）标记为作废 abandoned。引擎重建/回放会自然推进
    （单败淘汰对手自动晋级）。
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 保护规则（顺序）：不能删自己 -> 不能删最后一个 admin -> 不能删创建过
    # 比赛的用户（Competition.created_by FK NOT NULL，删除会悬空）。
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    if user.role == "admin":
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="不能删除最后一个管理员")
    if (
        db.query(Competition)
        .filter(Competition.created_by == user_id)
        .count()
        > 0
    ):
        raise HTTPException(status_code=400, detail="该用户创建了比赛，无法删除")

    # issue 3：未完结对局按轮空计算 -> 对手直接获胜。
    unfinished = (
        db.query(Match)
        .filter(
            or_(Match.participant_a == user_id, Match.participant_b == user_id),
            Match.status != "finished",
        )
        .all()
    )
    for match in unfinished:
        opponent = (
            match.participant_b if match.participant_a == user_id else match.participant_a
        )
        if opponent is None:
            match.status = "finished"
            match.result_type = "abandoned"
            continue
        match.status = "finished"
        match.result_type = "win"
        match.result = {
            "winner": opponent,
            "is_draw": False,
            "score_a": 0.0,
            "score_b": 0.0,
        }

    # 级联清理（子行在前，见函数 docstring）。
    db.query(Registration).filter(Registration.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(PointTransaction).filter(PointTransaction.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(TeamMember).filter(TeamMember.user_id == user_id).delete(
        synchronize_session=False
    )
    # 队长所属队伍：先清该队全部成员行，再删队（Registration.user_id 已在上面
    # 清掉，不会残留指向该队的报名）。
    for team in db.query(Team).filter(Team.captain_id == user_id).all():
        db.query(TeamMember).filter(TeamMember.team_id == team.id).delete(
            synchronize_session=False
        )
        db.delete(team)
    # 审计保留追溯：被删用户的旧审计置 NULL（detail 仍含 username）。
    db.query(AuditLog).filter(AuditLog.user_id == user_id).update(
        {"user_id": None}, synchronize_session=False
    )
    # 裁判悬空保护：Match.referee_id 可空，置 NULL 保留对局。
    db.query(Match).filter(Match.referee_id == user_id).update(
        {"referee_id": None}, synchronize_session=False
    )

    # 删除前写审计（actor 是当前 admin，不是被删用户）。
    ip = request.client.host if request.client else "unknown"
    log_audit(
        db,
        current_user.id,
        "admin_delete_user",
        ip,
        request.headers.get("user-agent"),
        {"target_user": user.username, "target_role": user.role},
    )
    db.delete(user)
    db.commit()
    return {"ok": True}


@router.patch("/api/admin/users/{user_id}", response_model=UserOut)
@limiter.limit("60/minute")
def update_user(
    user_id: int,
    payload: UserPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Partially update a user: role and/or password (all optional)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    changed: list[str] = []
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
        changed.append("role")

    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        changed.append("password")

    if payload.qq is not None:
        user.qq = payload.qq
        changed.append("qq")

    db.commit()
    db.refresh(user)

    if changed:
        log_audit(
            db,
            current_user.id,
            "admin_update_user",
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent"),
            {"target_user": user.username, "fields": changed},
        )
    return user
