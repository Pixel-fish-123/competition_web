"""Round-robin (分组循环赛) engine tests — todo 9.

TDD suite for ``app/tournaments/round_robin.py``. Pure algorithm tests — no DB,
no network. Coverage:

- circle-method (轮转法) scheduling: single group (even / odd size) and multiple
  groups with interleaved global round numbers
- Metis E1 draw semantics: a draw gives each side 0.5 wins
- Metis E2 bye semantics: an odd-sized group produces exactly one bye per round;
  the bye recipient auto-gets 1 win and 0 net score in standings
- Metis V1 tie-break: wins desc → net_score desc → head-to-head → participant id asc
- completion / round-advance behaviour and input validation
"""

import pytest

from app.tournaments.base import MatchResult
from app.tournaments.round_robin import RoundRobinEngine


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


def _opponents_of(participant, schedule):
    """Every non-bye opponent a participant faces, in match order."""
    opponents = []
    for m in _real_matches(schedule):
        if m.participant_a == participant:
            opponents.append(m.participant_b)
        elif m.participant_b == participant:
            opponents.append(m.participant_a)
    return opponents


def _byes_of(participant, schedule):
    return [m for r in schedule for m in r.matches if m.is_bye and m.participant_a == participant]


def _record_pairs(engine, results_by_pair):
    """Record results by unordered participant pair.

    ``results_by_pair`` maps a pair to ``(winner, score_for_winner,
    score_for_loser)``; the helper aligns the scores to the actual
    participant_a / participant_b orientation of the generated match plan
    (``score_a`` always belongs to ``participant_a``).
    """
    pair_to_plan = {}
    for m in _real_matches(engine.generate_schedule()):
        pair_to_plan[frozenset((m.participant_a, m.participant_b))] = m
    for pair, (winner, win_score, lose_score) in results_by_pair.items():
        plan = pair_to_plan[frozenset(pair)]
        if plan.participant_a == winner:
            engine.record_result(plan.match_id, MatchResult(winner=winner, score_a=win_score, score_b=lose_score))
        else:
            engine.record_result(plan.match_id, MatchResult(winner=winner, score_a=lose_score, score_b=win_score))


# --------------------------------------------------------------------------- #
# scheduling
# --------------------------------------------------------------------------- #


def test_six_participants_two_groups_of_three():
    """6 teams / group_size 3 → 2 groups of 3: 3 global rounds, 2 matches per
    round (1 real + 1 bye per group), 6 real matches total; every participant
    plays exactly 2 matches and no opponent twice."""
    engine = RoundRobinEngine([1, 2, 3, 4, 5, 6], {"group_size": 3})
    schedule = engine.generate_schedule()

    assert [r.round_number for r in schedule] == [1, 2, 3]
    assert len(_real_matches(schedule)) == 6
    for r in schedule:
        assert len([m for m in r.matches if not m.is_bye]) == 2
        assert len([m for m in r.matches if m.is_bye]) == 2  # one per odd group

    for pid in range(1, 7):
        opponents = _opponents_of(pid, schedule)
        assert len(opponents) == 2
        assert len(set(opponents)) == 2  # no repeated opponent
        assert len(_byes_of(pid, schedule)) == 1

    real_pairs = {tuple(sorted((m.participant_a, m.participant_b))) for m in _real_matches(schedule)}
    assert len(real_pairs) == 6


def test_four_participants_single_group():
    """4 teams / group_size 4 (single group): 3 rounds × 2 matches = 6 matches,
    no byes; each participant plays all 3 others exactly once."""
    engine = RoundRobinEngine([1, 2, 3, 4], {"group_size": 4})
    schedule = engine.generate_schedule()

    assert [r.round_number for r in schedule] == [1, 2, 3]
    assert len(_real_matches(schedule)) == 6
    for r in schedule:
        assert len(r.matches) == 2
        assert all(not m.is_bye for m in r.matches)

    for pid in range(1, 5):
        opponents = _opponents_of(pid, schedule)
        assert len(opponents) == 3
        assert len(set(opponents)) == 3


def test_five_participants_odd_single_group_byes():
    """5 teams single group (odd): 5 rounds (n rounds for odd n); each round has
    2 real matches + 1 bye; every participant gets exactly one bye (4 real
    matches); the bye auto-counts as 1 win / 0 net in standings."""
    engine = RoundRobinEngine([1, 2, 3, 4, 5], {})
    schedule = engine.generate_schedule()

    assert [r.round_number for r in schedule] == [1, 2, 3, 4, 5]
    assert len([m for r in schedule for m in r.matches if m.is_bye]) == 5
    for r in schedule:
        assert len([m for m in r.matches if not m.is_bye]) == 2

    for pid in range(1, 6):
        assert len(_byes_of(pid, schedule)) == 1
        opponents = _opponents_of(pid, schedule)
        assert len(opponents) == 4
        assert len(set(opponents)) == 4

    standings = engine.standings()
    for row in standings:
        assert row.wins == 1.0  # bye = 1 win
        assert row.net_score == 0.0  # bye = 0 net

    assert engine.is_complete() is False  # real matches not recorded yet


def test_uneven_group_sizes_interleave_by_largest_group():
    """5 teams / group_size 2 → tail chunk of 1 merges into the previous group
    ([2,2,1] → groups of 2 and 3). Global round count follows the largest group
    (3 rounds); the 2-member group contributes only its single round."""
    engine = RoundRobinEngine([1, 2, 3, 4, 5], {"group_size": 2})
    schedule = engine.generate_schedule()

    assert [r.round_number for r in schedule] == [1, 2, 3]
    assert len(_real_matches(schedule)) == 4  # 1 (group of 2) + 3 (group of 3)
    assert len([m for m in _matches_in_round(schedule, 1) if not m.is_bye]) == 2
    assert len([m for m in _matches_in_round(schedule, 2) if not m.is_bye]) == 1
    assert len([m for m in _matches_in_round(schedule, 3) if not m.is_bye]) == 1


# --------------------------------------------------------------------------- #
# result recording
# --------------------------------------------------------------------------- #


def test_record_winner_reflected_in_standings():
    engine = RoundRobinEngine([1, 2], {"group_size": 2})
    match = _real_matches(engine.generate_schedule())[0]
    assert {match.participant_a, match.participant_b} == {1, 2}

    engine.record_result(match.match_id, MatchResult(winner=1, score_a=3, score_b=1))
    standings = engine.standings()
    by_id = {row.participant_id: row for row in standings}

    assert by_id[1].wins == 1.0
    assert by_id[2].wins == 0.0
    assert by_id[1].net_score == 2.0
    assert by_id[2].net_score == -2.0
    assert standings[0].participant_id == 1


def test_draw_gives_half_win_to_both():
    """Metis E1: draw = 0.5 wins for both sides."""
    engine = RoundRobinEngine([1, 2], {"group_size": 2})
    match = _real_matches(engine.generate_schedule())[0]

    engine.record_result(match.match_id, MatchResult(winner=None, is_draw=True))
    standings = engine.standings()
    by_id = {row.participant_id: row for row in standings}

    assert by_id[1].wins == 0.5
    assert by_id[2].wins == 0.5


def test_record_result_guards():
    engine = RoundRobinEngine([1, 2], {"group_size": 2})
    match = _real_matches(engine.generate_schedule())[0]

    # winner must be one of the match participants
    with pytest.raises(ValueError):
        engine.record_result(match.match_id, MatchResult(winner=999))
    # a draw result must not name a winner
    with pytest.raises(ValueError):
        engine.record_result(match.match_id, MatchResult(winner=1, is_draw=True))

    engine.record_result(match.match_id, MatchResult(winner=1))
    # duplicate recording is rejected
    with pytest.raises(ValueError):
        engine.record_result(match.match_id, MatchResult(winner=2))
    # unknown match ids are rejected
    with pytest.raises(ValueError):
        engine.record_result(9999, MatchResult(winner=1))


def test_bye_match_cannot_have_result_recorded():
    engine = RoundRobinEngine([1, 2, 3], {"group_size": 3})
    bye = next(m for r in engine.generate_schedule() for m in r.matches if m.is_bye)
    with pytest.raises(ValueError):
        engine.record_result(bye.match_id, MatchResult(winner=bye.participant_a))


# --------------------------------------------------------------------------- #
# tie-break (Metis V1: wins → net_score → head-to-head → id)
# --------------------------------------------------------------------------- #


def test_tie_break_net_score_decides_before_head_to_head():
    """Players 1, 2, 3 all finish with 2 wins but different net scores.
    Player 2 BEAT player 1 head-to-head yet still ranks below 1 — proving
    net_score is compared before head-to-head."""
    engine = RoundRobinEngine([1, 2, 3, 4], {"group_size": 4})
    _record_pairs(engine, {
        (1, 4): (1, 3, 0),
        (2, 3): (3, 1, 0),
        (1, 2): (2, 1, 0),
        (3, 4): (3, 1, 0),
        (1, 3): (1, 1, 0),
        (2, 4): (2, 2, 0),
    })
    standings = engine.standings()
    by_id = {row.participant_id: row for row in standings}

    # wins: 1→2, 2→2, 3→2, 4→0 ; net: 1→+3, 2→+2, 3→+1, 4→-6
    assert [row.participant_id for row in standings] == [1, 2, 3, 4]
    assert all(row.wins == 2.0 for row in standings[:3])
    assert by_id[1].net_score > by_id[2].net_score > by_id[3].net_score


def test_tie_break_head_to_head_decides_after_equal_wins_and_net():
    """Players 2 and 3 tie on wins (2) and net (+1); player 2 beat player 3 in
    their mutual match → head-to-head puts 2 above 3. Same for pair (1, 4):
    both 1 win / net −1 and 1 beat 4 → 1 above 4. This is the head-to-head
    (相互胜负) case of Metis V1."""
    engine = RoundRobinEngine([1, 2, 3, 4], {"group_size": 4})
    _record_pairs(engine, {
        (1, 4): (1, 1, 0),
        (2, 3): (2, 1, 0),
        (1, 2): (2, 1, 0),
        (3, 4): (3, 1, 0),
        (1, 3): (3, 1, 0),
        (2, 4): (4, 1, 0),
    })
    standings = engine.standings()
    by_id = {row.participant_id: row for row in standings}

    assert [row.participant_id for row in standings] == [2, 3, 1, 4]
    # head-to-head scalar = mutual-match score within the tie group
    assert by_id[2].opponent_wins == 1.0
    assert by_id[3].opponent_wins == 0.0
    assert by_id[1].opponent_wins == 1.0
    assert by_id[4].opponent_wins == 0.0


# --------------------------------------------------------------------------- #
# completion / round advance
# --------------------------------------------------------------------------- #


def test_is_complete_after_all_matches_recorded():
    engine = RoundRobinEngine([1, 2, 3, 4], {"group_size": 4})
    real = _real_matches(engine.generate_schedule())

    assert engine.is_complete() is False
    for m in real[:-1]:
        engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
        assert engine.is_complete() is False
    engine.record_result(real[-1].match_id, MatchResult(winner=real[-1].participant_a))
    assert engine.is_complete() is True


def test_next_round_returns_rounds_in_order():
    engine = RoundRobinEngine([1, 2, 3, 4], {"group_size": 4})
    schedule = engine.generate_schedule()

    assert engine.next_round().round_number == 1
    for m in schedule[0].matches:
        engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
    assert engine.next_round().round_number == 2
    for m in schedule[1].matches:
        engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
    assert engine.next_round().round_number == 3
    for m in schedule[2].matches:
        engine.record_result(m.match_id, MatchResult(winner=m.participant_a))
    assert engine.next_round() is None


# --------------------------------------------------------------------------- #
# seed reporting
# --------------------------------------------------------------------------- #


def test_standings_report_seed_from_input_order():
    engine = RoundRobinEngine([9, 8, 7, 6], {"group_size": 4})
    by_id = {row.participant_id: row for row in engine.standings()}
    assert by_id[9].seed == 1
    assert by_id[8].seed == 2
    assert by_id[7].seed == 3
    assert by_id[6].seed == 4


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #


def test_value_error_for_fewer_than_two_participants():
    with pytest.raises(ValueError):
        RoundRobinEngine([], {})
    with pytest.raises(ValueError):
        RoundRobinEngine([42], {})


def test_value_error_for_invalid_group_size():
    with pytest.raises(ValueError):
        RoundRobinEngine([1, 2, 3], {"group_size": 1})
    with pytest.raises(ValueError):
        RoundRobinEngine([1, 2, 3], {"group_size": 0})
