"""棋盘结构测试：27 格 / 层级 / 邻接 / 自定义格构建。

运行：cd demo && python -m pytest tests/test_board.py -q
"""

from controller.board import (
    Cell,
    _compute_neighbors,
    _get_layer_and_index,
    _layer_index_to_id,
    build_cells,
)


def test_total_cells_and_energy():
    cells = build_cells()
    assert len(cells) == 27
    energy = [c for c in cells if c.is_energy]
    assert len(energy) == 6
    assert [c.id for c in energy] == [21, 22, 23, 24, 25, 26]


def test_layer_mapping():
    cases = {0: (1, 0), 1: (2, 0), 2: (2, 1), 3: (3, 0), 5: (3, 2),
             6: (4, 0), 9: (4, 3), 10: (5, 0), 14: (5, 4),
             15: (6, 0), 20: (6, 5)}
    for cid, (layer, idx) in cases.items():
        assert _get_layer_and_index(cid) == (layer, idx)
    assert _layer_index_to_id(1, 0) == 0
    assert _layer_index_to_id(6, 5) == 20


def test_l1_neighbors():
    assert sorted(_compute_neighbors(0)) == [1, 2]


def test_interior_cell_has_six_neighbors():
    # 中腹格（L3 中间）应有 6 个邻接：2 父 + 2 子 + 2 兄弟。
    assert sorted(_compute_neighbors(4)) == [1, 2, 3, 5, 7, 8]


def test_energy_cells_link_to_l6():
    for i in range(6):
        assert _compute_neighbors(21 + i) == [15 + i]


def test_edge_cells_have_fewer_neighbors():
    # 地图边界 = 邻接数 < 6；L1 只有 2 个邻接。
    assert len(_compute_neighbors(0)) == 2
    assert len(_compute_neighbors(1)) == 4       # 左上边
    assert len(_compute_neighbors(20)) == 3      # 右下角（L6）
    assert len(_compute_neighbors(15)) == 3      # 左下角（L6，含能源）


def test_build_cells_with_custom_data():
    data = [
        {"id": 3, "diff_score": 15, "task_bonus": 10,
         "difficulty_label": "Glitch 15+", "task_name": "达成MM",
         "song_name": "Vindication", "song_type": "Glitch", "song_level": "15+"},
    ]
    cells = build_cells(data)
    cell = cells[3]
    assert cell.diff_score == 15
    assert cell.task_bonus == 10
    assert cell.total_score == 25
    assert cell.song_name == "Vindication"
    assert cell.difficulty_label == "Glitch 15+"
    # 未提供的格子用默认值。
    assert cells[0].diff_score == 0
    assert cells[0].total_score == 0
    # 能源格不受自定义数据影响。
    assert cells[21].is_energy and cells[21].diff_score == 0


def test_build_cells_invalid_data():
    import pytest
    with pytest.raises(ValueError):
        build_cells([{"id": 99, "diff_score": 5}])
    with pytest.raises(ValueError):
        build_cells([{"id": 3, "diff_score": "x"}])


def test_cell_to_dict_contains_metadata():
    cells = build_cells([
        {"id": 0, "diff_score": 15, "song_name": "S1", "difficulty_label": "Chaos 15+"}
    ])
    d = cells[0].to_dict()
    assert d["id"] == 0
    assert d["song_name"] == "S1"
    assert d["neighbors"] == [1, 2]
