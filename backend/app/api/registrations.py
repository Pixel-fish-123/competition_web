"""Registration endpoints: register / withdraw / list / admin approve-reject.

Auth: ``get_current_user`` (app/core/rbac.py) resolves the user from the
"token" cookie — every route here requires an authenticated, active account;
admin 审批端点单独加 ``require_admin`` 依赖。

Registration lifecycle: rows are created with status "pending", then admin
审批（approve/reject）推进为 "approved"/"rejected"。Capacity counting uses
``status in ("pending", "approved")`` so a pending registration reserves a
slot immediately.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.rbac import get_current_user, require_admin
from app.db import get_db
from app.models.competition import Competition
from app.models.registration import Registration
from app.models.team import Team
from app.models.user import User
from app.schemas.registration import MyRegistrationOut, RegistrationCreate, RegistrationOut

router = APIRouter()

WITHDRAWABLE_STATUSES = ("pending", "approved")


def _request_meta(request: Request) -> tuple[str, str | None]:
    """(ip, user_agent) 供审计日志使用。"""
    ip = request.client.host if request.client else "unknown"
    return ip, request.headers.get("user-agent")


def _get_competition_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")
    return competition


def _registration_out(db: Session, reg: Registration) -> RegistrationOut:
    """序列化报名记录并解析参赛者名称（队伍=队名，个体=昵称或用户名）。"""
    name: str | None = None
    if reg.participant_type == "team" and reg.team_id is not None:
        team = db.get(Team, reg.team_id)
        name = team.name if team is not None else None
    elif reg.user_id is not None:
        user = db.get(User, reg.user_id)
        name = (user.nickname or user.username) if user is not None else None
    return RegistrationOut.model_validate(reg).model_copy(
        update={"participant_name": name}
    )


def _approved_count(db: Session, competition_id: int) -> int:
    """Count registrations occupying capacity (pending or approved)."""
    return (
        db.query(Registration)
        .filter(
            Registration.competition_id == competition_id,
            Registration.status.in_(WITHDRAWABLE_STATUSES),
        )
        .count()
    )


def _existing_registration(
    db: Session, competition_id: int, user: User
) -> Registration | None:
    """The user's own registration row for a competition.

    Individual: row with user_id == current user. Team: the row stores the
    CAPTAIN's user_id, so a team registration is also found by user_id (team
    members have no row of their own — covered via team membership).
    """
    return (
        db.query(Registration)
        .filter(
            Registration.competition_id == competition_id,
            Registration.user_id == user.id,
        )
        .first()
    )


@router.post(
    "/api/competitions/{competition_id}/register", response_model=RegistrationOut
)
def register(
    competition_id: int,
    payload: RegistrationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    competition = _get_competition_or_404(db, competition_id)
    if competition.status != "registration":
        raise HTTPException(status_code=400, detail="当前不可报名")

    if payload.participant_type == "team":
        if payload.team_id is None:
            raise HTTPException(status_code=422, detail="报名队伍不能为空")
        team = db.get(Team, payload.team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="队伍不存在")
        if team.captain_id != user.id:
            raise HTTPException(status_code=403, detail="只有队长可以报名")
        # A team registers as a unit: at most one registration per competition.
        already = (
            db.query(Registration)
            .filter(
                Registration.competition_id == competition_id,
                Registration.team_id == team.id,
            )
            .first()
        )
        if already is not None:
            if already.status != "rejected":
                raise HTTPException(status_code=400, detail="该队伍已报名")
            # 被拒绝后可重新报名：复用该行并重置为 pending（不占名额，见下）。
            registration = already
        else:
            registration = Registration(
                competition_id=competition_id,
                participant_type="team",
                team_id=team.id,
                user_id=team.captain_id,  # captain's id = the participant unit
            )
    else:  # individual
        existing = _existing_registration(db, competition_id, user)
        if existing is not None:
            if existing.status != "rejected":
                raise HTTPException(status_code=400, detail="已报名")
            # 被拒绝后可重新报名：复用该行并重置为 pending。
            registration = existing
        else:
            registration = Registration(
                competition_id=competition_id,
                participant_type="individual",
                user_id=user.id,
            )

    # Duplicate checks come before capacity so an already-registered user gets
    # "已报名" even when the competition is full (the slot is theirs anyway).
    if _approved_count(db, competition_id) >= competition.max_participants:
        raise HTTPException(status_code=400, detail="报名已满")

    registration.status = "pending"  # 待 admin 审批（approve/reject 端点见下）
    db.add(registration)
    try:
        db.commit()
    except IntegrityError:
        # uq_reg_competition_user race: registered between check and commit.
        db.rollback()
        raise HTTPException(status_code=400, detail="已报名")
    db.refresh(registration)
    return _registration_out(db, registration)


@router.delete("/api/competitions/{competition_id}/register")
def withdraw(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    competition = _get_competition_or_404(db, competition_id)
    if competition.status == "finished":
        raise HTTPException(status_code=400, detail="比赛已结束，无法撤销")

    registration = _existing_registration(db, competition_id, user)
    if registration is None or registration.status not in WITHDRAWABLE_STATUSES:
        raise HTTPException(status_code=404, detail="报名记录不存在")

    db.delete(registration)
    db.commit()
    return {"ok": True}


@router.get(
    "/api/competitions/{competition_id}/registrations",
    response_model=list[RegistrationOut],
)
def list_registrations(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_competition_or_404(db, competition_id)
    registrations = (
        db.query(Registration)
        .filter(Registration.competition_id == competition_id)
        .order_by(Registration.id)
        .all()
    )
    return [_registration_out(db, r) for r in registrations]


@router.get("/api/my/registrations", response_model=MyRegistrationOut)
def my_registrations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    registrations = (
        db.query(Registration)
        .filter(Registration.user_id == user.id)
        .order_by(Registration.id.desc())
        .all()
    )
    return {"registrations": [_registration_out(db, r) for r in registrations]}


def _get_registration_or_404(
    db: Session, competition_id: int, registration_id: int
) -> Registration:
    """取指定比赛的报名记录（必须属于该比赛，否则 404）。"""
    registration = (
        db.query(Registration)
        .filter(
            Registration.id == registration_id,
            Registration.competition_id == competition_id,
        )
        .first()
    )
    if registration is None:
        raise HTTPException(status_code=404, detail="报名记录不存在")
    return registration


def _resolve_registration(
    db: Session,
    competition_id: int,
    registration_id: int,
    admin: User,
    approve: bool,
    request: Request,
) -> RegistrationOut:
    """admin 审批共用逻辑：置 approved/rejected 并写审计日志。"""
    _get_competition_or_404(db, competition_id)
    registration = _get_registration_or_404(db, competition_id, registration_id)
    if registration.status != "pending":
        raise HTTPException(status_code=400, detail="该报名已处理")

    registration.status = "approved" if approve else "rejected"
    if approve:
        registration.approved_by = admin.id
    db.commit()
    db.refresh(registration)

    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        admin.id,
        "registration_approve" if approve else "registration_reject",
        ip,
        user_agent,
        {
            "competition_id": competition_id,
            "registration_id": registration.id,
            "participant_type": registration.participant_type,
        },
    )
    return _registration_out(db, registration)


@router.post(
    "/api/admin/competitions/{competition_id}/registrations/{registration_id}/approve",
    response_model=RegistrationOut,
)
def approve_registration(
    competition_id: int,
    registration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin 审批通过报名（pending -> approved）。"""
    return _resolve_registration(
        db, competition_id, registration_id, admin, approve=True, request=request
    )


@router.post(
    "/api/admin/competitions/{competition_id}/registrations/{registration_id}/reject",
    response_model=RegistrationOut,
)
def reject_registration(
    competition_id: int,
    registration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin 拒绝报名（pending -> rejected）。"""
    return _resolve_registration(
        db, competition_id, registration_id, admin, approve=False, request=request
    )
