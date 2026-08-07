"""Competition management endpoints (todo 8): public list/detail + admin CRUD.

Routes:
- GET    /api/competitions                  public list (no auth), id desc
- GET    /api/competitions/{id}             public detail (no auth)
- POST   /api/competitions                  admin create (referee_ids validated)
- PATCH  /api/competitions/{id}             admin partial update
- POST   /api/competitions/{id}/status      admin state-machine transition
- DELETE /api/competitions/{id}             admin delete (draft/cancelled/finished only)

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
from app.models.match import Match
from app.models.point import PointTransaction
from app.models.registration import Registration
from app.models.user import User
from app.schemas.competition import (
    CompetitionCreate,
    CompetitionOut,
    CompetitionStatusUpdate,
    CompetitionUpdate,
)
from app.services import match_service

router = APIRouter()

# Legal transitions: {from_status: {reachable statuses}}.
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"registration", "cancelled"},
    "registration": {"ongoing", "cancelled"},
    "ongoing": {"finished"},
    "finished": set(),  # terminal
    "cancelled": set(),  # terminal
}


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
    """Admin-only status transition, validated against the state machine.

    - 进入 ongoing：由引擎赛程生成全部 Match 行（Metis C7，非人工创建）；
      已有赛程时不重复生成。
    - 进入 finished：存在未完成对局时拒绝（Metis V-checks）；``force=true``
      时强制结束（issue 8）——未完成对局标记为作废（result_type=abandoned），
      不参与排名与引擎回放，比赛直接进入 finished。
    """
    competition = _get_competition_or_404(db, competition_id)
    if payload.status not in TRANSITIONS.get(competition.status, set()):
        raise HTTPException(status_code=400, detail="非法状态流转")

    if payload.status == "ongoing":
        existing = (
            db.query(Match)
            .filter(Match.competition_id == competition.id)
            .count()
        )
        if existing == 0:
            try:
                match_service.build_schedule_for_competition(db, competition)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
    elif payload.status == "finished":
        if payload.force:
            # 强制结束：未完成对局全部作废（不参与排名，_replay_finished 对
            # 无 result 的对局天然跳过），比赛直接 finished。
            db.query(Match).filter(
                Match.competition_id == competition.id,
                Match.status != "finished",
            ).update(
                {"status": "finished", "result_type": "abandoned"},
                synchronize_session=False,
            )
        else:
            # 瑞士轮：先把因上一轮结果提交而应落地、却因崩溃/竞态漏物化的轮次
            # 补进 DB，再检查未完成对局 —— 否则缺轮会导致守卫放行过早 finish。
            match_service._advance_swiss_if_due(db, competition)
            unfinished = (
                db.query(Match)
                .filter(
                    Match.competition_id == competition.id,
                    Match.status != "finished",
                )
                .count()
            )
            if unfinished:
                raise HTTPException(status_code=400, detail="存在未完成的对局")
        # 积分纯手动：进入 finished 不再自动结算（issue 6，无结算入口）。

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
    """Admin-only delete, allowed for any competition status (issue 1).

    Business data is removed explicitly (SQLite FKs are metadata-only by
    default, so no ON DELETE CASCADE fires): Match, PointTransaction and
    Registration. AuditLog is intentionally preserved.
    """
    competition = _get_competition_or_404(db, competition_id)
    # Cascade order matters: delete Match rows (incl. legacy session history).
    db.query(Match).filter(
        Match.competition_id == competition.id
    ).delete(synchronize_session=False)
    db.query(PointTransaction).filter(
        PointTransaction.ref_competition_id == competition.id
    ).delete(synchronize_session=False)
    db.query(Registration).filter(Registration.competition_id == competition.id).delete()
    db.delete(competition)
    db.commit()
    return {"ok": True}
