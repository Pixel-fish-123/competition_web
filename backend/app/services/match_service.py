"""对局生命周期服务（todo 14）：赛程落地 / 开赛 / 记分。

- ``build_schedule_for_competition``: 比赛进入 ongoing 时按引擎 schedule
  生成全部 Match 行（Metis C7：对局由引擎赛程创建，非人工创建）。
- ``start_match``: 裁判开赛 -> 对局置为 in_progress（不再创建玩法会话）；
  轮空对局自动完结（记 win）。
- ``record_match_result``: 裁判记分 -> 引擎 record_result + 对局落库。

玩法插件已从对局流程解耦：开赛不再调用插件 create_session / 不再建
GameSession（模型保留仅读旧数据）；比赛后可通过 gameplay-log 导入端点把
demo 控制器导出的玩法日志存入 ``match.gameplay_log`` 供展示（不参与赛程）。

引擎一致性（关键设计）：
- participants = 已批准报名按 participant id 排序（个体=user_id，
  队伍=team_id），排序保证每次重建引擎的 seed 顺序完全一致。
- start/record 时按相同 participants + competition.format_config 重建引擎，
  并把已完成对局的结果按 engine_match_id 回放进去（单败淘汰后续轮次
  的参赛者由前序结果解析）。engine_match_id 在排表时写入 Match 行。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.ws_manager import manager
from app.models.competition import Competition
from app.models.match import Match
from app.models.registration import Registration
from app.models.user import User
from app.schemas.match import MatchResultIn
from app.tournaments.base import MatchResult, RoundPlan, TournamentEngine
from app.tournaments.round_robin import RoundRobinEngine
from app.tournaments.single_elim import SingleElimEngine
from app.tournaments.swiss import SwissEngine


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _approved_participant_ids(db: Session, competition: Competition) -> list[int]:
    """已批准报名的 participant ids，升序排序（确定性，参与引擎 seed 顺序）。"""
    registrations = (
        db.query(Registration)
        .filter(
            Registration.competition_id == competition.id,
            Registration.status == "approved",
        )
        .all()
    )
    ids = [r.team_id if r.team_id is not None else r.user_id for r in registrations]
    return sorted(ids)


def _build_engine(competition: Competition, participants: list[int]) -> TournamentEngine:
    """按 tournament_format 实例化对应赛制引擎（格式非法抛 ValueError）。"""
    config = competition.format_config or {}
    if competition.tournament_format == "round_robin":
        return RoundRobinEngine(participants, config)
    if competition.tournament_format == "swiss":
        return SwissEngine(participants, config)
    if competition.tournament_format == "single_elim":
        return SingleElimEngine(participants, config)
    raise ValueError(f"未知赛制: {competition.tournament_format!r}")


def _rebuild_engine(db: Session, competition: Competition) -> TournamentEngine:
    """按当前已批准报名确定性重建引擎（与排表时完全一致）。"""
    participants = _approved_participant_ids(db, competition)
    return _build_engine(competition, participants)


def _replay_finished(
    db: Session,
    competition: Competition,
    engine: TournamentEngine,
    skip_match_id: int | None = None,
) -> None:
    """把已完结的真实对局结果回放进引擎，保证单败淘汰后续轮次可解析。

    按 Match.id 升序回放 = 按 schedule 顺序回放（排表时 Match 行按
    schedule 迭代顺序创建），因此前序轮次总是先于后续轮次进入引擎。
    轮空对局跳过（引擎按 is_bye 自动计分）。

    ``skip_match_id``：跳过该 match_id 的回放（用于 finished 状态重新
    记分——重建引擎时不回放旧结果，避免引擎 record_result 拒绝重复记录）。
    """
    finished = (
        db.query(Match)
        .filter(
            Match.competition_id == competition.id,
            Match.status == "finished",
            Match.result_type.isnot(None),
        )
        .order_by(Match.id)
        .all()
    )
    for match in finished:
        if skip_match_id is not None and match.id == skip_match_id:
            continue  # 重新记分：跳过旧结果，让新结果能正常 record
        if match.participant_b is None and match.participant_a is not None:
            continue  # 轮空，自动计分
        result = match.result or {}
        try:
            engine.record_result(
                match.engine_match_id,
                MatchResult(
                    winner=result.get("winner"),
                    is_draw=bool(result.get("is_draw", False)),
                    score_a=result.get("score_a", 0.0),
                    score_b=result.get("score_b", 0.0),
                ),
            )
        except ValueError:
            # 数据不一致（不应发生）：跳过该局，避免阻塞其它对局。
            continue
        # 瑞士轮：每记完一局就尝试生成下一轮（上一轮未完结时返回 None）。
        # 这让引擎在回放完第 N 轮后、回放第 N+1 轮之前已把 N+1 轮物化进
        # _match_index —— 否则重建后回放第 N+1 轮结果会因 match_id 未知而
        # 被上面的 except 跳过，积分结算/名次与对局服务漂移。
        if hasattr(engine, "generate_next_round"):
            engine.generate_next_round()


def _require_assigned_referee(competition: Competition, referee: User) -> None:
    """Metis E3：裁判必须在该比赛的 referee_ids 内，否则 403。

    admin 拥有最高权限，旁路该校验（用户确认：管理员应能直接操作任何比赛）。
    """
    if referee.role == "admin":
        return
    if referee.id not in (competition.referee_ids or []):
        raise HTTPException(status_code=403, detail="非本场比赛裁判")


# ---------------------------------------------------------------- schedule


def _materialize_round(
    db: Session, competition: Competition, round_plan: RoundPlan
) -> list[Match]:
    """为引擎的某一轮生成 Match 行（幂等，无 commit）。

    - 该 (competition, round_id) 已有 Match 行 -> 直接返回 []（重复调用安全，
      并发下两个裁判先后触发 advance 也只会创建一轮）。
    - 轮空对局直接标记 finished / result_type=win（winner=participant_a）。
    - commit 由调用方统一收尾（build_schedule_for_competition /
      _advance_swiss_if_due），保证每轮整批落地、不产生半截轮次。
    """
    existing = (
        db.query(Match)
        .filter(
            Match.competition_id == competition.id,
            Match.round_id == round_plan.round_number,
        )
        .count()
    )
    if existing:
        return []

    matches: list[Match] = []
    for plan in round_plan.matches:
        match = Match(
            competition_id=competition.id,
            round_id=round_plan.round_number,
            participant_a=plan.participant_a,
            participant_b=plan.participant_b,
            engine_match_id=plan.match_id,
            status="pending",
        )
        if plan.is_bye:
            # Metis E2：轮空自动计 1 胜，不可记分。
            match.status = "finished"
            match.result_type = "win"
            match.result = {
                "winner": plan.participant_a,
                "is_draw": False,
                "score_a": 0.0,
                "score_b": 0.0,
            }
        db.add(match)
        matches.append(match)
    return matches


def _advance_swiss_if_due(db: Session, competition: Competition) -> None:
    """把瑞士轮"上一轮已完结、下一轮未落地"的轮次补进 DB（幂等）。

    必须在结果 commit 之后调用：本函数重建引擎 + 回放已完成对局（能看到
    刚提交的结果），引擎内部逐局调用 generate_next_round 推进轮次，再把引擎
    中尚无 DB 行的轮次物化，最后单次 commit 收尾。重复调用 / 并发触发安全
    （_materialize_round 幂等），修复崩溃/竞态下漏物化的轮次。
    """
    if competition.tournament_format != "swiss":
        return
    engine = _rebuild_engine(db, competition)
    _replay_finished(db, competition, engine)
    for round_plan in engine.generate_schedule():
        _materialize_round(db, competition, round_plan)
    db.commit()


def build_schedule_for_competition(
    db: Session, competition: Competition
) -> list[Match]:
    """按引擎 schedule 为比赛生成 Match 行（瑞士轮：仅生成 round 1）。

    不足 2 名已批准选手时返回空列表（允许空赛程的比赛照常流转）。
    轮空对局直接标记为 finished / result_type=win（winner=participant_a）。
    非瑞士轮引擎的 generate_schedule 返回完整赛程 -> 全部轮次一次性落地；
    瑞士轮只返回当前已物化的轮次（初始仅 round 1），后续轮次由
    ``_advance_swiss_if_due`` 在前一轮全部完结后逐轮落地。
    """
    participants = _approved_participant_ids(db, competition)
    if len(participants) < 2:
        return []

    engine = _build_engine(competition, participants)

    matches: list[Match] = []
    for round_plan in engine.generate_schedule():
        matches.extend(_materialize_round(db, competition, round_plan))
    db.commit()
    for match in matches:
        db.refresh(match)
    return matches


# ------------------------------------------------------------------- start


def start_match(
    db: Session,
    match_id: int,
    referee: User,
    scheduled_at: datetime | None = None,
) -> Match:
    """裁判开赛：校验裁判归属 -> 对局置为 in_progress（不建玩法会话）。

    玩法插件已从对局流程解耦：开赛不再调用插件 create_session / 不再创建
    GameSession。轮空对局直接完结并返回（status=finished）；单败淘汰后续
    轮次的对局参赛者由引擎根据前序已记录结果解析并回写。
    """
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    competition = db.get(Competition, match.competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")

    _require_assigned_referee(competition, referee)

    # 轮空对局：排表时已自动完结（记 win）；重复开赛幂等。
    if match.participant_b is None and match.participant_a is not None:
        if match.status != "finished":
            match.status = "finished"
            match.result_type = "win"
            match.result = {
                "winner": match.participant_a,
                "is_draw": False,
                "score_a": 0.0,
                "score_b": 0.0,
            }
            match.referee_id = referee.id
            db.commit()
        return match

    if match.status != "pending":
        raise HTTPException(status_code=400, detail="对局不在待开始状态")

    if scheduled_at is not None:
        match.scheduled_at = scheduled_at

    # 解析本局两名真实参赛者（单败淘汰后续轮次排表时未知）。
    participant_a, participant_b = match.participant_a, match.participant_b
    if participant_a is None or participant_b is None:
        engine = _rebuild_engine(db, competition)
        _replay_finished(db, competition, engine)
        try:
            participant_a, participant_b = engine._resolve_participants(
                match.engine_match_id
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        # 回写解析出的真实参赛者到 Match 行（单败淘汰后续轮次排表时两列为
        # None），随下方 commit 落库，保证前端 match 接口能读到 participant_id。
        match.participant_a = participant_a
        match.participant_b = participant_b

    match.status = "in_progress"
    match.referee_id = referee.id
    db.commit()
    db.refresh(match)

    # 对局已开赛：通知订阅该对局的 WS 客户端（不再推送玩法棋盘状态）。
    manager.broadcast(match.id, {"type": "match_started", "match_id": match.id})
    return match


# ------------------------------------------------------------------ result


def record_match_result(
    db: Session, match_id: int, payload: MatchResultIn, referee: User
) -> Match:
    """裁判记分：单败淘汰禁平局（Metis E1）-> 引擎 record_result -> 落库。

    引擎状态通过"重建 + 回放已完成对局"恢复，保证单败淘汰后续轮次的
    胜者/参与者校验与排位推进一致。
    """
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    competition = db.get(Competition, match.competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")

    _require_assigned_referee(competition, referee)

    # 允许 in_progress（首次记分）和 finished（人工修改结果）两种状态。
    # finished 重新记分时，重建引擎需跳过当前 match 的旧结果（否则引擎
    # record_result 拒绝重复记录），见下方 _replay_finished(skip_match_id)。
    if match.status not in ("in_progress", "finished"):
        raise HTTPException(status_code=400, detail="对局未进行中或已结束")

    is_rerecord = match.status == "finished"

    if competition.tournament_format == "single_elim" and payload.is_draw:
        # Metis E1：单败淘汰必须分胜负。
        raise HTTPException(
            status_code=400, detail="单败淘汰不允许平局，裁判须指定胜者"
        )

    engine = _rebuild_engine(db, competition)
    # finished 重新记分时跳过当前 match 的旧结果回放，避免引擎拒绝重复记录。
    _replay_finished(db, competition, engine, skip_match_id=match.id if is_rerecord else None)

    engine_result = MatchResult(
        winner=payload.winner,
        is_draw=payload.is_draw,
        score_a=payload.score_a,
        score_b=payload.score_b,
    )
    try:
        engine.record_result(match.engine_match_id, engine_result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    match.result = {
        "winner": payload.winner,
        "is_draw": payload.is_draw,
        "score_a": payload.score_a,
        "score_b": payload.score_b,
    }
    match.result_type = "draw" if payload.is_draw else "win"
    match.status = "finished"
    db.commit()
    db.refresh(match)

    # 记分完成：把最终结果推送给订阅该对局的 WS 客户端（仅比分通知，
    # 不再推送玩法棋盘状态）。
    manager.broadcast(
        match.id,
        {
            "type": "score_update",
            "match_id": match.id,
            "result": match.result,
            "status": "finished",
        },
    )

    # 瑞士轮：最后一局结果提交后，把下一轮对局物化进 DB。post-commit 的
    # fresh-check（非同一事务内）是刻意的 —— 重建引擎能看到刚提交的结果，
    # 且并发裁判同时提交时，后到者的 advance 会因 _materialize_round 幂等
    # 而只创建一轮对局。
    if competition.tournament_format == "swiss":
        _advance_swiss_if_due(db, competition)
    return match
