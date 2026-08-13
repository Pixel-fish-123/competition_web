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


# ---------------------------------------------------------------- level 映射


def test_level_to_score_boundaries():
    cases = {
        "15+": 15, "16": 15, "16+": 15, "17": 15, "17+": 15,
        "15": 10,
        "14": 8, "14+": 8,
        "13": 6, "13+": 6,
        "12": 5, "12+": 5,
        "11": 4, "11+": 4,
        "9": 3, "9+": 3, "10": 3, "10+": 3,
        "8": 2, "7": 2, "1": 2,
    }
    for level, expected in cases.items():
        assert level_to_score(level) == expected, level


def test_level_type_prefix_ignored():
    assert level_to_score("Chaos 15+") == 15
    assert level_to_score("Hard 14") == 8
    assert level_to_score("Glitch 12+") == 5


def test_level_invalid():
    with pytest.raises(ValueError):
        level_to_score("")
    with pytest.raises(ValueError):
        level_to_score("abc")


# ---------------------------------------------------------------- 歌曲库校验


def test_parse_valid_library():
    songs = make_songs(50)
    assert len(songs) == 50
    assert songs[0].diff_score == 5
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


def test_generate_requires_23_songs():
    with pytest.raises(ValueError, match="至少需要 23 首"):
        generate_tasks_from_songs(make_songs(20), seed=1)


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
    """每区域任务数 ≤ 容量且总和 21（top≤1 / mid≤9 / shallow≤5 / energy≤6）。"""
    for seed in range(1, 6):
        cells = generate_tasks_from_songs(make_songs(50), seed=seed)
        ids = [c["id"] for c in cells]
        assert sum(1 for i in ids if i == 0) <= 1
        assert sum(1 for i in ids if 1 <= i <= 9) <= 9
        assert sum(1 for i in ids if 10 <= i <= 14) <= 5
        assert sum(1 for i in ids if 15 <= i <= 20) <= 6
        assert len(ids) == 21
