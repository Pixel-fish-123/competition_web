"""赛程只读接口（供 QQ 机器人插件拉取对局名单/身份）。

- GET /api/competitions/{competition_id}/schedule   指定比赛赛程（公开只读）
- GET /api/schedule/current                         当前进行中的比赛（公开只读）
- GET /competitions/{competition_id}/bracket        赛程图 HTML 页（公开只读，
  布局照抄 tournament-organizer 的 bracket.ejs：按轮次分列 + game 卡片 + 胜者加粗；
  图片由机器人插件用 web-read 对页面截图，不依赖后端装无头浏览器）

这些接口只暴露比赛展示所需的昵称与 QQ，不涉及账号敏感信息（邮箱/密码等），
因此公开只读，机器人无需登录即可拉取。
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.competition import Competition
from app.models.match import Match
from app.models.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User
from app.schemas.schedule import (
    ScheduleCompetition,
    ScheduleMatch,
    ScheduleOut,
    ScheduleParticipant,
)

router = APIRouter()

_templates_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
)
_templates = Jinja2Templates(directory=_templates_dir)


def _get_competition_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")
    return competition


def _resolve_participants(
    db: Session, competition_id: int, participant_a: int | None, participant_b: int | None
) -> tuple[ScheduleParticipant | None, ScheduleParticipant | None]:
    """解析双方参赛单位的显示名 + QQ 列表（队伍=全体成员 QQ，个体=本人 QQ）。"""

    def build(participant_id: int | None) -> ScheduleParticipant | None:
        if participant_id is None:
            return None
        reg = (
            db.query(Registration)
            .filter(
                Registration.competition_id == competition_id,
                Registration.status == "approved",
                or_(
                    Registration.team_id == participant_id,
                    Registration.user_id == participant_id,
                ),
            )
            .first()
        )
        if reg is None:
            return ScheduleParticipant(type="unknown", name=None, qqs=[])
        if reg.participant_type == "team":
            team = db.get(Team, participant_id)
            members = (
                db.query(User)
                .join(TeamMember, TeamMember.user_id == User.id)
                .filter(TeamMember.team_id == participant_id)
                .all()
            )
            return ScheduleParticipant(
                type="team",
                name=team.name if team else None,
                qqs=[u.qq for u in members if u.qq],
            )
        user = db.get(User, participant_id)
        return ScheduleParticipant(
            type="individual",
            name=(user.nickname or user.username) if user else None,
            qqs=[user.qq] if user and user.qq else [],
        )

    return build(participant_a), build(participant_b)


def _build_schedule(db: Session, competition: Competition) -> ScheduleOut:
    matches = (
        db.query(Match)
        .filter(Match.competition_id == competition.id)
        .order_by(Match.round_id, Match.id)
        .all()
    )
    out_matches: list[ScheduleMatch] = []
    for m in matches:
        a, b = _resolve_participants(db, competition.id, m.participant_a, m.participant_b)
        out_matches.append(
            ScheduleMatch(
                id=m.id,
                round_id=m.round_id,
                status=m.status,
                result_type=m.result_type,
                participant_a=a,
                participant_b=b,
            )
        )
    return ScheduleOut(competition=ScheduleCompetition.model_validate(competition), matches=out_matches)


@router.get("/api/competitions/{competition_id}/schedule", response_model=ScheduleOut)
def get_competition_schedule(competition_id: int, db: Session = Depends(get_db)) -> ScheduleOut:
    """指定比赛的赛程（公开只读）：轮次 + 每局双方单位名与 QQ。"""
    competition = _get_competition_or_404(db, competition_id)
    return _build_schedule(db, competition)


@router.get("/api/schedule/current", response_model=ScheduleOut)
def get_current_schedule(db: Session = Depends(get_db)) -> ScheduleOut:
    """当前进行中（ongoing）比赛的赛程；没有时 404。"""
    competition = (
        db.query(Competition)
        .filter(Competition.status == "ongoing")
        .order_by(Competition.id.desc())
        .first()
    )
    if competition is None:
        raise HTTPException(status_code=404, detail="当前没有进行中的比赛")
    return _build_schedule(db, competition)


def _round_name(round_id: int, total_rounds: int) -> str:
    """轮次命名，与前端 ScheduleChart.roundName 保持一致。"""
    if round_id == 1:
        return "第一轮"
    from_end = total_rounds - round_id + 1
    if from_end == 1:
        return "决赛"
    if from_end == 2:
        return "半决赛"
    if from_end == 3:
        return "八强赛"
    if from_end == 4:
        return "十六强赛"
    return f"第 {round_id} 轮"


def _bracket_context(db: Session, competition: Competition) -> dict:
    """组赛程图模板数据：轮次分列，每局含双方名字/比分/是否胜者。"""
    match_rows = (
        db.query(Match)
        .filter(Match.competition_id == competition.id)
        .order_by(Match.round_id, Match.id)
        .all()
    )
    results = {m.id: (m.result or {}) for m in match_rows}
    rounds: dict[int, dict] = {}
    for m in match_rows:
        a, b = _resolve_participants(db, competition.id, m.participant_a, m.participant_b)
        rounds.setdefault(m.round_id, {"round_id": m.round_id, "matches": []})
        result = results[m.id]
        rounds[m.round_id]["matches"].append(
            {
                "id": m.id,
                "status": m.status,
                "bye": m.participant_b is None,
                "a_name": (a.name if a else None) or "待定",
                "b_name": (b.name if b else None) if b is not None else "待定",
                "a_score": result.get("score_a") if result else None,
                "b_score": result.get("score_b") if result else None,
                "a_win": bool(
                    result
                    and result.get("winner") is not None
                    and m.participant_a is not None
                    and result["winner"] == m.participant_a
                ),
                "b_win": bool(
                    result
                    and result.get("winner") is not None
                    and m.participant_b is not None
                    and result["winner"] == m.participant_b
                ),
            }
        )
    round_list = sorted(rounds.values(), key=lambda r: r["round_id"])
    total_rounds = len(round_list)
    for r in round_list:
        r["title"] = _round_name(r["round_id"], total_rounds)
    return {
        "competition": ScheduleCompetition.model_validate(competition),
        "rounds": round_list,
    }


@router.get("/competitions/{competition_id}/bracket", response_class=HTMLResponse)
def bracket_page(competition_id: int, request: Request, db: Session = Depends(get_db)):
    """赛程图 HTML 页（公开只读）：照抄 tournament-organizer 的轮次分列布局。"""
    competition = _get_competition_or_404(db, competition_id)
    return _templates.TemplateResponse(
        request,
        "bracket.html",
        {"context": _bracket_context(db, competition)},
    )
