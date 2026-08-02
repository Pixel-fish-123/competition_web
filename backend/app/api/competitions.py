"""Competition management endpoints (todo 8): public list/detail + admin CRUD.

Routes:
- GET    /api/competitions                  public list (no auth), id desc
- GET    /api/competitions/{id}             public detail (no auth)
- POST   /api/competitions                  admin create (referee_ids validated)
- PATCH  /api/competitions/{id}             admin partial update
- POST   /api/competitions/{id}/status      admin state-machine transition
- DELETE /api/competitions/{id}             admin delete (draft/cancelled only)

Status machine (enforced here): draft → registration → ongoing → finished;
cancelled may be entered from draft or registration only; finished is terminal.

Referee assignment (Metis E3): every id in ``referee_ids`` must exist and the
user's live role must be "referee" (never trusted from a client-claimed role).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import require_admin
from app.db import get_db
from app.models.competition import Competition
from app.models.registration import Registration
from app.models.user import User
from app.schemas.competition import (
    CompetitionCreate,
    CompetitionOut,
    CompetitionStatusUpdate,
    CompetitionUpdate,
)

router = APIRouter()

# Legal transitions: {from_status: {reachable statuses}}.
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"registration", "cancelled"},
    "registration": {"ongoing", "cancelled"},
    "ongoing": {"finished"},
    "finished": set(),  # terminal
    "cancelled": set(),  # terminal
}

DELETABLE_STATUSES = ("draft", "cancelled")


def _get_competition_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")
    return competition


def _validate_referee_ids(db: Session, referee_ids: list[int]) -> None:
    """Every id must exist and be a user with live role "referee" (Metis E3)."""
    for referee_id in referee_ids:
        user = db.get(User, referee_id)
        if user is None:
            raise HTTPException(status_code=404, detail="裁判用户不存在")
        if user.role != "referee":
            raise HTTPException(status_code=400, detail="裁判组成员必须是 referee 角色")


@router.get("/api/competitions", response_model=list[CompetitionOut])
def list_competitions(db: Session = Depends(get_db)):
    """Public: all competitions, newest first. No authentication required."""
    return db.query(Competition).order_by(Competition.id.desc()).all()


@router.get("/api/competitions/{competition_id}", response_model=CompetitionOut)
def get_competition(competition_id: int, db: Session = Depends(get_db)):
    """Public: single competition detail. No authentication required."""
    return _get_competition_or_404(db, competition_id)


@router.post("/api/competitions", response_model=CompetitionOut)
def create_competition(
    payload: CompetitionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only create. status starts at "draft"; referee_ids fully validated."""
    _validate_referee_ids(db, payload.referee_ids)
    competition = Competition(
        name=payload.name,
        banner_url=payload.banner_url,
        description=payload.description,
        participant_type=payload.participant_type,
        tournament_format=payload.tournament_format,
        format_config=payload.format_config,
        points_rule=payload.points_rule,
        gameplay_plugin=payload.gameplay_plugin,
        song_lib=payload.song_lib,
        referee_ids=payload.referee_ids,
        max_participants=payload.max_participants,
        status="draft",
        start_time=payload.start_time,
        end_time=payload.end_time,
        created_by=admin.id,
    )
    db.add(competition)
    db.commit()
    db.refresh(competition)
    return competition


@router.patch("/api/competitions/{competition_id}", response_model=CompetitionOut)
def update_competition(
    competition_id: int,
    payload: CompetitionUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only partial update; referee_ids re-validated when provided."""
    competition = _get_competition_or_404(db, competition_id)
    if payload.referee_ids is not None:
        _validate_referee_ids(db, payload.referee_ids)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(competition, field, value)
    db.commit()
    db.refresh(competition)
    return competition


@router.post(
    "/api/competitions/{competition_id}/status", response_model=CompetitionOut
)
def change_status(
    competition_id: int,
    payload: CompetitionStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only status transition, validated against the state machine."""
    competition = _get_competition_or_404(db, competition_id)
    if payload.status not in TRANSITIONS.get(competition.status, set()):
        raise HTTPException(status_code=400, detail="非法状态流转")
    competition.status = payload.status
    db.commit()
    db.refresh(competition)
    return competition


@router.delete("/api/competitions/{competition_id}")
def delete_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only delete, allowed only for draft/cancelled competitions.

    Registrations are removed explicitly (SQLite FKs are metadata-only by
    default, so no ON DELETE CASCADE fires).
    """
    competition = _get_competition_or_404(db, competition_id)
    if competition.status not in DELETABLE_STATUSES:
        raise HTTPException(status_code=400, detail="比赛已开始或已结束，无法删除")
    db.query(Registration).filter(Registration.competition_id == competition.id).delete()
    db.delete(competition)
    db.commit()
    return {"ok": True}
