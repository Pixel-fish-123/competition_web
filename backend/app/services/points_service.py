"""积分服务：用户余额 + 全局榜聚合。

积分只能由管理员手动发放产生（POST /api/admin/points，kind=activity/manual，
见 api/points.py）。比赛结算已整体移除：finished 流转不自动结算、
settle_competition_points 不再存在（issue 6 用户确认，积分纯手动）。

说明：get_competition_standings 与 match_service 的引擎重建逻辑保持一致
（复用其模块级私有助手函数），避免两份实现漂移；不改动 tournaments/ 引擎。
"""

from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.competition import Competition
from app.models.point import PointTransaction
from app.models.user import User
from app.services.match_service import (
    _approved_participant_ids,
    _build_engine,
    _replay_finished,
)
from app.tournaments.base import StandingRow


# ------------------------------------------------------------ engine rebuild
# 与 match_service 相同的确定性重建（排序的已批准报名 -> 引擎 -> 回放）。
# 直接复用其模块级助手，避免引擎重建逻辑出现两份实现。


def get_competition_standings(db: Session, competition: Competition) -> list[StandingRow]:
    """确定性重建引擎并回放已完结对局，返回当前名次（best-first）。

    少于 2 名已批准选手时返回 []（引擎无法构造赛程）。
    """
    participants = _approved_participant_ids(db, competition)
    if len(participants) < 2:
        return []
    engine = _build_engine(competition, participants)
    _replay_finished(db, competition, engine)
    return engine.standings()


# --------------------------------------------------------------------- balance


def get_user_points(db: Session, user_id: int) -> float:
    """用户当前余额 = 其全部流水求和（含 competition/activity/manual）。"""
    total = (
        db.query(func.coalesce(func.sum(PointTransaction.amount), 0.0))
        .filter(PointTransaction.user_id == user_id)
        .scalar()
    )
    return float(total)


# ---------------------------------------------------------------- leaderboard


def get_leaderboard(
    db: Session, kind: str | None = None
) -> list[dict]:
    """按用户聚合的全局榜：total / competition_sum / activity_sum，total 降序。

    ``kind`` 非空时只统计该类别流水（total 也随之只含该类别）。
    仅包含至少一条流水的用户；并列按 competition_sum、user_id 稳定排序。
    """
    query = db.query(
        User.id.label("user_id"),
        User.username.label("username"),
        func.coalesce(func.sum(PointTransaction.amount), 0.0).label("total"),
        func.coalesce(
            func.sum(
                case(
                    (PointTransaction.kind == "competition", PointTransaction.amount),
                    else_=0.0,
                )
            ),
            0.0,
        ).label("competition_sum"),
        func.coalesce(
            func.sum(
                case(
                    (PointTransaction.kind == "activity", PointTransaction.amount),
                    else_=0.0,
                )
            ),
            0.0,
        ).label("activity_sum"),
    ).join(PointTransaction, PointTransaction.user_id == User.id)
    if kind:
        query = query.filter(PointTransaction.kind == kind)
    query = query.group_by(User.id, User.username).order_by(
        func.coalesce(func.sum(PointTransaction.amount), 0.0).desc(),
        func.coalesce(
            func.sum(
                case(
                    (PointTransaction.kind == "competition", PointTransaction.amount),
                    else_=0.0,
                )
            ),
            0.0,
        ).desc(),
        User.id.asc(),
    )
    return [
        {
            "user_id": row.user_id,
            "username": row.username,
            "total": float(row.total),
            "competition_sum": float(row.competition_sum),
            "activity_sum": float(row.activity_sum),
        }
        for row in query.all()
    ]
