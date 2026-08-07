"""单败淘汰赛引擎 — SingleElimEngine (todo 11).

Standard single-elimination bracket (单败淘汰). The bracket size is the next
power of two >= the participant count; the missing slots become byes (轮空) in
round 1, which auto-advance their recipient.

Fixed semantics (plan.md §七 + Metis review):
- E1 平局: draws are forbidden in single elimination — recording one raises
  ValueError("单败淘汰不允许平局").
- E2 轮空: a bye auto-advances its recipient and may never receive a result.
- Seeding: with config ``seeded=True`` participants are placed with the
  standard mirror method so seed 1 and seed 2 sit in opposite halves and can
  only meet in the final. Seed ranks come from input order (seed = index + 1)
  unless a config ``seeds`` map {pid: rank} is supplied; unseeded brackets
  place participants in input order.
- Third-place match: config ``third_place`` (default True) adds a single
  consolation match between the two semifinal losers, scheduled as its own
  round (round R+1, R = log2(bracket size)). It never blocks completion.
- Ranking: champion, runner-up, third-place result, then by elimination round
  desc (later elimination = higher rank), then seed asc.

Bracket structure: round 1 has B/2 matches with concrete slots (some byes);
round r has B/2**r matches whose participants are unknown at schedule time
(None/None) and are resolved from the recorded results of the feeding matches
when a result is recorded.

Validation: raises ValueError for a non-int list, fewer than 2 participants,
or duplicated participants. Pure logic — no DB, no I/O.
"""

from app.tournaments.base import MatchPlan, MatchResult, RoundPlan, StandingRow, TournamentEngine


class SingleElimEngine(TournamentEngine):
    """Single-elimination bracket engine (pure logic)."""

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
        self.seeded = bool(self.config.get("seeded", False))
        self.third_place = bool(self.config.get("third_place", True))

        self._B = self._bracket_size(len(participants))
        self._R = self._B.bit_length() - 1  # log2(B)

        self._slots: list[int | None] = self._build_slots()

        self._winners: dict[int, int] = {}
        self._feeders: dict[int, tuple[int, int]] = {}
        self._match_position: dict[int, tuple[int, int]] = {}
        self._resolved: dict[int, tuple[int, int]] = {}
        self._elim_round: dict[int, int] = {}
        self._final_match_id: int | None = None
        self._third_place_match_id: int | None = None

        self._schedule = self._build_schedule()
        self._match_index: dict[int, MatchPlan] = {
            m.match_id: m for r in self._schedule for m in r.matches
        }

    # ------------------------------------------------------------------ #
    # bracket construction
    # ------------------------------------------------------------------ #

    @staticmethod
    def _bracket_size(n: int) -> int:
        """Next power of two >= n."""
        size = 1
        while size < n:
            size *= 2
        return size

    def _build_slots(self) -> list[int | None]:
        """Place participants into the bracket's round-1 slots.

        Seeded: standard mirror method — seed ranks are placed so seed 1 and
        seed 2 occupy opposite halves; seed ranks above the participant count
        become byes. Unseeded: input order, with byes spread one per trailing
        pair so no round-1 pair is left empty on both sides.
        """
        n = len(self.participants)
        if self.seeded:
            seeds_cfg = self.config.get("seeds")
            if isinstance(seeds_cfg, dict):
                ranked = sorted(self.participants, key=lambda p: seeds_cfg.get(p, float("inf")))
            else:
                ranked = list(self.participants)
            order = [1]
            size = 2
            while size <= self._B:
                order = [s for pair in ((v, size + 1 - v) for v in order) for s in pair]
                size *= 2
            slots: list[int | None] = [None] * self._B
            for pos, seed_rank in enumerate(order):
                if seed_rank <= n:
                    slots[pos] = ranked[seed_rank - 1]
            return slots
        slots = [None] * self._B
        real_pairs = n - self._B // 2  # full pairs that get two players
        idx = 0
        for i in range(real_pairs):
            slots[2 * i] = self.participants[idx]
            slots[2 * i + 1] = self.participants[idx + 1]
            idx += 2
        for i in range(real_pairs, self._B // 2):
            slots[2 * i] = self.participants[idx]
            idx += 1
        return slots

    def _build_schedule(self) -> list[RoundPlan]:
        """Build rounds 1..R plus the optional third-place round (R+1)."""
        rounds: list[RoundPlan] = []
        match_id = 1

        # round 1: concrete slots; missing opponents become byes
        r1_matches: list[MatchPlan] = []
        for i in range(0, self._B, 2):
            a, b = self._slots[i], self._slots[i + 1]
            if a is None and b is None:
                continue  # cannot happen with the slot builders above
            if a is not None and b is not None:
                r1_matches.append(MatchPlan(match_id, a, b))
                self._match_position[match_id] = (1, len(r1_matches) - 1)
                match_id += 1
            else:
                recipient = a if a is not None else b
                r1_matches.append(MatchPlan(match_id, recipient, None, is_bye=True))
                self._winners[match_id] = recipient  # bye auto-advances
                self._match_position[match_id] = (1, len(r1_matches) - 1)
                match_id += 1
        rounds.append(RoundPlan(1, r1_matches))
        prev = r1_matches

        # rounds 2..R: participants resolved from the previous round
        for r in range(2, self._R + 1):
            count = self._B // (2**r)
            matches: list[MatchPlan] = []
            for i in range(count):
                mid = match_id
                self._feeders[mid] = (prev[2 * i].match_id, prev[2 * i + 1].match_id)
                matches.append(MatchPlan(mid, None, None))
                self._match_position[mid] = (r, i)
                match_id += 1
            rounds.append(RoundPlan(r, matches))
            prev = matches

        self._final_match_id = prev[0].match_id if prev else None

        # third-place match between the two semifinal losers
        if self.third_place and self._B >= 4:
            semifinals = rounds[self._R - 2].matches
            mid = match_id
            self._feeders[mid] = (semifinals[0].match_id, semifinals[1].match_id)
            self._third_place_match_id = mid
            self._match_position[mid] = (self._R + 1, 0)
            rounds.append(RoundPlan(self._R + 1, [MatchPlan(mid, None, None)]))
        return rounds

    def generate_schedule(self) -> list[RoundPlan]:
        """Return the (cached) bracket schedule. Idempotent."""
        return self._schedule

    # ------------------------------------------------------------------ #
    # result recording
    # ------------------------------------------------------------------ #

    def _loser_of(self, match_id: int) -> int | None:
        """Loser of a recorded match, or None when it has no result yet."""
        res = self._results.get(match_id)
        if res is None:
            return None
        pa, pb = self._resolved[match_id]
        return pa if res.winner == pb else pb

    def _resolve_participants(self, match_id: int) -> tuple[int, int]:
        """The two real participants of a match, resolved from results.

        Round-1 matches read their slots directly; later matches take the
        winners (or, for the third-place match, the losers) of their two
        feeding matches. Raises ValueError when a feeder has no result yet.
        """
        if match_id in self._resolved:
            return self._resolved[match_id]
        plan = self._match_index[match_id]
        pos = self._match_position[match_id]
        if pos[0] == 1:
            resolved = (plan.participant_a, plan.participant_b)
        elif match_id == self._third_place_match_id:
            feed_a, feed_b = self._feeders[match_id]
            adv_a = self._loser_of(feed_a)
            adv_b = self._loser_of(feed_b)
            if adv_a is None or adv_b is None:
                raise ValueError(f"match {match_id} cannot be played yet: previous round incomplete")
            resolved = (adv_a, adv_b)
        else:
            feed_a, feed_b = self._feeders[match_id]
            adv_a = self._winners.get(feed_a)
            adv_b = self._winners.get(feed_b)
            if adv_a is None or adv_b is None:
                raise ValueError(f"match {match_id} cannot be played yet: previous round incomplete")
            resolved = (adv_a, adv_b)
        self._resolved[match_id] = resolved
        return resolved

    def record_result(self, match_id: int, result: MatchResult) -> None:
        """Store a result; participants of later rounds are resolved from the
        recorded feeding matches (byes auto-advance their recipient)."""
        plan = self._match_index.get(match_id)
        if plan is None:
            raise ValueError(f"unknown match_id: {match_id}")
        if plan.is_bye:
            raise ValueError(f"bye match {match_id} is scored automatically and cannot have a result")
        if match_id in self._results:
            raise ValueError(f"result already recorded for match {match_id}")
        if result.is_draw:
            raise ValueError("单败淘汰不允许平局")
        resolved_a, resolved_b = self._resolve_participants(match_id)
        if result.winner not in (resolved_a, resolved_b):
            raise ValueError(
                f"winner must be one of the match participants "
                f"({resolved_a} / {resolved_b}), got {result.winner!r}"
            )
        self._results[match_id] = result
        self._winners[match_id] = result.winner
        loser = resolved_a if result.winner == resolved_b else resolved_b
        self._elim_round[loser] = self._match_position[match_id][0]

    # ------------------------------------------------------------------ #
    # standings / completion
    # ------------------------------------------------------------------ #

    def standings(self) -> list[StandingRow]:
        """Ranking: champion, runner-up, third-place winner/loser, then all
        other participants by elimination round desc, then seed asc. When the
        third-place match is unplayed, the two semifinal losers tie at 3rd/4th
        and are ordered by seed asc. wins = recorded non-bye match wins;
        losses = recorded losses; draws 恒 0（单败禁平局）; points = wins."""
        wins: dict[int, float] = {pid: 0.0 for pid in self.participants}
        losses: dict[int, float] = {pid: 0.0 for pid in self.participants}
        net: dict[int, float] = {pid: 0.0 for pid in self.participants}
        for mid, res in self._results.items():
            wins[res.winner] += 1.0
            pa, pb = self._resolved[mid]
            losses[pa if res.winner == pb else pb] += 1.0
            net[pa] += res.score_a - res.score_b
            net[pb] += res.score_b - res.score_a

        champion = runner_up = third = fourth = None
        if self._final_match_id is not None and self._final_match_id in self._results:
            res = self._results[self._final_match_id]
            champion = res.winner
            pa, pb = self._resolved[self._final_match_id]
            runner_up = pa if res.winner == pb else pb
        if self._third_place_match_id is not None and self._third_place_match_id in self._results:
            res = self._results[self._third_place_match_id]
            third = res.winner
            pa, pb = self._resolved[self._third_place_match_id]
            fourth = pa if res.winner == pb else pb

        explicitly_ranked = {p for p in (champion, runner_up, third, fourth) if p is not None}
        front = [p for p in (champion, runner_up, third, fourth) if p is not None]
        remaining = [p for p in self.participants if p not in explicitly_ranked]
        remaining.sort(key=lambda p: (-self._elim_round.get(p, self._R + 1), self._seed_map[p]))
        order = front + remaining
        return [
            StandingRow(
                p,
                wins[p],
                net[p],
                0.0,
                self._seed_map[p],
                losses=losses[p],
                draws=0.0,
                points=wins[p],
            )
            for p in order
        ]

    def is_complete(self) -> bool:
        """True once the final (champion-deciding) match has a result.

        The optional third-place match does not block completion.
        """
        return self._final_match_id is not None and self._final_match_id in self._results
