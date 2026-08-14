from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Cell:
    id: int
    layer: int
    is_energy: bool
    owner: str | None = None
    activated: bool = False
    diff_score: int = 0
    difficulty_label: str = ""
    task_name: str = ""
    task_bonus: int = 0
    song_name: str = ""
    song_type: str = ""
    song_level: str = ""
    total_score: int = 0
    energy_bonus: int = 0
    from_encirclement: bool = False   # 由包围机制获得的格子（前端虚线显示，功能与普通格相同）
    neighbors: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "layer": self.layer,
            "is_energy": self.is_energy,
            "owner": self.owner,
            "activated": self.activated,
            "diff_score": self.diff_score,
            "difficulty_label": self.difficulty_label,
            "task_name": self.task_name,
            "task_bonus": self.task_bonus,
            "song_name": self.song_name,
            "song_type": self.song_type,
            "song_level": self.song_level,
            "total_score": self.total_score,
            "energy_bonus": self.energy_bonus,
            "from_encirclement": self.from_encirclement,
            "neighbors": list(self.neighbors),
        }


def _layer_index_to_id(layer: int, index: int) -> int:
    return layer * (layer - 1) // 2 + index


def _get_layer_and_index(cell_id: int) -> tuple[int, int]:
    for layer in range(1, 7):
        start = layer * (layer - 1) // 2
        end = (layer + 1) * layer // 2
        if start <= cell_id < end:
            return layer, cell_id - start
    return 0, 0


def _compute_neighbors(cell_id: int) -> list[int]:
    if cell_id >= 21:
        i = cell_id - 21
        return [15 + i]

    layer, idx = _get_layer_and_index(cell_id)
    layer_size = layer
    neighbors: list[int] = []

    if layer < 6:
        neighbors.append(_layer_index_to_id(layer + 1, idx))
        neighbors.append(_layer_index_to_id(layer + 1, idx + 1))

    if idx > 0:
        neighbors.append(cell_id - 1)
    if idx < layer_size - 1:
        neighbors.append(cell_id + 1)

    if layer > 1:
        prev_layer_size = layer - 1
        if idx < prev_layer_size:
            neighbors.append(_layer_index_to_id(layer - 1, idx))
        if idx > 0:
            neighbors.append(_layer_index_to_id(layer - 1, idx - 1))

    if layer == 6:
        neighbors.append(21 + idx)

    return neighbors


def _to_int(value: Any, field: str, cell_id: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"格子 {cell_id} 的 {field} 必须是整数：{value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"格子 {cell_id} 的 {field} 必须是整数：{value!r}")
    return int(value)


def build_cells(cells_data: list[dict] | None = None) -> list[Cell]:
    cells: list[Cell] = []
    data_map: dict[int, dict] = {}
    for i, d in enumerate(cells_data or []):
        if not isinstance(d, dict):
            raise ValueError(f"第 {i + 1} 条自定义格子数据格式错误：应为对象")
        cid = d.get("id")
        if isinstance(cid, bool) or not isinstance(cid, int) or cid < 0 or cid > 20:
            raise ValueError(f"第 {i + 1} 条自定义格子数据 id 无效：{cid!r}（应为 0-20 的整数）")
        data_map[cid] = d

    for cell_id in range(27):
        if cell_id >= 21:
            cells.append(Cell(
                id=cell_id, layer=7, is_energy=True,
                neighbors=_compute_neighbors(cell_id),
            ))
        else:
            layer, _ = _get_layer_and_index(cell_id)
            d = data_map.get(cell_id, {})
            diff = _to_int(d.get("diff_score", 0), "diff_score", cell_id)
            bonus = _to_int(d.get("task_bonus", 0), "task_bonus", cell_id)
            cells.append(Cell(
                id=cell_id, layer=layer, is_energy=False,
                diff_score=diff,
                difficulty_label=str(d.get("difficulty_label", "")),
                task_name=str(d.get("task_name", "")),
                task_bonus=bonus,
                song_name=str(d.get("song_name", "")),
                song_type=str(d.get("song_type", "")),
                song_level=str(d.get("song_level", "")),
                total_score=diff + bonus,
                neighbors=_compute_neighbors(cell_id),
            ))
    return cells


def cell_positions(width: float, height: float) -> dict[int, tuple[float, float]]:
    """Compute (x, y) center positions for rendering the triangle grid."""
    positions: dict[int, tuple[float, float]] = {}
    margin_x = width * 0.08
    margin_y = height * 0.06
    usable_w = width - 2 * margin_x
    usable_h = height - 2 * margin_y
    dx = usable_w / 6.0
    dy = usable_h / 7.0
    cx = width / 2.0

    for cell_id in range(21):
        layer, idx = _get_layer_and_index(cell_id)
        x = cx + (idx - (layer - 1) / 2.0) * dx
        y = margin_y + (layer - 1) * dy
        positions[cell_id] = (x, y)

    for i in range(6):
        x = cx + (i - 2.5) * dx
        y = margin_y + 6 * dy
        positions[21 + i] = (x, y)

    return positions
