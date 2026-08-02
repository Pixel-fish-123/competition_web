"""Tournament engine abstraction — plan.md §七 (统一 TournamentEngine 接口).

This module defines the engine contract that every 赛制引擎 (round-robin /
swiss / single-elim, todos 9-11) implements, plus the plain dataclasses used
to exchange schedule / result / standing data. Pure logic — no DB, no I/O.

Data model
----------
- ``MatchPlan``: one scheduled pairing. ``participant_b is None`` together with
  ``is_bye=True`` marks a bye (轮空); the bye recipient is ``participant_a``.
- ``RoundPlan``: a global round number plus its matches (one group's matches
  may be absent in a global round when groups have different sizes).
- ``MatchResult``: outcome of a played match. ``winner is None`` +
  ``is_draw=True`` means a draw (平局, 0.5 win for both sides); otherwise
  ``winner`` must be one of the match's participants. ``score_a`` / ``score_b``
  feed the net-score tie-break (净胜分).
- ``StandingRow``: one participant's standings line. ``opponent_wins`` holds
  the head-to-head scalar (相互胜负): the sum of the participant's scores in
  matches against opponents sharing the same (wins, net_score) — for a two-way
  tie this is exactly the score in the single mutual match. ``seed`` is the
  1-based position of the participant in the constructor's input list.

Engine contract (methods are documented inline below): the abstract engine
stores participants + config, exposes schedule generation / result recording /
standings / completion / next-round advance. ``record_result``, ``is_complete``
and ``next_round`` are generic over any schedule that populates
``_schedule`` / ``_match_index``; ``generate_schedule`` and ``standings`` are
left abstract because their semantics are format-specific.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MatchPlan:
    """One scheduled pairing (or bye) inside a round.

    :param match_id: globally unique id across the whole schedule.
    :param participant_a: first participant (or the bye recipient when is_bye).
    :param participant_b: second participant; None for a bye.
    :param is_bye: True when this entry is an automatic bye (轮空) — the bye
        recipient gets 1 win / 0 net score and no result may be recorded.
    """

    match_id: int
    participant_a: int | None
    participant_b: int | None
    is_bye: bool = False


@dataclass(frozen=True)
class RoundPlan:
    """A global round: round_number (1-based, interleaved across groups) and
    the matches (real or bye) scheduled in it."""

    round_number: int
    matches: list[MatchPlan] = field(default_factory=list)


@dataclass(frozen=True)
class MatchResult:
    """Outcome of a played match.

    :param winner: participant id of the winner; must be one of the match's
        participants when is_draw is False.
    :param is_draw: True → draw (平局): each side receives 0.5 wins; winner
        must be None.
    :param score_a: score achieved by participant_a (for 净胜分 / net_score).
    :param score_b: score achieved by participant_b.
    """

    winner: int | None = None
    is_draw: bool = False
    score_a: float = 0.0
    score_b: float = 0.0


@dataclass
class StandingRow:
    """One participant's standings line, pre-sorted per the format's rules.

    :param participant_id: the participant unit id.
    :param wins: number of wins as a float (draw = 0.5, bye = 1.0).
    :param net_score: sum of (own score − opponent score) over recorded matches
        (bye contributes 0).
    :param opponent_wins: head-to-head scalar (相互胜负) — see module docstring.
    :param seed: 1-based position of the participant in the input list.
    """

    participant_id: int
    wins: float
    net_score: float
    opponent_wins: float
    seed: int


class TournamentEngine(ABC):
    """Interface shared by all 赛制引擎 (round-robin / swiss / single-elim).

    :param participants: list of participant unit ids (ints). The input order
        doubles as the seed order (seed = index + 1).
    :param config: format-specific options, e.g. ``{"group_size": 4}`` for the
        round-robin engine.
    """

    def __init__(self, participants: list[int], config: dict) -> None:
        self.participants: list[int] = list(participants)
        self.config: dict = dict(config) if config is not None else {}
        self._schedule: list[RoundPlan] | None = None
        self._results: dict[int, MatchResult] = {}
        self._match_index: dict[int, MatchPlan] = {}

    @abstractmethod
    def generate_schedule(self) -> list[RoundPlan]:
        """Build the full tournament schedule.

        Invariants every concrete engine must uphold:
        - every participant appears exactly once per round (or takes a bye);
        - no participant faces the same opponent twice;
        - every real match has a unique ``match_id``.
        Calling this method repeatedly must be idempotent.
        """

    def record_result(self, match_id: int, result: MatchResult) -> None:
        """Store the outcome of a played match.

        Validation (raises ValueError on any violation):
        - the match id must exist in the schedule;
        - bye matches are scored automatically and must not receive a result;
        - a match may only be recorded once;
        - a non-draw result must name one of the two participants as winner;
        - a draw result must not name a winner (winner stays None).
        """
        plan = self._match_index.get(match_id)
        if plan is None:
            raise ValueError(f"unknown match_id: {match_id}")
        if plan.is_bye:
            raise ValueError(f"bye match {match_id} is scored automatically and cannot have a result")
        if match_id in self._results:
            raise ValueError(f"result already recorded for match {match_id}")
        if result.is_draw:
            if result.winner is not None:
                raise ValueError("a draw result must have winner=None")
        elif result.winner not in (plan.participant_a, plan.participant_b):
            raise ValueError(
                f"winner must be one of the match participants "
                f"({plan.participant_a} / {plan.participant_b}), got {result.winner!r}"
            )
        self._results[match_id] = result

    @abstractmethod
    def standings(self) -> list[StandingRow]:
        """Return the current ranking, best first.

        Rows are sorted by the format's tie-break chain. Byes and unplayed
        matches are handled automatically (see the concrete engine).
        """

    def is_complete(self) -> bool:
        """True once every real (non-bye) match in the schedule has a result.

        Byes are automatic and never block completion.
        """
        if self._schedule is None:
            return False
        return all(
            m.is_bye or m.match_id in self._results
            for r in self._schedule
            for m in r.matches
        )

    def next_round(self) -> RoundPlan | None:
        """Return the earliest round (by round_number) that still has an
        unrecorded real match, or None when the tournament is complete."""
        if self._schedule is None:
            return None
        for r in self._schedule:
            if any(not m.is_bye and m.match_id not in self._results for m in r.matches):
                return r
        return None
