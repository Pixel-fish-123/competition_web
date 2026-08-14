"""歌曲库测试：level→分值 / 校验错误（带下标中文）/ 23→21 流水线。

运行：cd demo && python -m pytest tests/test_song_lib.py -q
"""

import pytest

from controller.song_lib import (
    Song,
    generate_tasks_from_songs,
    level_to_score,
    parse_song_library,
)


def make_songs(count: int = 50, level: str = "12") -> list[Song]:
    return parse_song_library({
        "songs": [{"name": f"Song{i}", "type": "Chaos", "level": level}
                  for i in range(count)]
    })


# ---------------------------------------------------------------- level 映射（10 分制）


def test_level_to_score_boundaries():
    cases = {
        "1": 1, "2": 1, "3": 1,
        "4": 2, "5": 2, "6": 2,
        "7": 3, "8": 3,
        "9": 4, "10": 4,
        "11": 5,
        "12": 6,
        "13": 7,
        "14": 8,
        "15": 9,
        "15+": 10, "16": 10, "16+": 10, "17": 10,
    }
    for level, expected in cases.items():
        assert level_to_score(level) == expected, level


def test_level_plus_one_on_base():
    """带 `+` 的定数在原等级基础上 +1（封顶 10）；类型不影响分值。"""
    assert level_to_score("11+") == 6
    assert level_to_score("12+") == 7
    assert level_to_score("13+") == 8
    assert level_to_score("14+") == 9
    assert level_to_score("15+") == 10
    # 类型不再影响分值（13/14 档统一 7/8）
    for t in ("Hard", "Chaos", "Glitch"):
        assert level_to_score("13", t) == 7
        assert level_to_score("14", t) == 8
        assert level_to_score("15", t) == 9
    assert level_to_score("15+", "Glitch") == 10


def test_level_invalid():
    with pytest.raises(ValueError):
        level_to_score("")
    with pytest.raises(ValueError):
        level_to_score("abc")


# ---------------------------------------------------------------- 歌曲库校验


def test_parse_valid_library():
    songs = make_songs(50)
    assert len(songs) == 50
    assert songs[0].diff_score == 6          # Chaos 12 -> 6 分（10 分制）
    assert songs[0].difficulty_label == "Chaos 12"


def test_parse_errors_carry_index_and_reason():
    with pytest.raises(ValueError, match="songs"):
        parse_song_library({})                     # 缺 songs 键
    with pytest.raises(ValueError, match="非空数组"):
        parse_song_library({"songs": []})          # 空数组
    with pytest.raises(ValueError, match="第 2 首歌曲缺少 name"):
        parse_song_library({"songs": [
            {"name": "A", "type": "Chaos", "level": "12"},
            {"type": "Chaos", "level": "12"},
        ]})
    with pytest.raises(ValueError, match="type 无效"):
        parse_song_library({"songs": [
            {"name": "A", "type": "Pop", "level": "12"},
        ]})
    with pytest.raises(ValueError, match="level 无效"):
        parse_song_library({"songs": [
            {"name": "A", "type": "Chaos", "level": "abc"},
        ]})
    with pytest.raises(ValueError, match="name 重复"):
        parse_song_library({"songs": [
            {"name": "A", "type": "Chaos", "level": "12"},
            {"name": "A", "type": "Hard", "level": "13"},
        ]})


# ---------------------------------------------------------------- 23→21 流水线


def test_generate_requires_25_songs():
    with pytest.raises(ValueError, match="至少需要 25 首"):
        generate_tasks_from_songs(make_songs(24), seed=1)


def test_generate_pipeline_shape():
    cells = generate_tasks_from_songs(make_songs(50), seed=42)
    assert len(cells) == 21
    assert {c["id"] for c in cells} == set(range(21))
    assert len({c["song_name"] for c in cells}) == 21   # 歌名不重复
    assert all(c["song_name"] for c in cells)
    # L1 固定 +10 与固定任务名
    l1 = next(c for c in cells if c["id"] == 0)
    assert l1["task_bonus"] == 10
    assert l1["task_name"] == "L1源头 (固定+10)"


def test_generate_same_seed_reproducible():
    a = generate_tasks_from_songs(make_songs(50), seed=7)
    b = generate_tasks_from_songs(make_songs(50), seed=7)
    assert a == b


def test_generate_different_seed_differs():
    a = generate_tasks_from_songs(make_songs(50), seed=1)
    b = generate_tasks_from_songs(make_songs(50), seed=2)
    assert a != b


def test_generate_capacity_per_region():
    """每区域任务数 ≤ 容量且总和 21（top≤1 / l2≤2 / mid≤7 / shallow≤5 / energy≤6）。"""
    for seed in range(1, 6):
        cells = generate_tasks_from_songs(make_songs(50), seed=seed)
        ids = [c["id"] for c in cells]
        assert sum(1 for i in ids if i == 0) <= 1
        assert sum(1 for i in ids if 1 <= i <= 2) <= 2
        assert sum(1 for i in ids if 3 <= i <= 9) <= 7
        assert sum(1 for i in ids if 10 <= i <= 14) <= 5
        assert sum(1 for i in ids if 15 <= i <= 20) <= 6
        assert len(ids) == 21


def _mixed_songs(count: int = 50) -> list[Song]:
    """混合难度歌曲库（10 分制 3~10 全覆盖，贴近真实导入）。"""
    levels = ["8", "10", "11", "12", "13", "14", "15", "15+", "16"]
    types = ["Hard", "Chaos", "Glitch"]
    return parse_song_library({"songs": [
        {"name": f"S{i}", "type": types[i % 3], "level": levels[i % len(levels)]}
        for i in range(count)
    ]})


def test_mid_region_high_intensity():
    """烈度设计（固定中腹高分模板）：mid 区（L3+L4）承接全盘最高分任务。"""
    for seed in range(1, 21):
        cells = generate_tasks_from_songs(_mixed_songs(), seed=seed)
        def t(c):
            return c["diff_score"] + c["task_bonus"]
        mid_max = max(t(c) for c in cells if 3 <= c["id"] <= 9)
        other_max = max(t(c) for c in cells
                        if (1 <= c["id"] <= 2 or 10 <= c["id"] <= 20))
        assert mid_max >= other_max, seed        # 高分任务先落 mid
        # L1 固定 +10
        l1 = next(c for c in cells if c["id"] == 0)
        assert l1["task_bonus"] == 10
        assert l1["task_name"] == "L1源头 (固定+10)"
