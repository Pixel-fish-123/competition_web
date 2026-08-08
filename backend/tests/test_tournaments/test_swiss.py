"""瑞士轮引擎 (Swiss) tests — todo 10.

TDD suite for ``app/tournaments/swiss.py``. Pure algorithm tests — no DB, no
network. Coverage:

- TRUE Swiss semantics: only round 1 exists at construction; each later round
  is materialized by ``generate_next_round()`` ONLY once the previous round is
  fully recorded, and pairs by the CURRENT standings (points → Buchholz → net
  → seed) — round 2+ pairings depend on recorded results, not a fixed seed
  schedule
- deterministic rebuild: replaying the same results into a fresh engine
  reproduces identical pairings AND match_ids (match_id determinism is the #1
  rebuild risk)
- odd fields: exactly one bye per round, bye to the lowest-ranked participant
  that has not yet had one, no double bye, bye = 1 point / 0 net
- Metis E1 draw semantics: 0.5 points for both sides
- full recording: standings sorted by points, undefeated champion on top
- Buchholz (对手分) tie-break: equal points + net, higher Buchholz ranks above
- standings correctness after each round (points + Buchholz)
- Metis V1 ordering: points desc → Buchholz desc → net desc → seed asc
- input / config validation
- completion and round-advance behaviour
"""

import math

import pytest

from app.tournaments.base import MatchResult
from app.tournaments.swiss import SwissEngine


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _real_matches(schedule):
    """All non-bye matches across the given rounds."""
    return [m for r in schedule for m in r.matches if not m.is_bye]


def _pairs_of(plan):
    """Pair set of a round's real matches."""
    return {frozenset((m.participant_a, m.participant_b)) for m in plan.matches if not m.is_bye}


def _record_round(engine, round_number, choose_winner):
    """Record every real match of an existing round, advancing to the next."""
    plan = engine.generate_schedule()[round_number - 1]
    for m in plan.matches:
        if m.is_bye:
            continue
        winner = choose_winner(m.participant_a, m.participant_b)
        if m.participant_a == winner:
            engine.record_result(m.match_id, MatchResult(winner=winner, score_a=1, score_b=0))
        else:
            engine.record_result(m.match_id, MatchResult(winner=winner, score_a=0, score_b=1))
    return engine.generate_next_round()


def _play_round_and_return(engine, round_number, choose_winner):
    """Like ``_record_round`` but also returns the recorded (match_id, result)
    pairs in replay order (for rebuild-determinism replay)."""
    plan = engine.generate_schedule()[round_number - 1]
    played = []
    for m in plan.matches:
        if m.is_bye:
            continue
        winner = choose_winner(m.participant_a, m.participant_b)
        if m.participant_a == winner:
            res = MatchResult(winner=winner, score_a=1, score_b=0)
        else:
            res = MatchResult(winner=winner, score_a=0, score_b=1)
        engine.record_result(m.match_id, res)
        played.append((m.match_id, res))
    engine.generate_next_round()
    return played


# --------------------------------------------------------------------------- #
# scheduling: round 1 = seed order, round 2+ = result-dependent
# --------------------------------------------------------------------------- #


def test_default_rounds_and_no_repeated_opponents_eight_players():
    """8 players / config {} → min(ceil(log2(8))+1, 7) = 4 rounds.

    Round 1 is seed order ((1,2),(3,4),(5,6),(7,8)). After round 1 is recorded,
    ``generate_next_round`` materializes round 2 whose pairings follow the
    round-1 standings (NOT the fixed seed-order schedule); no opponent pair
    repeats across the materialized rounds; every participant appears exactly
    once per round.
    """
    engine = SwissEngine([1, 2, 3, 4, 5, 6, 7, 8], {})
    assert engine._rounds == 4
    assert len(engine.generate_schedule()) == 1  # only round 1 at construction

    r1 = engine.generate_schedule()[0]
    assert r1.round_number == 1
    assert _pairs_of(r1) == {frozenset((1, 2)), frozenset((3, 4)), frozenset((5, 6)), frozenset((7, 8))}

    # Round 1 winners {1, 4, 5, 7} — deliberately mixed so the round-2 pairing
    # is NOT the fixed seed-order round 2 of the old engine.
    r1_winners = {1: 1, 3: 4, 5: 5, 7: 7}  # keyed by round-1 participant_a
    for m in r1.matches:
        winner = r1_winners[m.participant_a]
        if m.participant_a == winner:
            engine.record_result(m.match_id, MatchResult(winner=winner, score_a=1, score_b=0))
        else:
            engine.record_result(m.match_id, MatchResult(winner=winner, score_a=0, score_b=1))
    r2 = engine.generate_next_round()
    assert r2 is not None and r2.round_number == 2

    # Round 2 is standings-based, NOT the fixed seed-order round: the old
    # engine's round 2 was {(1,3),(2,4),(5,7),(6,8)}.
    r2_pairs = _pairs_of(r2)
    assert r2_pairs != {frozenset((1, 3)), frozenset((2, 4)), frozenset((5, 7)), frozenset((6, 8))}
    assert len(r2_pairs) == 4

    # No opponent pair repeats across the materialized rounds.
    all_pairs = {
        frozenset((m.participant_a, m.participant_b))
        for m in _real_matches(engine.generate_schedule())
    }
    assert len(all_pairs) == 8

    for pid in range(1, 9):
        for r in engine.generate_schedule():
            round_pids = {m.participant_a for m in r.matches} | {m.participant_b for m in r.matches}
            assert pid in round_pids


def test_round2_pairings_depend_on_round1_results():
    """THE Swiss property: two different round-1 result sets produce two
    different round-2 pairings (pairings are not fixed at construction)."""
    def engine_with(r1_winners):
        engine = SwissEngine([1, 2, 3, 4, 5, 6, 7, 8], {})
        r1 = engine.generate_schedule()[0]
        for m in r1.matches:
            winner = r1_winners[m.participant_a]  # keyed by round-1 participant_a
            if m.participant_a == winner:
                engine.record_result(m.match_id, MatchResult(winner=winner, score_a=1, score_b=0))
            else:
                engine.record_result(m.match_id, MatchResult(winner=winner, score_a=0, score_b=1))
        return engine, engine.generate_next_round()

    # All lower seeds win → winners {1,3,5,7}.
    engine_a, r2_a = engine_with({1: 1, 3: 3, 5: 5, 7: 7})
    # Mixed winners {1,4,5,7} (3 loses to 4).
    engine_b, r2_b = engine_with({1: 1, 3: 4, 5: 5, 7: 7})

    pairs_a = _pairs_of(r2_a)
    pairs_b = _pairs_of(r2_b)
    assert len(pairs_a) == len(pairs_b) == 4
    assert pairs_a != pairs_b
    # And the concrete traced pairings: standings-based round 2 vs seed group.
    assert pairs_a == {frozenset((1, 3)), frozenset((5, 7)), frozenset((2, 4)), frozenset((6, 8))}
    assert pairs_b == {frozenset((1, 4)), frozenset((5, 7)), frozenset((2, 3)), frozenset((6, 8))}


def test_generate_next_round_gating():
    """generate_next_round returns None while the previous round is incomplete
    and after the configured round count is reached."""
    engine = SwissEngine([1, 2, 3, 4], {})  # 3 rounds
    assert len(engine.generate_schedule()) == 1

    # Half-recorded round 1 → still None.
    r1 = engine.generate_schedule()[0]
    m0 = r1.matches[0]
    engine.record_result(m0.match_id, MatchResult(winner=m0.participant_a))
    assert engine.generate_next_round() is None
    assert len(engine.generate_schedule()) == 1

    # Round 1 fully recorded → round 2 materializes.
    m1 = r1.matches[1]
    engine.record_result(m1.match_id, MatchResult(winner=m1.participant_a))
    assert engine.generate_next_round().round_number == 2

    # Round 2 fully recorded → round 3 materializes.
    for m in engine.generate_schedule()[1].matches:
        engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
    assert engine.generate_next_round().round_number == 3

    # All rounds materialized → None, even with a pending last round.
    assert engine.generate_next_round() is None

    # And after the last round is recorded → still None.
    for m in engine.generate_schedule()[2].matches:
        engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
    assert engine.generate_next_round() is None
    assert engine.is_complete() is True


# --------------------------------------------------------------------------- #
# odd fields / byes
# --------------------------------------------------------------------------- #


def test_five_players_one_bye_per_round_no_double_bye():
    """5 players / config {} → 4 rounds (min(ceil(log2(5))+1, 7)). Each round
    has exactly one bye, no participant receives a second bye (4 byes over 5
    players). 比赛未开始（尚无任何真实对局结果）时轮空不计分（0/0/0）；
    出现第一场真实结果后轮空才计 1 分 / 0 净分。"""
    engine = SwissEngine([1, 2, 3, 4, 5], {})
    assert engine._rounds == 4

    bye_recipients = []
    for round_number in range(1, 5):
        plan = engine.generate_schedule()[round_number - 1]
        byes = [m for m in plan.matches if m.is_bye]
        assert len(byes) == 1
        recipient = byes[0].participant_a
        assert recipient not in bye_recipients  # no double bye
        bye_recipients.append(recipient)
        assert len([m for m in plan.matches if not m.is_bye]) == 2
        if round_number == 1:
            # 比赛未开始（无真实结果）：轮空不计分。
            by_id = {row.participant_id: row for row in engine.standings()}
            assert by_id[recipient].wins == 0.0
            assert by_id[recipient].points == 0.0
        _record_round(engine, round_number, lambda a, b: min(a, b))

    assert len(bye_recipients) == 4
    assert set(bye_recipients) <= set(range(1, 6))

    # 出现真实结果后，轮空正常计 1 分（每个轮空受益者至少 1 胜）。
    by_id = {row.participant_id: row for row in engine.standings()}
    for pid in bye_recipients:
        assert by_id[pid].wins >= 1.0


def test_bye_counts_only_after_its_round_starts():
    """需求 3（用户确认）：轮空计分按轮次门槛 —— 轮空所在轮次已有真实对局
    结果（该轮已开始）才计分；下一轮虽已物化但尚未开打时，其轮空不提前加分。"""
    engine = SwissEngine([1, 2, 3, 4, 5], {})
    r1 = engine.generate_schedule()[0]
    r1_bye = next(m for m in r1.matches if m.is_bye)
    r1_real = [m for m in r1.matches if not m.is_bye]

    # 比赛未开始：全部 0。
    by_id = {row.participant_id: row for row in engine.standings()}
    assert by_id[r1_bye.participant_a].wins == 0.0
    assert by_id[r1_bye.participant_a].points == 0.0

    # 第 1 轮第一场真实结果落地：第 1 轮轮空计 1 胜 / 1 分。
    engine.record_result(r1_real[0].match_id, MatchResult(winner=r1_real[0].participant_a))
    by_id = {row.participant_id: row for row in engine.standings()}
    assert by_id[r1_bye.participant_a].wins == 1.0
    assert by_id[r1_bye.participant_a].points == 1.0

    # 打完第 1 轮 -> 第 2 轮物化（5 人第 2 轮也有轮空）。
    engine.record_result(r1_real[1].match_id, MatchResult(winner=r1_real[1].participant_a))
    r2 = engine.generate_next_round()
    assert r2 is not None and r2.round_number == 2
    r2_bye = next(m for m in r2.matches if m.is_bye)

    # 第 2 轮尚未开打：第 2 轮轮空不计分（第 1 轮轮空仍正常计分）。
    by_id = {row.participant_id: row for row in engine.standings()}
    assert by_id[r2_bye.participant_a].wins == 0.0
    assert by_id[r1_bye.participant_a].wins == 1.0

    # 第 2 轮第一场真实结果落地：第 2 轮轮空开始计 1 分。
    r2_real = [m for m in r2.matches if not m.is_bye]
    engine.record_result(r2_real[0].match_id, MatchResult(winner=r2_real[0].participant_a))
    by_id = {row.participant_id: row for row in engine.standings()}
    assert by_id[r2_bye.participant_a].wins == 1.0


def test_bye_goes_to_lowest_ranked_each_round():
    """n=5, lower id wins: the bye goes to the lowest-ranked participant that
    has not yet had one — 5, then 4, then 3, then 2 (traced deterministically),
    never repeating a recipient."""
    engine = SwissEngine([1, 2, 3, 4, 5], {})
    expected_byes = [5, 4, 3, 2]
    for round_number, expected in enumerate(expected_byes, start=1):
        plan = engine.generate_schedule()[round_number - 1]
        byes = [m for m in plan.matches if m.is_bye]
        assert len(byes) == 1
        assert byes[0].participant_a == expected
        _record_round(engine, round_number, lambda a, b: min(a, b))
    assert engine.is_complete() is True


# --------------------------------------------------------------------------- #
# result recording
# --------------------------------------------------------------------------- #


def test_draw_gives_half_point_to_both():
    """Metis E1: a draw gives each side 0.5 points (wins 不计入胜场)."""
    engine = SwissEngine([1, 2, 3, 4], {})
    match = _real_matches(engine.generate_schedule())[0]

    engine.record_result(match.match_id, MatchResult(winner=None, is_draw=True))
    by_id = {row.participant_id: row for row in engine.standings()}

    assert by_id[match.participant_a].points == 0.5
    assert by_id[match.participant_b].points == 0.5
    assert by_id[match.participant_a].wins == 0.0
    assert by_id[match.participant_b].wins == 0.0
    assert by_id[match.participant_a].draws == 1.0
    assert by_id[match.participant_b].draws == 1.0


def test_record_all_wins_lower_id_always_wins():
    """Recording every round with the lower id winning → standings sorted by
    points desc; participant 1 is the undefeated 4-point leader."""
    engine = SwissEngine([1, 2, 3, 4, 5, 6, 7, 8], {})
    for round_number in range(1, engine._rounds + 1):
        _record_round(engine, round_number, lambda a, b: min(a, b))

    standings = engine.standings()
    assert standings[0].participant_id == 1
    assert standings[0].wins == 4.0  # undefeated champion
    assert all(row.wins <= 4.0 for row in standings)
    points = [row.points for row in standings]
    assert points == sorted(points, reverse=True)
    assert engine.is_complete() is True


# --------------------------------------------------------------------------- #
# tie-break (Metis V1: points → Buchholz → net → seed)
# --------------------------------------------------------------------------- #


def test_buchholz_tie_break_ranks_above_equal_points():
    """4 players, 2 rounds: 1 and 2 tie on points (1.0) and net (0.0);
    Buchholz (对手分) decides — 1's opponents accumulated 3.0 final points vs
    2's 1.0, so 1 ranks above 2 despite identical (points, net)."""
    engine = SwissEngine([1, 2, 3, 4], {})
    r1 = engine.generate_schedule()[0]
    assert _pairs_of(r1) == {frozenset((1, 2)), frozenset((3, 4))}

    # Round 1: 1 beats 2, 3 beats 4 (trace deterministically).
    engine.record_result(
        next(m for m in r1.matches if m.participant_a == 1).match_id,
        MatchResult(winner=1, score_a=1, score_b=0),
    )
    engine.record_result(
        next(m for m in r1.matches if m.participant_a == 3).match_id,
        MatchResult(winner=3, score_a=1, score_b=0),
    )
    r2 = engine.generate_next_round()
    assert r2 is not None and r2.round_number == 2
    assert _pairs_of(r2) == {frozenset((1, 3)), frozenset((2, 4))}

    # Round 2: 3 beats 1, 2 beats 4.
    engine.record_result(
        next(m for m in r2.matches if 1 in (m.participant_a, m.participant_b)).match_id,
        MatchResult(winner=3, score_a=0, score_b=1),
    )
    engine.record_result(
        next(m for m in r2.matches if 2 in (m.participant_a, m.participant_b)).match_id,
        MatchResult(winner=2, score_a=1, score_b=0),
    )

    standings = engine.standings()
    by_id = {row.participant_id: row for row in standings}
    assert by_id[1].wins == by_id[2].wins == 1.0
    assert by_id[1].net_score == by_id[2].net_score == 0.0
    assert by_id[1].opponent_wins == 3.0
    assert by_id[2].opponent_wins == 1.0
    assert standings.index(by_id[1]) < standings.index(by_id[2])
    assert by_id[3].wins == 2.0  # champion
    assert standings[0].participant_id == 3


def test_standings_correct_after_each_round():
    """Points and Buchholz are recomputed from the results recorded so far,
    for whatever rounds are materialized."""
    engine = SwissEngine([1, 2, 3, 4, 5, 6], {})  # 3 rounds
    _record_round(engine, 1, lambda a, b: min(a, b))

    by_id = {row.participant_id: row for row in engine.standings()}
    assert [by_id[p].wins for p in (1, 2, 3, 4, 5, 6)] == [1.0, 0.0, 1.0, 0.0, 1.0, 0.0]
    assert [by_id[p].opponent_wins for p in (1, 2, 3, 4, 5, 6)] == [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
    assert [row.participant_id for row in engine.standings()] == [1, 3, 5, 2, 4, 6]

    _record_round(engine, 2, lambda a, b: min(a, b))  # 1>3, 2>5, 4>6
    by_id = {row.participant_id: row for row in engine.standings()}
    assert [by_id[p].wins for p in (1, 2, 3, 4, 5, 6)] == [2.0, 1.0, 1.0, 1.0, 1.0, 0.0]
    assert [by_id[p].opponent_wins for p in (1, 2, 3, 4, 5, 6)] == [2.0, 3.0, 3.0, 1.0, 1.0, 2.0]
    assert [row.participant_id for row in engine.standings()] == [1, 2, 3, 4, 5, 6]


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #


def test_value_error_for_invalid_rounds_config():
    with pytest.raises(ValueError):
        SwissEngine([1, 2, 3, 4], {"rounds": 0})
    with pytest.raises(ValueError):
        SwissEngine([1, 2, 3, 4], {"rounds": -1})
    with pytest.raises(ValueError):
        SwissEngine([1, 2, 3, 4], {"rounds": "4"})


def test_value_error_for_invalid_participants():
    with pytest.raises(ValueError):
        SwissEngine([], {})
    with pytest.raises(ValueError):
        SwissEngine([42], {})
    with pytest.raises(ValueError):
        SwissEngine([1, 2, 2], {})


# --------------------------------------------------------------------------- #
# completion / round advance
# --------------------------------------------------------------------------- #


def test_is_complete_after_all_real_matches_recorded():
    engine = SwissEngine([1, 2, 3, 4, 5, 6, 7, 8], {})

    assert engine.is_complete() is False
    r1 = engine.generate_schedule()[0]
    for m in r1.matches:
        engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
    # Round 1 fully recorded but rounds 2-4 not materialized → NOT complete
    # (the base implementation would wrongly report complete here).
    assert engine.is_complete() is False

    engine.generate_next_round()
    assert engine.is_complete() is False

    for round_number in range(2, engine._rounds + 1):
        _record_round(engine, round_number, lambda a, b: min(a, b))
        assert engine.is_complete() is (round_number == engine._rounds)


def test_next_round_returns_rounds_in_order():
    engine = SwissEngine([1, 2, 3, 4, 5, 6, 7, 8], {})
    for expected in (1, 2, 3, 4):
        assert engine.next_round().round_number == expected
        _record_round(engine, expected, lambda a, b: min(a, b))
    assert engine.next_round() is None


# --------------------------------------------------------------------------- #
# rebuild determinism (match_id determinism is the #1 risk)
# --------------------------------------------------------------------------- #


def test_rebuild_determinism():
    """generate_next_round must be a pure function of (participants, results):
    a rebuilt engine that replays the same results materializes IDENTICAL
    pairings AND match_ids — otherwise persisted engine_match_id would no
    longer match the rebuilt engine and recording would 400."""
    participants = [1, 2, 3, 4, 5, 6, 7, 8]
    winner_fn = lambda a, b: b if (a + b) % 3 == 0 else a

    # Play rounds 1-2 on one engine and capture (match_id, result) in order.
    engine_a = SwissEngine(participants, {})
    played = _play_round_and_return(engine_a, 1, winner_fn)
    played += _play_round_and_return(engine_a, 2, winner_fn)
    schedule_a = engine_a.generate_schedule()

    # Rebuild from scratch and replay exactly the same results, calling
    # generate_next_round after every record (mirrors _replay_finished).
    engine_b = SwissEngine(participants, {})
    for match_id, res in played:
        engine_b.record_result(match_id, res)
        engine_b.generate_next_round()
    schedule_b = engine_b.generate_schedule()

    assert schedule_a == schedule_b  # RoundPlan equality covers ids + players

    # Repeat the whole thing once more: full determinism, no state leakage.
    engine_c = SwissEngine(participants, {})
    for match_id, res in played:
        engine_c.record_result(match_id, res)
        engine_c.generate_next_round()
    assert engine_c.generate_schedule() == schedule_a


# --------------------------------------------------------------------------- #
# scale
# --------------------------------------------------------------------------- #


def test_fifty_players_default_rounds_seven():
    """50 players / config {} → min(ceil(log2(50))+1, 7) = 7 rounds; 25 real
    matches per round; no opponent pair repeats across the whole tournament;
    every participant plays exactly once per round."""
    engine = SwissEngine(list(range(1, 51)), {})
    assert engine._rounds == 7 == min(math.ceil(math.log2(50)) + 1, 7)

    all_pairs = set()
    for round_number in range(1, 8):
        plan = engine.generate_schedule()[round_number - 1]
        assert plan.round_number == round_number
        assert len([m for m in plan.matches if not m.is_bye]) == 25
        assert not any(m.is_bye for m in plan.matches)  # even field
        round_pairs = _pairs_of(plan)
        assert len(round_pairs) == 25
        assert round_pairs.isdisjoint(all_pairs)  # no repeated opponents
        all_pairs |= round_pairs
        for pid in range(1, 51):
            round_pids = {m.participant_a for m in plan.matches} | {m.participant_b for m in plan.matches}
            assert pid in round_pids
        _record_round(engine, round_number, lambda a, b: min(a, b))

    assert len(all_pairs) == 25 * 7
    assert engine.is_complete() is True
