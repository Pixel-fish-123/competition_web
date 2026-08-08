"""瑞士轮赛制引擎 — SwissEngine (todo 10).

TRUE round-by-round Swiss pairing: the round count defaults to
``ceil(log2(n)) + 1`` (issue 7 用户确认：log2n 向上取整 +1 轮，动态随参赛
人数调整；不再受 7 轮上限约束，参赛人数 ≤50 时自然 ≤7 轮), but only round 1
is materialized at construction time (seed order — no results exist yet, so the
standings order degenerates to seed order). Each subsequent round is generated
by ``generate_next_round()`` ONLY once every real match of the previous round
has been recorded, and it pairs participants by the CURRENT standings —
V1 chain: points desc → Buchholz (对手分) desc → net desc → seed asc. The
schedule is therefore a pure deterministic function of (participants, seed
order, recorded results): rebuilding the engine and replaying the same results
reproduces identical pairings and match_ids.

Fixed semantics (plan.md §七 + Metis review):
- E1 平局: a draw gives each side 0.5 points (wins 不计入胜场；draws 计数)。
- E2 轮空: a bye counts as 1 win / 1 point / 0 net score and is scored
  automatically in ``standings`` (no result may be recorded for it). Byes are
  spread so no participant receives two while un-byed participants remain; the
  bye goes to the lowest-ranked participant that has not yet had one.
  **计分门槛（用户确认）**：轮空只在轮空所在轮次已有真实对局结果（该轮已
  开始）后计入 —— 比赛未开始、或下一轮虽已物化但尚未开打时，该轮空不计分。
- Buchholz (对手分): the sum of the FINAL points of all opponents a participant
  has actually played (recorded real matches only; byes contribute nothing).
- V1 同分决胜: points desc → Buchholz desc → net_score desc → seed asc.

StandingRow field mapping (issue 9/11：展示胜场/败场/平局):
- ``wins`` = 胜场数（bye 1.0，平局不计入）
- ``losses`` = 败场数、``draws`` = 平局数
- ``points`` = wins + 0.5·draws（排序主键）；``opponent_wins`` 携带 Buchholz。

Validation: raises ValueError when there are fewer than 2 participants, when
participants are duplicated, or when ``rounds`` is present but not a positive
int. Pure logic — no DB, no I/O.
"""

import math

from app.tournaments.base import MatchPlan, RoundPlan, StandingRow, TournamentEngine


class SwissEngine(TournamentEngine):
    """Round-by-round Swiss-system engine."""

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
            # issue 7：轮数 = ceil(log2 n) + 1，随参赛人数动态调整。
            self._rounds = math.ceil(math.log2(len(participants))) + 1
        elif not isinstance(rounds, int) or rounds <= 0:
            raise ValueError("rounds must be a positive int")
        else:
            self._rounds = rounds

        self._played_pairs: set[frozenset[int]] = set()
        self._bye_taken: set[int] = set()
        self._next_match_id = 1

        # Only round 1 is materialized at construction: with no results recorded
        # the standings order degenerates to seed order, so round 1 is exactly
        # the seed-order round of the original pre-generated schedule.
        self._schedule = [self._build_round(1, list(self.participants))]
        self._match_index: dict[int, MatchPlan] = {
            m.match_id: m for r in self._schedule for m in r.matches
        }

    # ------------------------------------------------------------------ #
    # schedule generation
    # ------------------------------------------------------------------ #

    def generate_schedule(self) -> list[RoundPlan]:
        """Return the rounds materialized SO FAR (round 1 initially; more as
        ``generate_next_round`` is called). Idempotent."""
        return list(self._schedule)

    def generate_next_round(self) -> RoundPlan | None:
        """Materialize the next round iff the last one is fully recorded.

        Pure deterministic function of (participants, seed order, ``_results``):
        it pairs the current ``standings()`` order (points → Buchholz → net →
        seed), so rebuilding the engine and replaying the same results in the
        same order reproduces identical pairings and match_ids.
        """
        if len(self._schedule) >= self._rounds:
            return None
        last = self._schedule[-1]
        if not all(m.is_bye or m.match_id in self._results for m in last.matches):
            return None  # previous round not complete
        order = [row.participant_id for row in self.standings()]  # V1 tie-break order
        plan = self._build_round(len(self._schedule) + 1, order)
        self._schedule.append(plan)
        self._match_index.update({m.match_id: m for m in plan.matches})
        return plan

    def _build_round(self, round_number: int, order: list[int]) -> RoundPlan:
        """Pair one round from an already-ordered pool of participants.

        An odd field gives the last eligible participant (lowest-ranked that has
        not yet had a bye) a bye — never twice while un-byed alternatives
        remain; the remaining pool is perfect-matched with backtracking so no
        opponent pair is repeated across the whole tournament.
        """
        pool = list(order)
        matches: list[MatchPlan] = []
        if len(pool) % 2 == 1:
            bye = self._pick_bye_recipient(pool)
            pool.remove(bye)
            self._bye_taken.add(bye)
            matches.append(MatchPlan(self._next_match_id, bye, None, is_bye=True))
            self._next_match_id += 1
        for a, b in self._perfect_match(pool):
            matches.append(MatchPlan(self._next_match_id, a, b))
            self._played_pairs.add(frozenset((a, b)))
            self._next_match_id += 1
        return RoundPlan(round_number, matches)

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
    # standings / completion
    # ------------------------------------------------------------------ #

    def standings(self) -> list[StandingRow]:
        """Ranking sorted by points desc → Buchholz desc → net_score desc →
        seed asc (Metis V1). Byes auto-count as 1 win / 1 point / 0 net; draws
        give 0.5 points to both sides (胜场/败场/平局分别计数，issue 9/11);
        unplayed real matches contribute nothing."""
        wins: dict[int, float] = {pid: 0.0 for pid in self.participants}
        losses: dict[int, float] = {pid: 0.0 for pid in self.participants}
        draws: dict[int, float] = {pid: 0.0 for pid in self.participants}
        points: dict[int, float] = {pid: 0.0 for pid in self.participants}
        net: dict[int, float] = {pid: 0.0 for pid in self.participants}

        for r in self._schedule:
            # 轮空计分门槛（用户确认）：轮空所在轮次自身已有真实对局产生结果
            # （该轮已开始）时才计 1 胜/1 分。下一轮尚未开打时，即使该轮
            # 轮空行已随赛程物化（如 5 人赛第 2 轮的轮空），也不提前加分。
            round_started = any(
                not m.is_bye and m.match_id in self._results for m in r.matches
            )
            for m in r.matches:
                if m.is_bye:
                    # Metis E2: bye = 1 win / 1 point, 0 net score.
                    if not round_started:
                        continue
                    wins[m.participant_a] += 1.0
                    points[m.participant_a] += 1.0
                    continue
                res = self._results.get(m.match_id)
                if res is None:
                    continue
                if res.is_draw:
                    # Metis E1: draw = 0.5 points for both sides.
                    draws[m.participant_a] += 1.0
                    draws[m.participant_b] += 1.0
                    points[m.participant_a] += 0.5
                    points[m.participant_b] += 0.5
                else:
                    wins[res.winner] += 1.0
                    points[res.winner] += 1.0
                    loser = (
                        m.participant_b
                        if res.winner == m.participant_a
                        else m.participant_a
                    )
                    losses[loser] += 1.0
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
            StandingRow(
                pid,
                wins[pid],
                net[pid],
                buchholz[pid],
                self._seed_map[pid],
                losses=losses[pid],
                draws=draws[pid],
                points=points[pid],
            )
            for pid in self.participants
        ]
        rows.sort(key=lambda row: (-row.points, -row.opponent_wins, -row.net_score, row.seed))
        return rows

    def is_complete(self) -> bool:
        """True once every round has been materialized and every real match in
        the materialized schedule has a result.

        The base implementation would wrongly report complete on a partially
        materialized schedule (it only inspects the rounds that exist); Swiss
        must also require ``len(_schedule) >= _rounds``.
        """
        return len(self._schedule) >= self._rounds and all(
            m.is_bye or m.match_id in self._results
            for r in self._schedule
            for m in r.matches
        )
