from __future__ import annotations

import random
import re
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
        self.diff_score = level_to_score(self.level, self.type)
        self.difficulty_label = f"{self.type} {self.level}"


def level_to_score(level: str, song_type: str = "") -> int:
    """Map a difficulty level to a 10-scale song score (Cytus II 2026 难度表).

    歌曲难度部分占单格总分 50%（0~10 分制）。纯数值制：13 → 7、14 → 8；
    带 `+` 的定数在原等级基础上 +1（封顶 10）；16 及以上封顶 10。
    `song_type` 参数仅为兼容旧调用保留，**不影响分值**。
    """
    if not isinstance(level, str) or not level.strip():
        raise ValueError(f"level 无效：{level!r}")
    text = level.strip()
    has_plus = text.endswith("+")
    match = re.search(r"\d+", text)
    if not match:
        raise ValueError(f"level 无效：{level!r}")
    n = int(match.group())
    if n <= 3:
        base = 1
    elif n <= 6:
        base = 2
    elif n <= 8:
        base = 3
    elif n <= 10:
        base = 4
    elif n == 11:
        base = 5
    elif n == 12:
        base = 6
    elif n == 13:
        base = 7
    elif n == 14:
        base = 8
    elif n == 15:
        base = 9
    else:
        return 10  # >= 16 封顶
    return min(base + (1 if has_plus else 0), 10)


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


# Region definitions: fixed capacity per region（烈度分区，任务与难度设计 v1）。
# - top    = L1（id 0，能量引擎，最后单独填充：剩余 3 首中最难 +10）
# - l2     = L2（id 1-2）：低分区（一定较低）
# - mid    = L3+L4（id 3-9）：烈度最高区（承载高难任务）
# - shallow= L5（id 10-14）：次低区（不出现过高难度）
# - energy = L6（id 15-20）：低分区（邻接能源的接入层）
_REGIONS = {
    "top": (0, 0),        # {0}
    "l2": (1, 2),         # {1..2}
    "mid": (3, 9),        # {3..9}
    "shallow": (10, 14),  # {10..14}
    "energy": (15, 20),   # {15..20}
}
_WEIGHT_MAP = {"high": 3, "medium": 2, "low": 1}
# 20 个普通格任务分配的 4 个区域（top/L1 最后单独填充）
_ALLO_CAP = {
    "l2": (1, 2),
    "mid": (3, 9),
    "shallow": (10, 14),
    "energy": (15, 20),
}
# 固定采用「中间分数高的模板」：mid（中腹）权重 high（中腹对峙），不随机三模板
_FIXED_TEMPLATE = "C"
_SAMPLE_COUNT = 25     # 第一步：随机抽 25 首
_DROP_COUNT = 2        # 第二步：按定数删最难/最简各 1 首 -> 23
_ALLOC_COUNT = 20      # 第三步：23 抽 20 配任务（剩余 3 首供 L1）


def _song_key(song: Song) -> tuple[int, int]:
    """歌曲定数排序键：level 数值为主，加号后缀修正（15+ > 15）。"""
    m = re.search(r"\d+", song.level or "")
    n = int(m.group()) if m else 0
    plus = 1 if (song.level or "").strip().endswith("+") else 0
    return (n, plus)


def generate_tasks_from_songs(songs: list[Song], seed=None,
                              return_template: bool = False):
    """Generate 21 cells_data from a song library via the templated pipeline.

    流水线（任务与难度设计 v1）：
    1. 从歌曲库随机抽 25 首；
    2. 按定数删去最难与最简各 1 首 -> 23 首；
    3. 从 23 首中抽 20 首，按任务表权重随机分配任务；
    4. 套「中腹高分」固定模板（mid=high），按区域权重贪心填 L2~L6（id 1-20）；
    5. L1 最后填充：从剩余 3 首中选定数最高的一首，默认 +10 分。

    ``return_template=True`` 时返回 (cells_data, template)，供平衡性模拟统计
    （默认 False 保持原返回结构，向后兼容）。
    """
    rng = random.Random(seed)

    if len(songs) < _SAMPLE_COUNT:
        raise ValueError(f"歌曲库至少需要 {_SAMPLE_COUNT} 首")

    # 1) 随机抽 25 首；2) 按定数删最难/最简各 1 -> 23
    sampled = rng.sample(songs, _SAMPLE_COUNT)
    ordered = sorted(sampled, key=_song_key)
    kept = ordered[_DROP_COUNT // 2: -(_DROP_COUNT // 2)]  # 去头尾各 1

    # 3) 23 抽 20，按任务表权重随机分配任务
    chosen = rng.sample(kept, _ALLOC_COUNT)
    tasks = RULES["tasks"]
    assigned = []
    for song in chosen:
        task = _weighted_choice(tasks, rng)
        assigned.append((song.diff_score + task["bonus"], song, task))
    assigned.sort(key=lambda x: x[0], reverse=True)

    # 4) 固定「中腹高分」模板，按区域权重贪心填 L2~L6（容量恰为 20）
    template = _FIXED_TEMPLATE
    region_weights = RULES["templates"][template]
    sorted_regions = sorted(
        _ALLO_CAP,
        key=lambda name: (-_WEIGHT_MAP[region_weights[name]], name),
    )
    capacities = {name: end - start + 1 for name, (start, end) in _ALLO_CAP.items()}
    cells_data: list[dict] = []
    for total, song, task in assigned:
        placed = False
        for region in sorted_regions:
            if capacities[region] > 0:
                start, end = _ALLO_CAP[region]
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

    # 5) L1 最后填充：23 首中未被挑选的 3 首里选定数最高一首，默认 +10
    remaining = [s for s in kept if s not in chosen]
    l1_song = max(remaining, key=_song_key)
    cells_data.append({
        "id": 0,
        "diff_score": l1_song.diff_score,
        "difficulty_label": l1_song.difficulty_label,
        "song_name": l1_song.name,
        "song_type": l1_song.type,
        "song_level": l1_song.level,
        "task_name": "L1源头 (固定+10)",
        "task_bonus": 10,
    })

    # Return ordered by id so id=0 (L1) is at index 0.
    cells_data.sort(key=lambda c: c["id"])
    if return_template:
        return cells_data, template
    return cells_data
