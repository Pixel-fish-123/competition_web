"""Registration endpoints: register / withdraw / list (todo 7).

Auth: ``get_current_user`` (app/core/rbac.py) resolves the user from the
"token" cookie — every route here requires an authenticated, active account.

Registration lifecycle note: approval/rejection endpoints arrive with the
admin flows (todo 8/19), so rows are created with status "pending" and stay
pending for now. Capacity counting uses ``status in ("pending", "approved")``
so a pending registration reserves a slot immediately.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user
from app.db import get_db
from app.models.competition import Competition
from app.models.registration import Registration
from app.models.team import Team
from app.models.user import User
from app.schemas.registration import MyRegistrationOut, RegistrationCreate, RegistrationOut

router = APIRouter()

WITHDRAWABLE_STATUSES = ("pending", "approved")


def _get_competition_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")
    return competition


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
            raise HTTPException(status_code=400, detail="该队伍已报名")
        registration = Registration(
            competition_id=competition_id,
            participant_type="team",
            team_id=team.id,
            user_id=team.captain_id,  # captain's id = the participant unit
        )
    else:  # individual
        if _existing_registration(db, competition_id, user) is not None:
            raise HTTPException(status_code=400, detail="已报名")
        registration = Registration(
            competition_id=competition_id,
            participant_type="individual",
            user_id=user.id,
        )

    # Duplicate checks come before capacity so an already-registered user gets
    # "已报名" even when the competition is full (the slot is theirs anyway).
    if _approved_count(db, competition_id) >= competition.max_participants:
        raise HTTPException(status_code=400, detail="报名已满")

    registration.status = "pending"  # approval arrives with admin (todo 8/19)
    db.add(registration)
    try:
        db.commit()
    except IntegrityError:
        # uq_reg_competition_user race: registered between check and commit.
        db.rollback()
        raise HTTPException(status_code=400, detail="已报名")
    db.refresh(registration)
    return registration


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
    return (
        db.query(Registration)
        .filter(Registration.competition_id == competition_id)
        .order_by(Registration.id)
        .all()
    )


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
    return {"registrations": registrations}
