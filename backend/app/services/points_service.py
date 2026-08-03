"""积分服务：比赛结算（仅手动/测试调用）+ 用户余额 + 全局榜聚合。

比赛结算（``settle_competition_points``）设计：

- 积分改为 admin 纯手动发放（用户确认 ①A）：competitions 的 finished
  流转已移除自动结算调用；本函数保留供手动/测试直接调用，不再被任何
  API 端点自动触发。
- 幂等：同一比赛已存在 ``kind == "competition"`` 的流水则直接返回 []，
  绝不重复入账（流水只能由系统产生，见 plan.md Must NOT）。
- 结算依据：与 match_service 完全一致的「确定性重建引擎 + 回放已完结对局
  」流程 —— ``_approved_participant_ids``（已批准报名按 participant id
  排序，个体=user_id、队伍=team_id）+ ``_build_engine``（round_robin /
  swiss / single_elim）+ ``_replay_finished``（按 Match.id 升序回放）。
  引擎 standings() 即最终名次（best-first）。
- 积分规则：``competition.points_rule`` 为 {名次(str) -> 积分} dict，
  如 {"1": 100, "2": 60, "3": 40, "default": 10}。第 N 名取 rule[str(N)]，
  无该名次时取 rule["default"]，再无则 0（不产生流水）。
- 队伍奖励（Metis C6/E15）：队伍参赛单位获奖时，队内每位成员各得该名次
  全额积分（不拆分）；reason 记「比赛名次·第N名·队伍<队名>」。
  个体记「比赛名次·第N名」。

说明：本服务与 match_service 的引擎重建逻辑保持一致（复用其模块级私有
助手函数），避免两份实现漂移；不改动 tournaments/ 引擎与 plugins/。
"""

from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.audit import log_audit
from app.models.competition import Competition
from app.models.match import Match
from app.models.point import PointTransaction
from app.models.registration import Registration
from app.models.team import Team, TeamMember
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


# ------------------------------------------------------------------ settlement


def settle_competition_points(
    db: Session, competition: Competition
) -> list[PointTransaction]:
    """按 points_rule 结算比赛积分；幂等。

    .. note::
        不再自动调用（competitions finished 流转已移除自动结算），保留供
        手动/测试调用。

    - 已存在该比赛的 competition 流水 -> 直接返回 []（不重复结算）。
    - 存在未完成对局 -> raise ValueError("存在未完成的对局，无法结算")。
    - 否则：重建引擎 -> standings -> 按名次应用 points_rule -> 为每个参赛
      单位创建流水（队伍 = 每位成员各全额）。提交后写审计日志。
    """
    existing = (
        db.query(PointTransaction)
        .filter(
            PointTransaction.ref_competition_id == competition.id,
            PointTransaction.kind == "competition",
        )
        .count()
    )
    if existing:
        return []

    unfinished = (
        db.query(Match)
        .filter(
            Match.competition_id == competition.id,
            Match.status != "finished",
        )
        .count()
    )
    if unfinished:
        raise ValueError("存在未完成的对局，无法结算")

    standings = get_competition_standings(db, competition)
    if not standings:
        return []  # 少于 2 名参赛者：无赛程可排，无积分可结。

    rule = competition.points_rule or {}
    default_points = float(rule.get("default", 0))

    regs = (
        db.query(Registration)
        .filter(
            Registration.competition_id == competition.id,
            Registration.status == "approved",
        )
        .all()
    )
    reg_by_participant: dict[int, Registration] = {}
    for reg in regs:
        reg_by_participant[reg.team_id or reg.user_id] = reg
    team_cache: dict[int, Team | None] = {}

    transactions: list[PointTransaction] = []
    for rank, row in enumerate(standings, start=1):
        reg = reg_by_participant.get(row.participant_id)
        if reg is None:
            continue
        points = float(rule.get(str(rank), default_points))
        if not points:
            continue
        if reg.participant_type == "team":
            team = team_cache.get(reg.team_id)
            if team is None and reg.team_id is not None:
                team = db.get(Team, reg.team_id)
                team_cache[reg.team_id] = team
            team_name = team.name if team is not None else f"#{reg.team_id}"
            reason = f"比赛名次·第{rank}名·队伍{team_name}"
            # Metis C6/E15：队伍奖励 = 每位成员各得全额，不拆分。
            members = (
                db.query(TeamMember)
                .filter(TeamMember.team_id == reg.team_id)
                .all()
            )
            for member in members:
                transactions.append(
                    PointTransaction(
                        user_id=member.user_id,
                        amount=points,
                        kind="competition",
                        ref_competition_id=competition.id,
                        reason=reason,
                        created_by=competition.created_by,
                    )
                )
        else:
            transactions.append(
                PointTransaction(
                    user_id=reg.user_id,
                    amount=points,
                    kind="competition",
                    ref_competition_id=competition.id,
                    reason=f"比赛名次·第{rank}名",
                    created_by=competition.created_by,
                )
            )

    for tx in transactions:
        db.add(tx)
    db.commit()
    for tx in transactions:
        db.refresh(tx)
    log_audit(
        db,
        competition.created_by,
        "competition_settle",
        detail={
            "competition_id": competition.id,
            "competition": competition.name,
            "transactions": len(transactions),
        },
    )
    return transactions


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
