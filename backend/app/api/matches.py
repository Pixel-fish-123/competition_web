"""对局 API（todo 14）：列表 / 详情 / 开赛 / 记分。

路由（Metis C7：对局由引擎赛程创建，不提供人工创建端点）：
- GET  /api/competitions/{competition_id}/matches   任意登录用户：赛程列表
- GET  /api/matches/{match_id}                       任意登录用户：单局详情
- POST /api/matches/{match_id}/start                 裁判（须在本场 referee_ids）
- POST /api/matches/{match_id}/result                裁判（须在本场 referee_ids）
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user, require_referee
from app.db import get_db
from app.models.competition import Competition
from app.models.match import GameSession, Match
from app.models.user import User
from app.schemas.match import (
    GameSessionOut,
    MatchDetailOut,
    MatchOut,
    MatchResultIn,
    MatchStartIn,
)
from app.services import match_service

router = APIRouter()


def _get_competition_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")
    return competition


def _get_match_or_404(db: Session, match_id: int) -> Match:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    return match


@router.get(
    "/api/competitions/{competition_id}/matches", response_model=list[MatchOut]
)
def list_matches(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """赛程列表（任意登录用户），按轮次/创建顺序排列。"""
    _get_competition_or_404(db, competition_id)
    return (
        db.query(Match)
        .filter(Match.competition_id == competition_id)
        .order_by(Match.round_id, Match.id)
        .all()
    )


@router.get("/api/matches/{match_id}", response_model=MatchDetailOut)
def get_match_detail(
    match_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """单局详情（任意登录用户）：对局信息 + 玩法会话状态（若已开赛）。"""
    match = _get_match_or_404(db, match_id)
    session = (
        db.query(GameSession)
        .filter(GameSession.match_id == match_id)
        .order_by(GameSession.id.desc())
        .first()
    )
    session_out = None
    if session is not None:
        session_out = GameSessionOut(
            id=session.id,
            match_id=session.match_id,
            plugin_name=session.plugin_name,
            state=session.state_json,
            started_at=session.started_at,
            ended_at=session.ended_at,
        )
    return MatchDetailOut(match=MatchOut.model_validate(match), session=session_out)


@router.post("/api/matches/{match_id}/start")
def start_match(
    match_id: int,
    payload: MatchStartIn,
    db: Session = Depends(get_db),
    staff: User = Depends(require_referee),
):
    """裁判开赛（须在本场 referee_ids 内）。轮空对局自动完结，不建会话。"""
    session = match_service.start_match(
        db, match_id, staff, scheduled_at=payload.scheduled_at
    )
    if session is None:
        return {"session_id": None, "match_id": match_id, "status": "finished"}
    return {
        "session_id": session.id,
        "match_id": match_id,
        "status": "in_progress",
        "state": session.state_json,
    }


@router.post("/api/matches/{match_id}/result", response_model=MatchOut)
def record_result(
    match_id: int,
    payload: MatchResultIn,
    db: Session = Depends(get_db),
    staff: User = Depends(require_referee),
):
    """裁判记分（须在本场 referee_ids 内）；单败淘汰禁平局。"""
    return match_service.record_match_result(db, match_id, payload, staff)
