"""分组循环赛引擎 — RoundRobinEngine (todo 9).

Standard circle method (轮转法): the first participant stays fixed and the
others rotate one position per round, pairing position i against position n-1-i
in each round. Participants are split into groups of ``group_size`` (config
key, default 4); every group schedules its own round-robin and the global
schedule interleaves the group rounds (global round k = every group's k-th
round; a group with fewer rounds simply contributes nothing to the remaining
global rounds).

Fixed semantics (plan.md §七 + Metis review):
- E1 平局: a draw gives each side 0.5 wins (wins are floats).
- E2 轮空: an odd-sized group's circle method produces exactly one bye per
  round; a bye counts as 1 win / 0 net score and is scored automatically in
  ``standings`` (no result may be recorded for it).
- V1 同分决胜: wins desc → net_score desc → head-to-head (相互胜负) →
  participant id asc. The head-to-head scalar is the sum of a participant's
  scores in matches against opponents tied on (wins, net_score) — for a
  two-way tie that is exactly the mutual-match score.

Validation: raises ValueError when there are fewer than 2 participants, when
participants are duplicated, or when ``group_size`` is not an int >= 2. A
1-member trailing chunk is merged into the previous group (a single 1-person
group can never be formed). Pure logic — no DB, no I/O.
"""

from app.tournaments.base import MatchPlan, RoundPlan, StandingRow, TournamentEngine


class RoundRobinEngine(TournamentEngine):
    """Group round-robin engine built on the standard circle method."""

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

        group_size = self.config.get("group_size", 4)
        if not isinstance(group_size, int) or group_size < 2:
            raise ValueError("group_size must be an int >= 2")
        self.group_size = group_size

        self._groups: list[list[int]] = self._split_groups()
        self._seed_map: dict[int, int] = {pid: i + 1 for i, pid in enumerate(participants)}
        self._schedule = self._build_schedule()
        self._match_index: dict[int, MatchPlan] = {
            m.match_id: m for r in self._schedule for m in r.matches
        }

    # ------------------------------------------------------------------ #
    # group splitting
    # ------------------------------------------------------------------ #

    def _split_groups(self) -> list[list[int]]:
        """Slice participants into groups of group_size; a trailing chunk of
        size 1 is merged into the previous group (never left as a 1-person
        group). With >= 2 participants a lone size-1 group is impossible, so
        this merge always succeeds."""
        groups: list[list[int]] = []
        current: list[int] = []
        for pid in self.participants:
            current.append(pid)
            if len(current) == self.group_size:
                groups.append(current)
                current = []
        if current:
            if len(current) == 1:
                if not groups:
                    raise ValueError("cannot form a group of size 1")
                groups[-1].extend(current)
            else:
                groups.append(current)
        return groups

    # ------------------------------------------------------------------ #
    # schedule generation
    # ------------------------------------------------------------------ #

    def generate_schedule(self) -> list[RoundPlan]:
        """Return the (cached) interleaved group schedule. Idempotent."""
        return self._schedule

    def _build_schedule(self) -> list[RoundPlan]:
        """Circle-method schedule per group, interleaved by global round."""
        group_rounds = [self._circle_schedule(g) for g in self._groups]
        total_rounds = max(len(gr) for gr in group_rounds)
        match_id = 1
        rounds: list[RoundPlan] = []
        for r in range(total_rounds):
            matches: list[MatchPlan] = []
            for gr in group_rounds:
                if r < len(gr):
                    for a, b in gr[r]:
                        if b is None:
                            matches.append(MatchPlan(match_id, a, None, is_bye=True))
                        else:
                            matches.append(MatchPlan(match_id, a, b))
                        match_id += 1
            rounds.append(RoundPlan(r + 1, matches))
        return rounds

    def _circle_schedule(self, group: list[int]) -> list[list[tuple[int, int | None]]]:
        """Standard circle method (轮转法) for one group.

        Returns one list per round; each round is a list of (a, b) pairings.
        ``b is None`` marks a bye for ``a``. For an odd-sized group a dummy
        player is appended (so the table has an even count): the dummy never
        appears in the output — the player paired against it takes a bye.
        Round count: n-1 for even n, n for odd n (bye added).
        """
        players: list[int | None] = list(group)
        if len(players) % 2 == 1:
            players.append(None)  # dummy → bye slot
        fixed = players[0]
        rest = players[1:]
        rounds: list[list[tuple[int, int | None]]] = []
        for _ in range(len(players) - 1):
            current = [fixed, *rest]
            round_matches: list[tuple[int, int | None]] = []
            for i in range(len(current) // 2):
                a = current[i]
                b = current[len(current) - 1 - i]
                if a is None:  # keep the dummy on side b
                    a, b = b, a
                if b is None:
                    round_matches.append((a, None))
                else:
                    round_matches.append((a, b))
            rounds.append(round_matches)
            rest = [rest[-1], *rest[:-1]]  # rotate the non-fixed players
        return rounds

    # ------------------------------------------------------------------ #
    # standings
    # ------------------------------------------------------------------ #

    def standings(self) -> list[StandingRow]:
        """Ranking sorted by wins desc → net_score desc → head-to-head desc →
        participant id asc (Metis V1). Byes auto-count as 1 win / 0 net;
        unplayed real matches contribute nothing."""
        wins: dict[int, float] = {pid: 0.0 for pid in self.participants}
        net: dict[int, float] = {pid: 0.0 for pid in self.participants}

        for r in self._schedule:
            for m in r.matches:
                if m.is_bye:
                    # Metis E2: bye = automatic win, 0 net score.
                    wins[m.participant_a] += 1.0
                    continue
                res = self._results.get(m.match_id)
                if res is None:
                    continue
                if res.is_draw:
                    # Metis E1: draw = 0.5 wins for both sides.
                    wins[m.participant_a] += 0.5
                    wins[m.participant_b] += 0.5
                else:
                    wins[res.winner] += 1.0
                net[m.participant_a] += res.score_a - res.score_b
                net[m.participant_b] += res.score_b - res.score_a

        # Head-to-head (相互胜负): within each (wins, net_score) tie group, each
        # member's scalar is the sum of their scores in recorded matches against
        # other members of the same group.
        tie_groups: dict[tuple[float, float], list[int]] = {}
        for pid in self.participants:
            tie_groups.setdefault((wins[pid], net[pid]), []).append(pid)
        h2h: dict[int, float] = {pid: 0.0 for pid in self.participants}
        for tie_group in tie_groups.values():
            if len(tie_group) < 2:
                continue
            tie_set = set(tie_group)
            for r in self._schedule:
                for m in r.matches:
                    if m.is_bye or m.match_id not in self._results:
                        continue
                    if m.participant_a in tie_set and m.participant_b in tie_set:
                        res = self._results[m.match_id]
                        h2h[m.participant_a] += res.score_a
                        h2h[m.participant_b] += res.score_b

        rows = [
            StandingRow(pid, wins[pid], net[pid], h2h[pid], self._seed_map[pid])
            for pid in self.participants
        ]
        rows.sort(key=lambda row: (-row.wins, -row.net_score, -row.opponent_wins, row.participant_id))
        return rows
