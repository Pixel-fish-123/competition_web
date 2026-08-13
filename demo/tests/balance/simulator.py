"""平衡性对战模拟器（蒙特卡洛）。

在真实棋盘（controller.board）上复用 controller.game.GameController 的完整规则
（激活 / 新包围 / 计分 / 顶端直胜 / 更新链），把「占领」包装为耗时任务：
每方最多并行 team_size 个挑战，任务耗时由 TimeModel(总分) 决定，时间推进到
任务完成事件，再触发一次真实占领。25 分钟限时或顶端直胜结束一局。

策略为启发式评分（可配置权重 + 噪声），目标是产生有代表性的攻防对抗，
用于统计「不同分数格子的实际挑战时间」与「双方胜率」。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from controller.game import GameController
from controller.song_lib import Song, generate_tasks_from_songs

try:                                   # pytest 包模式
    from .models import BalanceConfig
except ImportError:                    # 直接脚本模式（python tests/balance/run_balance.py）
    from models import BalanceConfig

_L1 = 0
_ENERGY_BASE = range(15, 21)   # L6：邻接能源的接入层


@dataclass
class MatchResult:
    seed: int
    winner: str | None            # "defender" / "attacker" / "draw"
    win_type: str | None          # "top" / "timeout" / None
    defender_score: float
    attacker_score: float
    defender_cells: int
    attacker_cells: int
    l1_holder: str | None
    encirclement_count: int = 0   # 本局包围成立次数
    l1_challenges: int = 0        # 本局 L1 挑战次数（双方合计）
    template: str = ""            # 本局任务模板 A/B/C
    occupation_times: list = field(default_factory=list)  # [(total_score, minutes)]

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "winner": self.winner,
            "win_type": self.win_type,
            "defender_score": self.defender_score,
            "attacker_score": self.attacker_score,
            "defender_cells": self.defender_cells,
            "attacker_cells": self.attacker_cells,
            "l1_holder": self.l1_holder,
            "encirclement_count": self.encirclement_count,
            "l1_challenges": self.l1_challenges,
            "template": self.template,
        }


@dataclass
class _Task:
    team: str
    cell_id: int
    kind: str                  # "cell" | "l1"
    start: float
    end: float
    score: int | None = None
    tp: float | None = None
    done: bool = False


def _defender_score(g: GameController, cell_id: int, cfg: BalanceConfig,
                    rng: random.Random) -> float:
    cell = g.cells[cell_id]
    if cell.owner is not None or cell.is_energy:
        return float("-inf")
    score = cfg.d_ratio * (cell.total_score / cfg.time_model.minutes(cell.total_score))
    if cell_id in (1, 2):                      # L2 封顶位
        score += cfg.d_seal_top
    if any(g.cells[n].owner == "attacker" and g.cells[n].activated
           for n in cell.neighbors):           # 切断攻击方激活块
        score += cfg.d_cut
    score += cfg.d_wall * sum(
        1 for n in cell.neighbors if g.cells[n].owner == "defender"
    )
    return score + rng.gauss(0, cfg.noise)


def _attacker_score(g: GameController, cell_id: int, cfg: BalanceConfig,
                    rng: random.Random) -> float:
    cell = g.cells[cell_id]
    if cell.owner is not None or cell.is_energy:
        return float("-inf")
    score = cfg.a_ratio * (cell.total_score / cfg.time_model.minutes(cell.total_score))
    if cell_id in _ENERGY_BASE:                # L6 能源接入
        score += cfg.a_energy_base
    score += cfg.a_extend * sum(
        1 for n in cell.neighbors
        if g.cells[n].owner == "attacker" and g.cells[n].activated
    )
    score += cfg.a_top_pull * (6 - cell.layer)  # 向 L1（浅层）牵引
    if cell_id in (1, 2):                        # L2 冲顶关键格
        score += cfg.a_top_claim
    return score + rng.gauss(0, cfg.noise)


def _choose_target(g: GameController, team: str, cfg: BalanceConfig,
                   rng: random.Random, pending: set[int]):
    """返回 (cell_id, kind, score, tp) 或 None（无可选目标）。"""
    if team == "attacker":
        # 攻击方冲顶：已有激活的 L3 格（路径过半）且 L1 未被己方持有 -> 提前挑战 L1
        # （占下 L1 后，一旦 L2 通路激活，L1 随更新链激活即触发顶端直胜）
        has_activated_l3 = any(
            g.cells[cid].owner == "attacker" and g.cells[cid].activated
            for cid in (3, 4, 5)
        )
        if has_activated_l3 and g.l1_high_team != "attacker":
            return (_L1, "l1", rng.randint(cfg.l1_score_lo, cfg.l1_score_hi),
                    round(rng.uniform(cfg.l1_tp_lo, cfg.l1_tp_hi), 2))
        scorer = _attacker_score
    else:
        # 防守方守 L1：攻击方持有 L1 时优先夺回（防顶端直胜）
        if g.l1_high_team == "attacker":
            return (_L1, "l1", rng.randint(cfg.l1_score_lo, cfg.l1_score_hi),
                    round(rng.uniform(cfg.l1_tp_lo, cfg.l1_tp_hi), 2))
        scorer = _defender_score

    best_id, best_score = None, float("-inf")
    for cid in range(1, 21):                   # 普通格（L1 单独处理）
        if cid in pending:
            continue
        s = scorer(g, cid, cfg, rng)
        if s > best_score:
            best_id, best_score = cid, s
    if best_id is None:
        return None
    return (best_id, "cell", None, None)


def simulate_match(songs: list[Song], seed: int, cfg: BalanceConfig) -> MatchResult:
    """模拟一局对战，返回结算结果与统计样本（含包围次数 / L1 挑战次数 / 模板）。"""
    rng = random.Random(seed)
    cells_data, template = generate_tasks_from_songs(songs, seed=seed, return_template=True)
    g = GameController()
    g.init(cells_data)

    t = 0.0
    tasks: dict[str, list[_Task]] = {"defender": [], "attacker": []}
    occupation_times: list = []
    l1_challenges = 0

    def schedule(team: str, now: float) -> None:
        active = sum(1 for tk in tasks[team] if not tk.done)
        while active < cfg.team_size:
            pending = {tk.cell_id for tk in tasks[team] if not tk.done}
            choice = _choose_target(g, team, cfg, rng, pending)
            if choice is None:
                break
            cell_id, kind, score, tp = choice
            if kind == "l1":
                dur = cfg.l1_challenge_minutes
            else:
                dur = cfg.time_model.minutes(g.cells[cell_id].total_score)
            tasks[team].append(_Task(team, cell_id, kind, now, now + dur, score, tp))
            active += 1

    schedule("defender", 0.0)
    schedule("attacker", 0.0)

    while t < cfg.time_limit_minutes and not g.game_over:
        # 下一个完成事件（双方任务）
        ends = [tk.end for team in tasks.values() for tk in team if not tk.done]
        if not ends:
            break
        next_t = min(ends)
        if next_t >= cfg.time_limit_minutes:
            t = cfg.time_limit_minutes
            break
        t = next_t

        # 完成所有到点任务（同一时刻按列表顺序逐个执行）
        for team in ("defender", "attacker"):
            for tk in tasks[team]:
                if tk.done or tk.end > t:
                    continue
                tk.done = True
                if tk.kind == "l1":
                    l1_challenges += 1
                    g.occupy(_L1, tk.team, score=tk.score, tp=tk.tp)
                    occupation_times.append((0, t - tk.start))
                else:
                    cell = g.cells[tk.cell_id]
                    if g.occupy(tk.cell_id, tk.team):
                        occupation_times.append((cell.total_score, t - tk.start))

        # 补足任务
        schedule("defender", t)
        schedule("attacker", t)

    if not g.game_over:
        g.end_game()

    def count(team: str) -> int:
        return sum(1 for c in g.cells[:21] if c.owner == team)

    return MatchResult(
        seed=seed,
        winner=g.winner,
        win_type=g.win_type,
        defender_score=g.defender_score,
        attacker_score=g.attacker_score,
        defender_cells=count("defender"),
        attacker_cells=count("attacker"),
        l1_holder=g.l1_high_team,
        encirclement_count=g.encirclement_count,
        l1_challenges=l1_challenges,
        template=template,
        occupation_times=occupation_times,
    )


def run_tournament(songs: list[Song], games: int, seed: int,
                   cfg: BalanceConfig) -> list[MatchResult]:
    """跑 games 局蒙特卡洛，返回全部结果（种子依次递增，可复现）。"""
    return [simulate_match(songs, seed + i, cfg) for i in range(games)]
