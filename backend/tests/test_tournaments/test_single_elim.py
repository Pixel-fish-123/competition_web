"""单败淘汰赛 (single-elimination) engine tests — todo 11.

TDD suite for ``app/tournaments/single_elim.py``. Pure algorithm tests — no DB,
no network. Coverage:

- bracket schedule shape: power-of-two rounds, third-place match on/off
- byes: 5 participants → bracket size 8, 3 round-1 byes auto-advancing
- seeding: seed 1 and 2 meet only in the final (mirror placement)
- result guards: draws forbidden (单败淘汰不允许平局), winner must be a resolved
  participant, a match cannot be recorded before its previous round
- completion / round-advance (the final decides completion; the third-place
  match does not block it)
- input validation (fewer than 2 participants, duplicates)
"""

import pytest

from app.tournaments.base import MatchResult
from app.tournaments.single_elim import SingleElimEngine


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _real_matches(schedule):
    """All non-bye matches across the whole schedule."""
    return [m for r in schedule for m in r.matches if not m.is_bye]


def _matches_in_round(schedule, round_number):
    for r in schedule:
        if r.round_number == round_number:
            return r.matches
    return []


def _play_engine(engine, pick_winner=None):
    """Record every playable match in order (lower participant id wins by
    default) until the schedule is exhausted."""
    if pick_winner is None:
        pick_winner = lambda a, b: min(a, b)
    while True:
        r = engine.next_round()
        if r is None:
            break
        for m in r.matches:
            if m.is_bye or m.match_id in engine._results:
                continue
            a, b = engine._resolve_participants(m.match_id)
            engine.record_result(m.match_id, MatchResult(winner=pick_winner(a, b)))


# --------------------------------------------------------------------------- #
# scheduling
# --------------------------------------------------------------------------- #


def test_schedule_shape_eight_participants_with_third_place():
    """8 participants (default third_place=True): rounds 4,2,1 matches + the
    third-place match = 8 total; champion determined once everything is
    recorded."""
    engine = SingleElimEngine([1, 2, 3, 4, 5, 6, 7, 8], {"third_place": True})
    schedule = engine.generate_schedule()

    assert [r.round_number for r in schedule] == [1, 2, 3, 4]
    assert [len(r.matches) for r in schedule] == [4, 2, 1, 1]
    assert len(_real_matches(schedule)) == 8
    assert all(not m.is_bye for r in schedule for m in r.matches)  # power of two → no byes

    _play_engine(engine)
    assert engine.is_complete() is True
    assert engine.standings()[0].participant_id == 1  # champion (lower id wins)


def test_no_third_place_match_when_disabled():
    """8 participants / third_place=False: 7 matches, no third-place round."""
    engine = SingleElimEngine([1, 2, 3, 4, 5, 6, 7, 8], {"third_place": False})
    schedule = engine.generate_schedule()

    assert [r.round_number for r in schedule] == [1, 2, 3]
    assert len(_real_matches(schedule)) == 7

    _play_engine(engine)
    assert engine.is_complete() is True


def test_five_participants_bracket_of_eight_three_byes():
    """5 participants → bracket size 8: 3 round-1 byes (is_bye=True,
    participant_b=None) that auto-advance; champion correct after simulating
    the full tournament (lower id wins)."""
    engine = SingleElimEngine([1, 2, 3, 4, 5], {})
    schedule = engine.generate_schedule()
    round1 = _matches_in_round(schedule, 1)

    assert len(round1) == 4
    byes = [m for m in round1 if m.is_bye]
    assert len(byes) == 3
    assert all(m.participant_b is None for m in byes)
    assert all(m.participant_a in (1, 2, 3, 4, 5) for m in byes)
    assert len([m for m in round1 if not m.is_bye]) == 1
    # byes auto-advance without recording a result
    for m in byes:
        assert engine._winners[m.match_id] == m.participant_a

    _play_engine(engine)
    assert engine.is_complete() is True
    assert engine.standings()[0].participant_id == 1


def test_seeded_placement_seeds_one_and_two_only_meet_in_final():
    """seeded=True: mirror placement puts seed 1 (participant 1) and seed 2
    (participant 2) in opposite halves; simulating all-lower-seed wins they
    only meet in the final."""
    engine = SingleElimEngine([1, 2, 3, 4, 5, 6, 7, 8], {"seeded": True})
    schedule = engine.generate_schedule()
    assert len(_real_matches(schedule)) == 8

    _play_engine(engine)
    pa, pb = engine._resolved[engine._final_match_id]
    assert {pa, pb} == {1, 2}
    assert engine.standings()[0].participant_id == 1


# --------------------------------------------------------------------------- #
# result recording guards
# --------------------------------------------------------------------------- #


def test_draw_result_rejected():
    """Metis E1: a draw is impossible in single elimination."""
    engine = SingleElimEngine([1, 2, 3, 4], {})
    match = _real_matches(engine.generate_schedule())[0]
    with pytest.raises(ValueError, match="单败淘汰不允许平局"):
        engine.record_result(match.match_id, MatchResult(winner=None, is_draw=True))


def test_winner_must_be_a_resolved_participant():
    """The winner must be one of the actual participants of the match — for
    later rounds those are the feeding winners, not just any participant."""
    engine = SingleElimEngine([1, 2, 3, 4], {})
    r1 = _matches_in_round(engine.generate_schedule(), 1)

    with pytest.raises(ValueError):
        engine.record_result(r1[0].match_id, MatchResult(winner=999))
    for m in r1:
        engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
    r2 = _matches_in_round(engine.generate_schedule(), 2)[0]
    with pytest.raises(ValueError):
        engine.record_result(r2.match_id, MatchResult(winner=2))  # 2 lost in round 1


def test_cannot_record_before_previous_round_complete():
    """A later-round match needs its feeding results first."""
    engine = SingleElimEngine([1, 2, 3, 4], {})
    r2 = _matches_in_round(engine.generate_schedule(), 2)[0]
    with pytest.raises(ValueError, match="previous round incomplete"):
        engine.record_result(r2.match_id, MatchResult(winner=1))


def test_unknown_and_bye_and_duplicate_guards():
    engine = SingleElimEngine([1, 2, 3, 4, 5], {})
    r1 = _matches_in_round(engine.generate_schedule(), 1)
    bye = next(m for m in r1 if m.is_bye)
    real = next(m for m in r1 if not m.is_bye)

    with pytest.raises(ValueError):
        engine.record_result(9999, MatchResult(winner=1))
    with pytest.raises(ValueError):
        engine.record_result(bye.match_id, MatchResult(winner=bye.participant_a))
    engine.record_result(real.match_id, MatchResult(winner=real.participant_a))
    with pytest.raises(ValueError):
        engine.record_result(real.match_id, MatchResult(winner=real.participant_b))


# --------------------------------------------------------------------------- #
# completion / round advance
# --------------------------------------------------------------------------- #


def test_is_complete_only_when_final_recorded():
    """Everything except the final (including the third-place match) recorded →
    still incomplete; recording the final determines the champion."""
    engine = SingleElimEngine([1, 2, 3, 4, 5, 6, 7, 8], {"third_place": True})
    schedule = engine.generate_schedule()
    assert engine.is_complete() is False

    for r in schedule:
        for m in r.matches:
            if m.is_bye or m.match_id == engine._final_match_id:
                continue
            a, b = engine._resolve_participants(m.match_id)
            engine.record_result(m.match_id, MatchResult(winner=min(a, b)))
    assert engine.is_complete() is False  # final missing

    a, b = engine._resolve_participants(engine._final_match_id)
    engine.record_result(engine._final_match_id, MatchResult(winner=min(a, b)))
    assert engine.is_complete() is True

    standings = engine.standings()
    assert standings[0].participant_id == 1  # champion
    assert standings[1].participant_id == 5  # runner-up


def test_next_round_returns_rounds_in_order():
    """next_round yields rounds 1,2,3 then the third-place round, then None."""
    engine = SingleElimEngine([1, 2, 3, 4, 5, 6, 7, 8], {"third_place": True})
    seen = []
    while True:
        r = engine.next_round()
        if r is None:
            break
        seen.append(r.round_number)
        for m in r.matches:
            if m.is_bye:
                continue
            a, b = engine._resolve_participants(m.match_id)
            engine.record_result(m.match_id, MatchResult(winner=min(a, b)))
    assert seen == [1, 2, 3, 4]


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #


def test_value_error_for_fewer_than_two_participants():
    with pytest.raises(ValueError):
        SingleElimEngine([], {})
    with pytest.raises(ValueError):
        SingleElimEngine([42], {})


def test_value_error_for_duplicate_participants():
    with pytest.raises(ValueError):
        SingleElimEngine([1, 1, 2], {})
