"""对局 API（todo 14）：列表 / 详情 / 开赛 / 记分。

路由（Metis C7：对局由引擎赛程创建，不提供人工创建端点）：
- GET  /api/competitions/{competition_id}/matches   任意登录用户：赛程列表
- GET  /api/matches/{match_id}                       任意登录用户：单局详情
- POST /api/matches/{match_id}/start                 裁判（须在本场 referee_ids）
- POST /api/matches/{match_id}/result                裁判（须在本场 referee_ids）
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.core.rbac import get_current_user, require_referee
from app.db import get_db
from app.models.competition import Competition
from app.models.match import GameSession, Match
from app.models.registration import Registration
from app.models.team import Team
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


def _request_meta(request: Request) -> tuple[str, str | None]:
    ip = request.client.host if request.client else "unknown"
    return ip, request.headers.get("user-agent")


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


def _resolve_participant_names(
    db: Session,
    competition_id: int,
    participant_a: int | None,
    participant_b: int | None,
) -> tuple[str | None, str | None]:
    """解析两名参赛者的显示名称（队伍=队名，个体=昵称或用户名）。

    批量查询避免 N+1：Registration 一次 in_ 取出，Team/User 再各一次批量查。
    参赛者 id 可能同时是某队的 team_id 或某个人的 user_id，按该报名记录的
    participant_type 决定解析方式；找不到返回 None。
    """
    ids = [pid for pid in (participant_a, participant_b) if pid is not None]
    names: dict[int, str | None] = {}
    if ids:
        regs = (
            db.query(Registration)
            .filter(
                Registration.competition_id == competition_id,
                Registration.status == "approved",
                (Registration.team_id.in_(ids)) | (Registration.user_id.in_(ids)),
            )
            .all()
        )
        team_ids = [r.team_id for r in regs if r.team_id is not None]
        user_ids = [r.user_id for r in regs if r.user_id is not None]
        teams = (
            {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
            if team_ids
            else {}
        )
        users = (
            {
                u.id: (u.nickname or u.username)
                for u in db.query(User).filter(User.id.in_(user_ids)).all()
            }
            if user_ids
            else {}
        )
        for pid in ids:
            reg = next((r for r in regs if r.team_id == pid or r.user_id == pid), None)
            if reg is None:
                names[pid] = None
            elif reg.participant_type == "team":
                names[pid] = teams.get(pid)
            else:
                names[pid] = users.get(pid)
    return names.get(participant_a), names.get(participant_b)


def _match_out(db: Session, match: Match) -> MatchOut:
    """序列化单局对局并填充参赛者显示名称。"""
    a_name, b_name = _resolve_participant_names(
        db, match.competition_id, match.participant_a, match.participant_b
    )
    return MatchOut.model_validate(match).model_copy(
        update={"participant_a_name": a_name, "participant_b_name": b_name}
    )


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
    matches = (
        db.query(Match)
        .filter(Match.competition_id == competition_id)
        .order_by(Match.round_id, Match.id)
        .all()
    )
    return [_match_out(db, m) for m in matches]


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
    return MatchDetailOut(match=_match_out(db, match), session=session_out)


@router.post("/api/matches/{match_id}/start")
def start_match(
    match_id: int,
    payload: MatchStartIn,
    request: Request,
    db: Session = Depends(get_db),
    staff: User = Depends(require_referee),
):
    """裁判开赛（须在本场 referee_ids 内）。轮空对局自动完结，不建会话。"""
    session = match_service.start_match(
        db, match_id, staff, scheduled_at=payload.scheduled_at
    )
    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        staff.id,
        "match_start",
        ip,
        user_agent,
        {"match_id": match_id, "referee": staff.username},
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
    request: Request,
    db: Session = Depends(get_db),
    staff: User = Depends(require_referee),
):
    """裁判记分（须在本场 referee_ids 内）；单败淘汰禁平局。"""
    result = match_service.record_match_result(db, match_id, payload, staff)
    ip, user_agent = _request_meta(request)
    log_audit(
        db,
        staff.id,
        "match_result",
        ip,
        user_agent,
        {
            "match_id": match_id,
            "referee": staff.username,
            "winner": payload.winner,
            "is_draw": payload.is_draw,
        },
    )
    return _match_out(db, result)
