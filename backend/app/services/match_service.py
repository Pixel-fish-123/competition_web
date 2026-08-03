"""对局生命周期服务（todo 14）：赛程落地 / 开赛 / 记分。

- ``build_schedule_for_competition``: 比赛进入 ongoing 时按引擎 schedule
  生成全部 Match 行（Metis C7：对局由引擎赛程创建，非人工创建）。
- ``start_match``: 裁判开赛 -> 创建 GameSession（插件 create_session）；
  轮空对局自动完结（记 win，不建会话）。
- ``record_match_result``: 裁判记分 -> 引擎 record_result + 对局落库。

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
from app.models.match import GameSession, Match
from app.models.registration import Registration
from app.models.user import User
from app.plugins.registry import registry
from app.schemas.match import MatchResultIn
from app.tournaments.base import MatchResult, TournamentEngine
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


def _replay_finished(db: Session, competition: Competition, engine: TournamentEngine) -> None:
    """把已完结的真实对局结果回放进引擎，保证单败淘汰后续轮次可解析。

    按 Match.id 升序回放 = 按 schedule 顺序回放（排表时 Match 行按
    schedule 迭代顺序创建），因此前序轮次总是先于后续轮次进入引擎。
    轮空对局跳过（引擎按 is_bye 自动计分）。
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


def _require_assigned_referee(competition: Competition, referee: User) -> None:
    """Metis E3：裁判必须在该比赛的 referee_ids 内，否则 403。

    admin 拥有最高权限，旁路该校验（用户确认：管理员应能直接操作任何比赛）。
    """
    if referee.role == "admin":
        return
    if referee.id not in (competition.referee_ids or []):
        raise HTTPException(status_code=403, detail="非本场比赛裁判")


# ---------------------------------------------------------------- schedule


def build_schedule_for_competition(
    db: Session, competition: Competition
) -> list[Match]:
    """按引擎 schedule 为比赛生成全部 Match 行。

    不足 2 名已批准选手时返回空列表（允许空赛程的比赛照常流转）。
    轮空对局直接标记为 finished / result_type=win（winner=participant_a）。
    """
    participants = _approved_participant_ids(db, competition)
    if len(participants) < 2:
        return []

    engine = _build_engine(competition, participants)
    schedule = engine.generate_schedule()

    matches: list[Match] = []
    for round_plan in schedule:
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
) -> GameSession | None:
    """裁判开赛：校验裁判归属 -> 创建 GameSession（插件 create_session）。

    轮空对局直接完结并返回 None（无会话）；单败淘汰后续轮次的对局参赛者
    由引擎根据前序已记录结果解析。
    """
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    competition = db.get(Competition, match.competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")

    _require_assigned_referee(competition, referee)

    # 轮空对局：排表时已自动完结（记 win，不建会话）；重复开赛幂等。
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
        return None

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

    plugin = registry.get(competition.gameplay_plugin)
    if plugin is None:
        raise HTTPException(status_code=404, detail="玩法插件不存在")

    config = {
        "song_lib": competition.song_lib,
        "seed": match.id,
        "sides": {participant_a: "defender", participant_b: "attacker"},
    }
    try:
        state = plugin.create_session(match.id, config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session = GameSession(
        match_id=match.id,
        plugin_name=plugin.name,
        config=config,
        state_json=state,
        started_at=_utcnow(),
    )
    db.add(session)
    match.status = "in_progress"
    match.referee_id = referee.id
    db.commit()
    db.refresh(session)

    # todo 15：开赛后把最新会话状态实时推送给已订阅该对局的 WS 客户端。
    plugin = registry.get(session.plugin_name)
    state = session.state_json
    if plugin is not None:
        try:
            state = plugin.get_state(session.id, session.state_json)
        except ValueError:
            pass
    manager.broadcast(
        match.id,
        {"type": "state_update", "session_id": session.id, "state": state},
    )
    return session


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

    if match.status != "in_progress":
        raise HTTPException(status_code=400, detail="对局未进行中")

    if competition.tournament_format == "single_elim" and payload.is_draw:
        # Metis E1：单败淘汰必须分胜负。
        raise HTTPException(
            status_code=400, detail="单败淘汰不允许平局，裁判须指定胜者"
        )

    engine = _rebuild_engine(db, competition)
    _replay_finished(db, competition, engine)

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
    return match
