"""排行榜 API（todo 17）：场次排名 + 全局榜。

- GET /api/rankings/competition/{id}   任意登录用户：按引擎 standings 返回
  该比赛当前名次（与 match_service 相同的确定性重建 + 回放），并解析
  参赛单位名称（个体=用户名，队伍=队名）。
- GET /api/rankings/global             任意登录用户：全局榜（复用积分
  leaderboard 聚合逻辑，与 /api/points/leaderboard 完全一致）。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user
from app.db import get_db
from app.models.competition import Competition
from app.models.registration import Registration
from app.models.team import Team
from app.models.user import User
from app.schemas.point import LeaderboardRow
from app.services import points_service

router = APIRouter()


def _get_competition_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")
    return competition


@router.get("/api/rankings/competition/{competition_id}")
def competition_rankings(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """该比赛当前名次（best-first，rank 从 1 开始）。

    依据：已批准报名重建引擎 + 回放已完结对局（与 match_service 一致的
    确定性流程），standings() 即当前排名。无需比赛已结束即可查看。
    """
    competition = _get_competition_or_404(db, competition_id)

    # 参赛单位 id -> 名称（个体=用户名，队伍=队名）。
    regs = (
        db.query(Registration)
        .filter(
            Registration.competition_id == competition.id,
            Registration.status == "approved",
        )
        .all()
    )
    names: dict[int, str | None] = {}
    team_cache: dict[int, str] = {}
    for reg in regs:
        participant_id = reg.team_id or reg.user_id
        if reg.participant_type == "team":
            if reg.team_id not in team_cache:
                team = db.get(Team, reg.team_id)
                team_cache[reg.team_id] = team.name if team is not None else None
            names[participant_id] = team_cache[reg.team_id]
        else:
            user = db.get(User, reg.user_id)
            names[participant_id] = user.username if user is not None else None

    standings = points_service.get_competition_standings(db, competition)
    return [
        {
            "rank": rank,
            "participant_id": row.participant_id,
            "participant_name": names.get(row.participant_id),
            "wins": row.wins,
            "net_score": row.net_score,
            "opponent_wins": row.opponent_wins,
        }
        for rank, row in enumerate(standings, start=1)
    ]


@router.get("/api/rankings/global", response_model=list[LeaderboardRow])
def global_rankings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """全局榜：与 /api/points/leaderboard 完全一致（委托同一聚合）。"""
    return points_service.get_leaderboard(db)
