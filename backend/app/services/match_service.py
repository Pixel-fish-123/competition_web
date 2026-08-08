"""对局生命周期服务（todo 14）：赛程落地 / 开赛 / 记分。

- ``build_schedule_for_competition``: 比赛进入 ongoing 时按引擎 schedule
  生成全部 Match 行（Metis C7：对局由引擎赛程创建，非人工创建）。
- ``start_match``: 裁判开赛 -> 对局置为 in_progress（不再创建玩法会话）；
  轮空对局自动完结（记 win）。
- ``record_match_result``: 裁判记分 -> 引擎 record_result + 对局落库。

玩法插件已从对局流程解耦：开赛不创建任何玩法会话；比赛后可通过
gameplay-log 导入端点把 demo 控制器导出的玩法日志存入 ``match.gameplay_log``
供展示（不参与赛程）。

引擎一致性（关键设计）：
- participants = 已批准报名按 participant id 排序（个体=user_id，
  队伍=team_id），排序保证每次重建引擎的 seed 顺序完全一致。
- start/record 时按相同 participants + competition.format_config 重建引擎，
  并把已完成对局的结果按 engine_match_id 回放进去（单败淘汰后续轮次
  的参赛者由前序结果解析）。engine_match_id 在排表时写入 Match 行。
"""

from __future__ import annotations

import random
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.ws_manager import manager
from app.models.competition import Competition
from app.models.match import Match
from app.models.registration import Registration
from app.models.user import User
from app.schemas.match import MatchResultIn
from app.tournaments.base import MatchResult, RoundPlan, TournamentEngine
from app.tournaments.single_elim import SingleElimEngine
from app.tournaments.swiss import SwissEngine


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
                _align_scores_to_engine(match, engine, result),
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


def _round_real_matches(db: Session, competition: Competition, round_id: int) -> list[Match]:
    """某轮的全部真实对局（排除轮空行）。"""
    return (
        db.query(Match)
        .filter(
            Match.competition_id == competition.id,
            Match.round_id == round_id,
            Match.participant_b.isnot(None),
        )
        .all()
    )


def lock_round(
    db: Session,
    competition: Competition,
    round_id: int,
    staff: User,
    commit: bool = True,
) -> int:
    """按轮次锁定：该轮全部真实对局结束后才能锁定整轮结果。

    返回被锁定的对局数。已锁定的对局保持锁定（幂等）。``commit=False``
    时由调用方统一收尾（complete_round 单事务原子提交）。
    """
    _require_assigned_referee(competition, staff)
    real_matches = _round_real_matches(db, competition, round_id)
    if not real_matches:
        raise HTTPException(status_code=400, detail="该轮没有可锁定的对局")
    unfinished = [m for m in real_matches if m.status != "finished"]
    if unfinished:
        raise HTTPException(status_code=400, detail="本轮尚未全部结束，无法锁定结果")

    locked = 0
    for match in real_matches:
        if not match.result_locked:
            match.result_locked = True
            locked += 1
    if commit:
        db.commit()
    return locked


def complete_round(
    db: Session,
    competition: Competition,
    round_id: int,
    staff: User,
) -> tuple[int, int | None]:
    """结束本轮（「开始下一轮」按钮）：锁定本轮全部结果 + 推进下一轮。

    瑞士轮下一轮在锁定后才物化（先锁定、后按最终结果生成配对，避免
    下一轮已生成却还能改本轮结果的竞态 bug）；单败淘汰完整赛程已在排表时
    落地，本轮锁定后下一轮直接可开赛。

    只允许结束最新一轮（防止绕开 UI 直接补锁旧轮导致后续轮次配对基于
    未锁定结果）；锁定与推进在同一事务提交，失败时整体回滚、可重试。

    返回 (locked_count, next_round_id)；next_round_id 为 None 表示已是最后一轮。
    """
    _require_assigned_referee(competition, staff)

    latest = (
        db.query(Match)
        .filter(Match.competition_id == competition.id)
        .order_by(Match.round_id.desc())
        .first()
    )
    if latest is None or latest.round_id != round_id:
        raise HTTPException(status_code=400, detail="只能结束最新一轮")

    locked = lock_round(db, competition, round_id, staff, commit=False)
    if competition.tournament_format == "swiss":
        # 上一轮已锁定并提交结果，引擎回放后把下一轮物化进 DB（不单独提交）。
        _advance_swiss_if_due(db, competition, commit=False)
    db.commit()
    next_round = (
        db.query(Match.round_id)
        .filter(
            Match.competition_id == competition.id,
            Match.round_id > round_id,
        )
        .order_by(Match.round_id.asc())
        .first()
    )
    return locked, (next_round[0] if next_round else None)


def reset_latest_round(
    db: Session,
    competition: Competition,
    staff: User,
) -> tuple[int, list[Match]]:
    """重置最新一轮的对局安排：删除该轮全部对局行，重建引擎后重新生成。

    - 仅允许重置最新一轮（其后没有更多轮次，避免 engine_match_id 断裂）。
    - 该轮存在已锁定结果时拒绝（锁定后不可重置）。
    - 重建引擎确定性回放已完成对局（engine_match_id 保持不变），排行榜
      经回放机制自动按新赛程更新积分/胜负。
    """
    _require_assigned_referee(competition, staff)

    latest = (
        db.query(Match)
        .filter(Match.competition_id == competition.id)
        .order_by(Match.round_id.desc())
        .first()
    )
    if latest is None:
        raise HTTPException(status_code=400, detail="暂无对局可重置")

    round_id = latest.round_id
    round_matches = (
        db.query(Match)
        .filter(
            Match.competition_id == competition.id,
            Match.round_id == round_id,
        )
        .all()
    )
    if any(m.result_locked for m in round_matches):
        raise HTTPException(status_code=400, detail="本轮已有锁定结果，无法重置")

    for match in round_matches:
        db.delete(match)
    db.commit()

    # 重建引擎并回放剩余已完成对局（前一/几轮），再物化全部已生成轮次：
    # 已存在轮次幂等跳过，最新一轮按引擎确定性重新生成。
    engine = _rebuild_engine(db, competition)
    _replay_finished(db, competition, engine)
    created: list[Match] = []
    for round_plan in engine.generate_schedule():
        created.extend(_materialize_round(db, competition, round_plan))
    db.commit()
    for match in created:
        db.refresh(match)
    return round_id, created


def _align_scores_to_engine(
    match: Match, engine: TournamentEngine, result: dict
) -> MatchResult:
    """把 DB 行保存的结果按引擎 schedule 的 participant 顺序对齐。

    随机选边（issue 2）会交换 Match.participant_a/b，而引擎 MatchPlan 的
    顺序在排表时固定。回放/记分时须把 score_a/score_b 归位到引擎坐标系，
    否则净胜分（net_score）会归属错误。winner 是 participant id（全局唯一），
    无需对齐；is_bye 行不会走到这里。
    """
    plan = engine._match_index.get(match.engine_match_id)
    score_a = result.get("score_a", 0.0)
    score_b = result.get("score_b", 0.0)
    if plan is not None and match.participant_a != plan.participant_a:
        score_a, score_b = score_b, score_a
    return MatchResult(
        winner=result.get("winner"),
        is_draw=bool(result.get("is_draw", False)),
        score_a=score_a,
        score_b=score_b,
    )


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


def _advance_swiss_if_due(db: Session, competition: Competition, commit: bool = True) -> None:
    """把瑞士轮"上一轮已完结、下一轮未落地"的轮次补进 DB（幂等）。

    必须在结果 commit 之后调用：本函数重建引擎 + 回放已完成对局（能看到
    刚提交的结果），引擎内部逐局调用 generate_next_round 推进轮次，再把引擎
    中尚无 DB 行的轮次物化，最后单次 commit 收尾。重复调用 / 并发触发安全
    （_materialize_round 幂等），修复崩溃/竞态下漏物化的轮次。

    ``commit=False`` 时跳过收尾提交（complete_round 单事务原子提交用）。
    """
    if competition.tournament_format != "swiss":
        return
    if len(_approved_participant_ids(db, competition)) < 2:
        return  # 无赛程可推进（空比赛 finish 也应放行，issue 8）
    engine = _rebuild_engine(db, competition)
    _replay_finished(db, competition, engine)
    for round_plan in engine.generate_schedule():
        _materialize_round(db, competition, round_plan)
    if commit:
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


def randomize_sides(
    db: Session,
    match_id: int,
    referee: User,
) -> tuple[Match, bool]:
    """开赛前随机选边（issue 2）：等概率交换对局双方的阵营。

    掠夺者=participant_a、守护者=participant_b。仅对双方已确定（均非 None）
    且未开始（pending）的对局生效；交换仅影响展示与引擎分数对齐
    （``_align_scores_to_engine`` 保证净胜分归属正确）。返回
    (match, swapped) —— swapped 表示本次是否实际交换了顺序。
    """
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    competition = db.get(Competition, match.competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")

    _require_assigned_referee(competition, referee)

    if match.participant_a is None or match.participant_b is None:
        raise HTTPException(status_code=400, detail="对局双方尚未确定，无法随机选边")
    if match.status != "pending":
        raise HTTPException(status_code=400, detail="仅未开始的比赛可以进行随机选边")

    swapped = random.random() < 0.5
    if swapped:
        match.participant_a, match.participant_b = (
            match.participant_b,
            match.participant_a,
        )
        db.commit()
        db.refresh(match)
    return match, swapped


def start_match(
    db: Session,
    match_id: int,
    referee: User,
    scheduled_at: datetime | None = None,
) -> Match:
    """裁判开赛：校验裁判归属 -> 对局置为 in_progress（不建玩法会话）。

    轮空对局直接完结并返回（status=finished）；单败淘汰后续轮次的对局
    参赛者由引擎根据前序已记录结果解析并回写。
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

    issue 14：``payload.lock`` 为 true 时保存结果并锁定 —— 锁定后任何
    再次 /result 均返回 400（结果已确定，无法更改）。
    """
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    competition = db.get(Competition, match.competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="比赛不存在")

    _require_assigned_referee(competition, referee)

    if match.result_locked:
        raise HTTPException(status_code=400, detail="结果已锁定，无法更改")

    # 按轮次锁定（用户确认）：lock=true 仅当本轮全部真实对局结束后才接受。
    if payload.lock:
        unfinished = [
            m
            for m in _round_real_matches(db, competition, match.round_id)
            if m.status != "finished"
        ]
        if unfinished:
            raise HTTPException(status_code=400, detail="本轮尚未全部结束，无法锁定结果")

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

    engine_result = _align_scores_to_engine(
        match,
        engine,
        {
            "winner": payload.winner,
            "is_draw": payload.is_draw,
            "score_a": payload.score_a,
            "score_b": payload.score_b,
        },
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
    if payload.lock:
        match.result_locked = True
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
    return match
