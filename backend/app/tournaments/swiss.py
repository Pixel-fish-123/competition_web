"""瑞士轮赛制引擎 — SwissEngine (todo 10).

Deterministic pre-generated Swiss schedule: the round count defaults to
``min(ceil(log2(n)) + 1, 7)`` and pairings are fixed at construction time —
they do NOT depend on recorded results, which satisfies the base engine's
"full schedule" contract. Each round orders participants by seed (no results
exist during build, so the standings order degenerates to seed order), hands a
bye to the last eligible participant when the field is odd, then perfect-matches
the rest greedily with backtracking so no opponent pair repeats across the
whole tournament.

Fixed semantics (plan.md §七 + Metis review):
- E1 平局: a draw gives each side 0.5 wins (wins are floats).
- E2 轮空: a bye counts as 1 win / 0 net score and is scored automatically in
  ``standings`` (no result may be recorded for it). Byes are spread so no
  participant receives two while un-byed participants remain.
- Buchholz (对手分): the sum of the FINAL points of all opponents a participant
  has actually played (recorded real matches only; byes contribute nothing).
- V1 同分决胜: points desc → Buchholz desc → net_score desc → seed asc.

StandingRow field mapping: ``wins`` carries the points (draw 0.5 / bye 1.0)
and ``opponent_wins`` carries the Buchholz score.

Validation: raises ValueError when there are fewer than 2 participants, when
participants are duplicated, or when ``rounds`` is present but not a positive
int. Pure logic — no DB, no I/O.
"""

import math

from app.tournaments.base import MatchPlan, RoundPlan, StandingRow, TournamentEngine


class SwissEngine(TournamentEngine):
    """Swiss-system engine with a deterministic pre-generated schedule."""

    def __init__(self, participants: list[int], config: dict) -> None:
        super().__init__(participants, config)

        if not isinstance(participants, list) or not all(
            isinstance(p, int) for p in participants
        ):
            raise ValueError("participants must be a list of ints")
        if len(participants) < 2:
            raise ValueError("at least 2 participants are required")
        if len(set(participants)) != len(participants):
            raise ValueError("participants must be unique")

        self._seed_map: dict[int, int] = {pid: i + 1 for i, pid in enumerate(participants)}

        rounds = self.config.get("rounds")
        if rounds is None:
            self._rounds = min(math.ceil(math.log2(len(participants))) + 1, 7)
        elif not isinstance(rounds, int) or rounds <= 0:
            raise ValueError("rounds must be a positive int")
        else:
            self._rounds = rounds

        self._played_pairs: set[frozenset[int]] = set()
        self._bye_taken: set[int] = set()

        self._schedule = self._build_schedule()
        self._match_index: dict[int, MatchPlan] = {
            m.match_id: m for r in self._schedule for m in r.matches
        }

    # ------------------------------------------------------------------ #
    # schedule generation
    # ------------------------------------------------------------------ #

    def generate_schedule(self) -> list[RoundPlan]:
        """Return the (cached) pre-generated schedule. Idempotent."""
        return self._schedule

    def _build_schedule(self) -> list[RoundPlan]:
        """Pre-generate the full Swiss schedule.

        Every round pairs in seed order (no results exist at build time, so the
        standings order degenerates to seed order). An odd field gives the last
        eligible participant a bye (never twice while un-byed alternatives
        remain); the remaining field is perfect-matched with backtracking so no
        opponent pair is repeated across the whole tournament.
        """
        rounds: list[RoundPlan] = []
        match_id = 1
        order = list(self.participants)  # seed order for every round
        for r in range(1, self._rounds + 1):
            pool = list(order)
            matches: list[MatchPlan] = []
            if len(pool) % 2 == 1:
                bye = self._pick_bye_recipient(pool)
                pool.remove(bye)
                self._bye_taken.add(bye)
                matches.append(MatchPlan(match_id, bye, None, is_bye=True))
                match_id += 1
            for a, b in self._perfect_match(pool):
                matches.append(MatchPlan(match_id, a, b))
                self._played_pairs.add(frozenset((a, b)))
                match_id += 1
            rounds.append(RoundPlan(r, matches))
        return rounds

    def _pick_bye_recipient(self, pool: list[int]) -> int:
        """Last participant in the ordering that has not yet had a bye; falls
        back to the last in the ordering once everyone has had one."""
        for pid in reversed(pool):
            if pid not in self._bye_taken:
                return pid
        return pool[-1]

    def _perfect_match(self, pool: list[int]) -> list[tuple[int, int]]:
        """Pair every participant in ``pool`` (already sorted) such that no
        opponent pair is repeated.

        Greedy with backtracking and fully deterministic: for the first
        unpaired participant the first eligible later participant is tried
        first. Pools are small (<= 50), so the recursion depth is bounded and
        the first-choice path almost always succeeds.
        """
        n = len(pool)
        if n % 2 != 0:
            raise ValueError("perfect matching requires an even pool")
        pairings: list[tuple[int, int]] = []

        def backtrack() -> bool:
            if len(pairings) * 2 == n:
                return True
            used = {p for pair in pairings for p in pair}
            a = next(p for p in pool if p not in used)
            used.add(a)
            for b in pool:
                if b in used or frozenset((a, b)) in self._played_pairs:
                    continue
                pairings.append((a, b))
                if backtrack():
                    return True
                pairings.pop()
            return False

        if not backtrack():
            raise ValueError("cannot schedule without repeating an opponent pair")
        return pairings

    # ------------------------------------------------------------------ #
    # standings
    # ------------------------------------------------------------------ #

    def standings(self) -> list[StandingRow]:
        """Ranking sorted by points desc → Buchholz desc → net_score desc →
        seed asc (Metis V1). Byes auto-count as 1 point / 0 net; draws give
        0.5 to both sides; unplayed real matches contribute nothing."""
        points: dict[int, float] = {pid: 0.0 for pid in self.participants}
        net: dict[int, float] = {pid: 0.0 for pid in self.participants}

        for r in self._schedule:
            for m in r.matches:
                if m.is_bye:
                    # Metis E2: bye = 1 point, 0 net score.
                    points[m.participant_a] += 1.0
                    continue
                res = self._results.get(m.match_id)
                if res is None:
                    continue
                if res.is_draw:
                    # Metis E1: draw = 0.5 points for both sides.
                    points[m.participant_a] += 0.5
                    points[m.participant_b] += 0.5
                else:
                    points[res.winner] += 1.0
                net[m.participant_a] += res.score_a - res.score_b
                net[m.participant_b] += res.score_b - res.score_a

        # Buchholz (对手分): sum of the final points of all played opponents
        # (recorded real matches only; byes contribute nothing).
        buchholz: dict[int, float] = {pid: 0.0 for pid in self.participants}
        for r in self._schedule:
            for m in r.matches:
                if m.is_bye or m.match_id not in self._results:
                    continue
                buchholz[m.participant_a] += points[m.participant_b]
                buchholz[m.participant_b] += points[m.participant_a]

        rows = [
            StandingRow(pid, points[pid], net[pid], buchholz[pid], self._seed_map[pid])
            for pid in self.participants
        ]
        rows.sort(key=lambda row: (-row.wins, -row.opponent_wins, -row.net_score, row.seed))
        return rows
