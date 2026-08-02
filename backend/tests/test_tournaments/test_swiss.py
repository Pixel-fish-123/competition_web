"""瑞士轮引擎 (Swiss) tests — todo 10.

TDD suite for ``app/tournaments/swiss.py``. Pure algorithm tests — no DB, no
network. Coverage:

- deterministic pre-generated schedule: default round count, matches per round,
  no repeated opponent pair across the whole tournament
- odd fields: exactly one bye per round, no participant receives two byes,
  bye = 1 point / 0 net in standings
- Metis E1 draw semantics: 0.5 points for both sides
- full recording: standings sorted by points, undefeated champion on top
- Buchholz (对手分) tie-break: equal points, higher Buchholz ranks above
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
    """All non-bye matches across the whole schedule."""
    return [m for r in schedule for m in r.matches if not m.is_bye]


def _byes(schedule):
    """All bye matches across the whole schedule."""
    return [m for r in schedule for m in r.matches if m.is_bye]


def _pair_to_plan(engine):
    return {
        frozenset((m.participant_a, m.participant_b)): m
        for m in _real_matches(engine.generate_schedule())
    }


def _record_all_wins(engine, choose_winner):
    """Record every real match, choosing the winner via ``choose_winner(a, b)``
    with 1-0 scores aligned to the actual a/b orientation of each plan."""
    for m in _real_matches(engine.generate_schedule()):
        winner = choose_winner(m.participant_a, m.participant_b)
        if m.participant_a == winner:
            engine.record_result(m.match_id, MatchResult(winner=winner, score_a=1, score_b=0))
        else:
            engine.record_result(m.match_id, MatchResult(winner=winner, score_a=0, score_b=1))


# --------------------------------------------------------------------------- #
# scheduling
# --------------------------------------------------------------------------- #


def test_default_rounds_and_no_repeated_opponents_eight_players():
    """8 players / config {} → min(ceil(log2(8))+1, 7) = 4 rounds; every round
    has 4 real matches (16 total); no opponent pair repeats across the whole
    tournament; every participant appears exactly once per round."""
    engine = SwissEngine([1, 2, 3, 4, 5, 6, 7, 8], {})
    schedule = engine.generate_schedule()

    assert [r.round_number for r in schedule] == [1, 2, 3, 4]
    assert len(_real_matches(schedule)) == 16
    for r in schedule:
        assert len([m for m in r.matches if not m.is_bye]) == 4
        assert not any(m.is_bye for m in r.matches)

    pairs = {frozenset((m.participant_a, m.participant_b)) for m in _real_matches(schedule)}
    assert len(pairs) == 16

    for pid in range(1, 9):
        for r in schedule:
            round_pids = {m.participant_a for m in r.matches} | {m.participant_b for m in r.matches}
            assert pid in round_pids
        opponents = [
            m.participant_b if m.participant_a == pid else m.participant_a
            for m in _real_matches(schedule)
            if pid in (m.participant_a, m.participant_b)
        ]
        assert len(set(opponents)) == 4


def test_five_players_one_bye_per_round_no_double_bye():
    """5 players / config {} → 4 rounds (min(ceil(log2(5))+1, 7)); each round
    has exactly one bye and no participant gets a second bye (4 byes over 5
    players); each bye counts as 1 point / 0 net in standings."""
    engine = SwissEngine([1, 2, 3, 4, 5], {})
    schedule = engine.generate_schedule()

    assert [r.round_number for r in schedule] == [1, 2, 3, 4]
    assert len(_real_matches(schedule)) == 8  # 2 per round × 4 rounds
    for r in schedule:
        assert len([m for m in r.matches if m.is_bye]) == 1

    byes = _byes(schedule)
    assert len(byes) == 4
    recipients = [m.participant_a for m in byes]
    assert len(set(recipients)) == len(recipients)  # no participant has 2 byes

    by_id = {row.participant_id: row for row in engine.standings()}
    for pid in recipients:
        assert by_id[pid].wins == 1.0  # bye = 1 point
        assert by_id[pid].net_score == 0.0  # bye = 0 net


# --------------------------------------------------------------------------- #
# result recording
# --------------------------------------------------------------------------- #


def test_draw_gives_half_point_to_both():
    """Metis E1: a draw gives each side 0.5 points."""
    engine = SwissEngine([1, 2, 3, 4], {})
    match = _real_matches(engine.generate_schedule())[0]

    engine.record_result(match.match_id, MatchResult(winner=None, is_draw=True))
    by_id = {row.participant_id: row for row in engine.standings()}

    assert by_id[match.participant_a].wins == 0.5
    assert by_id[match.participant_b].wins == 0.5


def test_record_all_wins_lower_id_always_wins():
    """Recording every match with the lower id winning → standings sorted by
    points desc; participant 1 is the undefeated 4-point leader."""
    engine = SwissEngine([1, 2, 3, 4, 5, 6, 7, 8], {})
    _record_all_wins(engine, lambda a, b: min(a, b))
    standings = engine.standings()

    assert standings[0].participant_id == 1
    assert standings[0].wins == 4.0  # undefeated champion
    assert all(row.wins <= 4.0 for row in standings)
    points = [row.wins for row in standings]
    assert points == sorted(points, reverse=True)
    assert engine.is_complete() is True


# --------------------------------------------------------------------------- #
# tie-break (Metis V1: points → Buchholz → net → seed)
# --------------------------------------------------------------------------- #


def test_buchholz_tie_break_ranks_above_equal_points():
    """Two players finish with equal points and net but different Buchholz
    (对手分): player 1's opponents accumulated more final points than player 2's
    opponents, so 1 ranks above 2 despite the identical (points, net)."""
    engine = SwissEngine([1, 2, 3, 4, 5, 6, 7, 8], {})
    # Winner per unordered pair (all matches are 1-0). This must match the
    # deterministic schedule exactly — guarded by the set-equality assert below.
    outcomes = {
        frozenset((1, 2)): 2, frozenset((3, 4)): 3, frozenset((5, 6)): 5, frozenset((7, 8)): 7,
        frozenset((1, 3)): 1, frozenset((2, 4)): 4, frozenset((5, 7)): 5, frozenset((6, 8)): 6,
        frozenset((1, 4)): 4, frozenset((2, 3)): 3, frozenset((5, 8)): 5, frozenset((6, 7)): 7,
        frozenset((1, 5)): 1, frozenset((2, 6)): 2, frozenset((3, 7)): 3, frozenset((4, 8)): 4,
    }
    pair_to_plan = _pair_to_plan(engine)
    assert set(outcomes) == set(pair_to_plan)  # schedule matches the traced pairing

    for pair, winner in outcomes.items():
        plan = pair_to_plan[pair]
        if plan.participant_a == winner:
            engine.record_result(plan.match_id, MatchResult(winner=winner, score_a=1, score_b=0))
        else:
            engine.record_result(plan.match_id, MatchResult(winner=winner, score_a=0, score_b=1))

    standings = engine.standings()
    by_id = {row.participant_id: row for row in standings}

    # 1 and 2 tie on points (2.0) and net (0.0); Buchholz decides: 1's played
    # opponents (2,3,4,5 → 2+3+3+3=11) beat 2's (1,4,3,6 → 2+3+3+1=9).
    assert by_id[1].wins == by_id[2].wins == 2.0
    assert by_id[1].net_score == by_id[2].net_score == 0.0
    assert by_id[1].opponent_wins == 11.0
    assert by_id[2].opponent_wins == 9.0
    assert standings.index(by_id[1]) < standings.index(by_id[2])


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
    real = _real_matches(engine.generate_schedule())

    assert engine.is_complete() is False
    for m in real[:-1]:
        engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
        assert engine.is_complete() is False
    engine.record_result(real[-1].match_id, MatchResult(winner=real[-1].participant_a))
    assert engine.is_complete() is True


def test_next_round_returns_rounds_in_order():
    engine = SwissEngine([1, 2, 3, 4, 5, 6, 7, 8], {})
    schedule = engine.generate_schedule()

    for expected in (1, 2, 3, 4):
        assert engine.next_round().round_number == expected
        for m in schedule[expected - 1].matches:
            engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
    assert engine.next_round() is None


# --------------------------------------------------------------------------- #
# scale
# --------------------------------------------------------------------------- #


def test_fifty_players_default_rounds_seven():
    """50 players / config {} → min(ceil(log2(50))+1, 7) = 7 rounds; 25 real
    matches per round; no opponent pair repeats across the whole tournament."""
    engine = SwissEngine(list(range(1, 51)), {})
    schedule = engine.generate_schedule()

    assert engine._rounds == 7 == min(math.ceil(math.log2(50)) + 1, 7)
    assert [r.round_number for r in schedule] == list(range(1, 8))
    assert len(_real_matches(schedule)) == 25 * 7
    for r in schedule:
        assert len([m for m in r.matches if not m.is_bye]) == 25

    pairs = {frozenset((m.participant_a, m.participant_b)) for m in _real_matches(schedule)}
    assert len(pairs) == 25 * 7
