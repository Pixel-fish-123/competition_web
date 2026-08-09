from __future__ import annotations
import random

from .rules import RULES

DIFFICULTY_TABLE = [
    {"label": "CHAOS 15+", "diff_score": 15, "tier": 8},
    {"label": "CHAOS 15", "diff_score": 10, "tier": 7},
    {"label": "CHAOS 14+", "diff_score": 8, "tier": 6},
    {"label": "CHAOS 13+", "diff_score": 6, "tier": 5},
    {"label": "CHAOS 12+", "diff_score": 5, "tier": 4},
    {"label": "CHAOS 11+", "diff_score": 4, "tier": 3},
    {"label": "CHAOS 10", "diff_score": 3, "tier": 2},
    {"label": "CHAOS 8", "diff_score": 2, "tier": 1},
]

TASK_TABLE = [
    {"name": t["name"], "weight": t["weight"], "task_bonus": t["bonus"]}
    for t in RULES["tasks"]
]


def _weighted_choice(table: list[dict], rng: random.Random, key: str = "weight") -> dict:
    total = sum(item[key] for item in table)
    r = rng.uniform(0, total)
    upto = 0
    for item in table:
        upto += item[key]
        if r <= upto:
            return item
    return table[-1]


def generate_tasks(seed: int | None = None) -> list[dict]:
    # 局部随机源，避免污染进程全局 random 状态（与 song_lib 的 rng 用法一致）
    rng = random.Random(seed)

    tiers = [d["tier"] for d in DIFFICULTY_TABLE]

    chosen: list[dict] = []
    for _ in range(21):
        tier = rng.choice(tiers)
        diff = next(x for x in DIFFICULTY_TABLE if x["tier"] == tier)
        chosen.append(dict(diff))

    top_tier = max(d["tier"] for d in DIFFICULTY_TABLE)
    top_indices = [i for i, c in enumerate(chosen) if c["tier"] == top_tier]
    if len(top_indices) > 1:
        keep = rng.choice(top_indices)
        fallback = next(d for d in DIFFICULTY_TABLE if d["tier"] == top_tier - 1)
        for i in top_indices:
            if i != keep:
                chosen[i] = dict(fallback)
    elif len(top_indices) == 0:
        upgrade_idx = rng.randint(0, 20)
        chosen[upgrade_idx] = dict(next(
            d for d in DIFFICULTY_TABLE if d["tier"] == top_tier
        ))

    cells_data: list[dict] = []
    for cell_id in range(21):
        diff = chosen[cell_id]
        task = _weighted_choice(TASK_TABLE, rng)
        bonus = task["task_bonus"]
        if cell_id == 0:
            bonus = 10
            task = {"name": "L1源头 (固定+10)", "task_bonus": 10}
        cells_data.append({
            "id": cell_id,
            "diff_score": diff["diff_score"],
            "difficulty_label": diff["label"],
            "task_name": task["name"],
            "task_bonus": bonus,
        })
    return cells_data
