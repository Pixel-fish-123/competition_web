from __future__ import annotations

import random
from dataclasses import dataclass

from .rules import RULES

VALID_TYPES = {"Glitch", "Chaos", "Hard"}


@dataclass
class Song:
    name: str
    type: str
    level: str
    diff_score: int = 0
    difficulty_label: str = ""

    def __post_init__(self) -> None:
        self.diff_score = level_to_score(self.level)
        self.difficulty_label = f"{self.type} {self.level}"


def level_to_score(level: str) -> int:
    """Map a difficulty level string to a diff_score (distinguishes '+' suffix)."""
    has_plus = level.strip().endswith("+")
    n = int(level.strip().rstrip("+"))
    if n >= 16:
        return 15
    if n == 15:
        return 15 if has_plus else 10
    if n == 14:
        return 8
    if n == 13:
        return 6
    if n == 12:
        return 5
    if n == 11:
        return 4
    if n in (9, 10):
        return 3
    if n <= 8:
        return 2
    return 0


def parse_song_library(data) -> list[Song]:
    """Validate a song-library JSON structure and return a list of Song."""
    if not isinstance(data, dict) or "songs" not in data:
        raise ValueError("歌曲库格式错误：需要 {\"songs\": [...]}")
    songs_raw = data["songs"]
    if not isinstance(songs_raw, list) or len(songs_raw) == 0:
        raise ValueError("歌曲库格式错误：songs 必须是非空数组")

    songs: list[Song] = []
    seen_names: set[str] = set()
    for i, item in enumerate(songs_raw):
        idx = i + 1
        if not isinstance(item, dict):
            raise ValueError(f"第 {idx} 首歌曲格式错误：应为对象")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"第 {idx} 首歌曲缺少 name")
        name = name.strip()
        stype = item.get("type")
        if stype not in VALID_TYPES:
            raise ValueError(f"第 {idx} 首歌曲 type 无效：{stype!r}（应为 Glitch/Chaos/Hard）")
        level = item.get("level")
        try:
            score = level_to_score(level)
        except (TypeError, ValueError):
            raise ValueError(f"第 {idx} 首歌曲 level 无效：{level!r}")
        if score == 0:
            raise ValueError(f"第 {idx} 首歌曲 level 无效：{level!r}")
        if name in seen_names:
            raise ValueError(f"第 {idx} 首歌曲 name 重复：{name!r}")
        seen_names.add(name)
        songs.append(Song(name=name, type=stype, level=str(level)))

    return songs


def _weighted_choice(table, rng: random.Random):
    """Weighted random pick from a list of dicts with a 'weight' key."""
    total = sum(item["weight"] for item in table)
    r = rng.uniform(0, total)
    upto = 0.0
    for item in table:
        upto += item["weight"]
        if upto >= r:
            return item
    return table[-1]


# Region definitions: fixed capacity per region.
# NOTE: 'energy' = L6 layer (ids 15-20), NOT the energy cells (21-26).
_REGIONS = {
    "top": (0, 0),        # {0}
    "mid": (1, 9),        # {1..9}
    "shallow": (10, 14),  # {10..14}
    "energy": (15, 20),   # {15..20}
}
_WEIGHT_MAP = {"high": 3, "medium": 2, "low": 1}
_REGION_ORDER = ["energy", "mid", "shallow", "top"]


def generate_tasks_from_songs(songs: list[Song], seed=None) -> list[dict]:
    """Generate 21 cells_data from a song library via the templated pipeline."""
    rng = random.Random(seed)

    if len(songs) < 23:
        raise ValueError("歌曲库至少需要 23 首")

    # 23 no-repeat sample, each gets a weighted task.
    sampled = rng.sample(songs, 23)
    tasks = RULES["tasks"]
    assigned = []
    for song in sampled:
        task = _weighted_choice(tasks, rng)
        total = song.diff_score + task["bonus"]
        assigned.append((total, song, task))

    # Sort by total desc, drop highest (index 0) and lowest (index -1) -> 21.
    assigned.sort(key=lambda x: x[0], reverse=True)
    kept = assigned[1:-1]

    # Template selection.
    template = rng.choice(["A", "B", "C"])
    region_weights = RULES["templates"][template]

    # Sort regions by (weight desc, fixed order energy->mid->shallow->top).
    sorted_regions = sorted(
        _REGION_ORDER,
        key=lambda name: (-_WEIGHT_MAP[region_weights[name]], _REGION_ORDER.index(name)),
    )

    # Greedy allocation: tasks in score-desc order, each into the first region
    # (in sorted order) with remaining capacity > 0, at a random empty cell.
    capacities = {name: _REGIONS[name][1] - _REGIONS[name][0] + 1 for name in _REGION_ORDER}
    cells_data: list[dict] = []
    for total, song, task in kept:
        placed = False
        for region in sorted_regions:
            if capacities[region] > 0:
                start, end = _REGIONS[region]
                empty = [cid for cid in range(start, end + 1)
                         if cid not in {c["id"] for c in cells_data}]
                cid = rng.choice(empty)
                cells_data.append({
                    "id": cid,
                    "diff_score": song.diff_score,
                    "difficulty_label": song.difficulty_label,
                    "song_name": song.name,
                    "song_type": song.type,
                    "song_level": song.level,
                    "task_name": task["name"],
                    "task_bonus": task["bonus"],
                })
                capacities[region] -= 1
                placed = True
                break
        if not placed:
            raise RuntimeError("任务分配失败：区域容量不足")

    # Force L1 (id=0) fixed bonus and task name.
    for cell in cells_data:
        if cell["id"] == 0:
            cell["task_bonus"] = 10
            cell["task_name"] = "L1源头 (固定+10)"

    # Return ordered by id so id=0 (L1) is at index 0.
    cells_data.sort(key=lambda c: c["id"])
    return cells_data
