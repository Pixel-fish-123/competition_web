from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .board import Cell, build_cells

TIME_LIMIT_MINUTES = 25.0
MAX_PLAYABLE_CELL_ID = 20


@dataclass
class GameEvent:
    time: str
    text: str
    etype: str = "occupy"

    def to_dict(self) -> dict:
        return {"time": self.time, "text": self.text, "type": self.etype}


@dataclass
class GameController:
    cells: list[Cell] = field(default_factory=list)
    defender_score: float = 0.0
    attacker_score: float = 0.0
    l1_high_score: int | None = None
    l1_high_tp: float | None = None
    l1_high_team: str | None = None
    game_over: bool = False
    winner: str | None = None
    win_type: str | None = None
    elapsed_minutes: float = 0.0
    events: list[GameEvent] = field(default_factory=list)
    started: bool = False
    _action_counter: int = 0
    _start_ts: float = 0.0
    time_limit_minutes: float = TIME_LIMIT_MINUTES

    def init(self, cells_data: list[dict] | None = None) -> None:
        self.cells = build_cells(cells_data)
        self.defender_score = 0.0
        self.attacker_score = 0.0
        self.l1_high_score = None
        self.l1_high_tp = None
        self.l1_high_team = None
        self.game_over = False
        self.winner = None
        self.win_type = None
        self.elapsed_minutes = 0.0
        self.events = []
        self.started = True
        self._action_counter = 0
        self._start_ts = time.time()
        self._log("游戏初始化完成", "system")

    def elapsed(self) -> float:
        if not self.started or self.game_over:
            return self.elapsed_minutes
        return (time.time() - self._start_ts) / 60.0

    def _sync_elapsed(self) -> None:
        if self.started and not self.game_over:
            self.elapsed_minutes = (time.time() - self._start_ts) / 60.0

    def _check_timeout(self) -> bool:
        self._sync_elapsed()
        if self.elapsed_minutes >= self.time_limit_minutes and not self.game_over:
            self.end_game()
            return True
        return False

    def _log(self, text: str, etype: str = "occupy") -> None:
        self._sync_elapsed()  # ensure elapsed_minutes is current (frozen when game_over)
        total_sec = int(self.elapsed_minutes * 60)
        mm = total_sec // 60
        ss = total_sec % 60
        self.events.insert(0, GameEvent(f"{mm:02d}:{ss:02d}", text, etype))
        if len(self.events) > 200:
            self.events = self.events[:200]

    def _ensure_started(self) -> bool:
        if not self.started:
            self._log("游戏未初始化", "system")
            return False
        if self.game_over:
            self._log("游戏已结束", "system")
            return False
        if self._check_timeout():
            return False
        return True

    def occupy(self, cell_id: int, team: str, score: int | None = None,
               tp: float | None = None) -> bool:
        if not self._ensure_started():
            return False
        if cell_id < 0 or cell_id > MAX_PLAYABLE_CELL_ID:
            self._log(f"非法格子 ID: {cell_id}", "system")
            return False
        if team not in ("defender", "attacker"):
            self._log(f"非法阵营: {team}", "system")
            return False

        cell = self.cells[cell_id]

        if cell_id == 0:
            return self._occupy_l1(team, score, tp)

        if cell.owner == team:
            self._log(f"{self._team_cn(team)} 已占领 L{cell.layer}格{self._idx_in_layer(cell_id)}，忽略", "system")
            return False

        if cell.owner is not None:
            self._log(f"L{cell.layer}格{self._idx_in_layer(cell_id)} 已被占领，忽略", "system")
            return False

        cell.owner = team
        cell.activated = False
        self._run_update_chain()
        name = cell.song_name or cell.difficulty_label or f"CHAOS {cell.diff_score}"
        annotations = self._occupation_annotations(cell, team)
        self._log(
            f"{self._team_cn(team)} 占领了L{cell.layer}第{self._idx_in_layer(cell_id) + 1}个格子 的{name} {cell.task_name} ({cell.total_score}) {annotations}",
            "occupy",
        )
        return True

    def _occupy_l1(self, team: str, score: int | None, tp: float | None) -> bool:
        cell = self.cells[0]
        if score is None:
            self._log("L1 占领需要 score 参数", "system")
            return False

        accepted = (self.l1_high_score is None
                or score > self.l1_high_score
                or (score == self.l1_high_score
                    and tp is not None
                    and self.l1_high_tp is not None
                    and tp > self.l1_high_tp))
        if accepted:
            self.l1_high_score = score
            self.l1_high_tp = tp if tp is not None else self.l1_high_tp
            self.l1_high_team = team
            cell.owner = team
            name = cell.song_name or cell.difficulty_label or f"CHAOS {cell.diff_score}"
            self._run_update_chain()
            self._log(
                f"{self._team_cn(team)} 占领了L1源头 的{name} {cell.task_name} {self._score_tp_str(score, tp)} [占领L1]",
                "l1",
            )
        if not accepted:
            self._log(
                f"{self._team_cn(team)} L1挑战失败 {self._score_tp_str(score, tp)} <= {self._score_tp_str(self.l1_high_score, self.l1_high_tp)}",
                "l1",
            )
        return True

    @staticmethod
    def _score_tp_str(score: int | None, tp: float | None) -> str:
        if tp is not None:
            return f"(score={score}, tp={tp})"
        return f"(score={score})"

    def cancel_occupy(self, cell_id: int) -> bool:
        if not self._ensure_started():
            return False
        if cell_id < 0 or cell_id > MAX_PLAYABLE_CELL_ID:
            return False
        cell = self.cells[cell_id]
        if cell.owner is None:
            return False
        prev = self._team_cn(cell.owner)
        cell.owner = None
        cell.activated = False
        if cell_id == 0:
            self.l1_high_score = None
            self.l1_high_tp = None
            self.l1_high_team = None
        name = cell.song_name or cell.difficulty_label or f"CHAOS {cell.diff_score}"
        self._log(
            f"取消了L{cell.layer}第{self._idx_in_layer(cell_id) + 1}个格子 的{name} 的{prev}占领",
            "system",
        )
        self._run_update_chain()
        return True

    def end_game(self) -> bool:
        if not self.started:
            return False
        if self.game_over:
            return False
        self._sync_elapsed()
        self.game_over = True
        self.win_type = "timeout"
        if self.defender_score > self.attacker_score:
            self.winner = "defender"
        elif self.attacker_score > self.defender_score:
            self.winner = "attacker"
        else:
            self.winner = "draw"
        self._log(
            f"游戏结束 - {self._team_cn(self.winner) if self.winner != 'draw' else '平局'} "
            f"(防{int(self.defender_score)} : 攻{int(self.attacker_score)})",
            "system",
        )
        return True

    def _run_update_chain(self) -> None:
        self.update_activation()
        self.check_encirclement()
        self.recalc_scores()
        self.check_top_victory()
        if not self.game_over:
            self._check_timeout()

    def update_activation(self) -> None:
        for c in self.cells:
            if not c.is_energy:
                c.activated = False

        for e in self.cells:
            if not e.is_energy:
                continue
            for nid in e.neighbors:
                n = self.cells[nid]
                if n.owner == "attacker" and not n.activated:
                    queue = deque([nid])
                    n.activated = True
                    while queue:
                        cur = self.cells[queue.popleft()]
                        for nn in cur.neighbors:
                            nb = self.cells[nn]
                            if (nb.owner == "attacker"
                                    and not nb.is_energy
                                    and not nb.activated):
                                nb.activated = True
                                queue.append(nn)

    def check_encirclement(self) -> None:
        """新包围系统：非防守方连通区域被「防守方格 / 地图边界」完全围住时，整片变为防守方地块。

        - 连通区域 = 相邻的「未占领 + 攻击方占领」格；排除能源格（21–26）。
          **L1（id 0）可属于连通区域**，但包围转换时 L1 本身不被占领（豁免）。
        - 封闭判定：区域内每格的每个邻接格，要么属于本区域，要么是防守方占领；
          邻接槽位缺失（=地图边界）视为封闭边；邻接攻击方 / 未占领 / 能源格 → 不成立。
        - 每次占领变化后判定，可多次触发；单次判定内迭代到不动点（转换出的防守方格
          可继续围住相邻区域）。
        """
        converted: list[int] = []
        while True:
            # 1) 由当前盘面找出全部非防守方连通区域（含 L1，排除能源格）
            region_of: dict[int, int] = {}
            regions: list[set[int]] = []
            for start in range(0, 22):  # 0..20 任务格（含 L1）；21–26 能源格不参与
                if start in region_of:
                    continue
                start_cell = self.cells[start]
                if start_cell.is_energy or start_cell.owner == "defender":
                    continue
                region: set[int] = set()
                queue = deque([start])
                region.add(start)
                region_of[start] = len(regions)
                while queue:
                    cur = self.cells[queue.popleft()]
                    for nid in cur.neighbors:
                        if (nid in region_of or nid >= 21
                                or self.cells[nid].owner == "defender"):
                            continue
                        region.add(nid)
                        region_of[nid] = len(regions)
                        queue.append(nid)
                regions.append(region)

            # 2) 转换全部被完全围住的区域（一次遍历；L1-only 区域豁免跳过），
            #    然后迭代到不动点（转换出的防守方格可继续围住相邻区域）。
            newly: list[int] = []
            for region in regions:
                if not self._region_enclosed(region):
                    continue
                targets = [i for i in region if i != 0]  # L1 豁免：不转换
                if not targets:
                    continue  # 纯 L1 区域：无可转换格，跳过不中断
                for i in targets:
                    cell = self.cells[i]
                    if cell.owner == "attacker":
                        cell.activated = False
                    cell.owner = "defender"
                newly.extend(targets)
            if not newly:
                break
            converted.extend(newly)
            if len(converted) >= 21:
                break

        if converted:
            self._log(
                f"包围成立！{len(converted)}格变为防守方地块",
                "encircle",
            )

    def _region_enclosed(self, region: set[int]) -> bool:
        """区域被完全围住 ⟺ 区域内每格的每个邻接格都在区域内或是防守方占领。

        邻接槽位缺失（`neighbors` 中不存在）= 地图边界 = 封闭边，无需检查。
        邻接格为攻击方 / 未占领 / 能源格 → 非防守方，判定失败。
        """
        for i in region:
            for nid in self.cells[i].neighbors:
                if nid in region:
                    continue
                if self.cells[nid].owner != "defender":
                    return False
        return True

    def recalc_scores(self) -> None:
        def_score = 0
        atk_score = 0

        for cell in self.cells:
            if not cell.is_energy:
                cell.energy_bonus = 0

        for cell in self.cells:
            if cell.is_energy:
                continue
            if cell.owner == "defender":
                def_score += cell.total_score
            elif cell.owner == "attacker" and cell.id == 0:
                atk_score += cell.total_score

        visited: set[int] = set()
        for cell in self.cells:
            if cell.is_energy:
                continue
            if (cell.owner == "attacker"
                    and cell.activated
                    and cell.id != 0
                    and cell.id not in visited):
                block = self._bfs_attacker_block(cell.id)
                visited |= block
                energy_count = self._count_energy_contacts(block)
                bonus = min(energy_count - 1, 2) if energy_count >= 1 else 0
                for bid in block:
                    self.cells[bid].energy_bonus = bonus
                    atk_score += self.cells[bid].total_score + bonus

        self.defender_score = float(def_score)
        self.attacker_score = float(atk_score)

    def _bfs_attacker_block(self, start: int) -> set[int]:
        block: set[int] = set()
        queue = deque([start])
        block.add(start)
        while queue:
            cur = self.cells[queue.popleft()]
            for nid in cur.neighbors:
                nb = self.cells[nid]
                if (nid not in block
                        and nid != 0  # L1 已在 recalc_scores 单独计分，避免重复
                        and nb.owner == "attacker"
                        and nb.activated
                        and not nb.is_energy):
                    block.add(nid)
                    queue.append(nid)
        return block

    def _count_energy_contacts(self, block: set[int]) -> int:
        energy_ids: set[int] = set()
        for bid in block:
            for nid in self.cells[bid].neighbors:
                if self.cells[nid].is_energy:
                    energy_ids.add(nid)
        return len(energy_ids)

    def _occupation_annotations(self, cell: Cell, team: str) -> str:
        parts = []
        if team == "defender":
            parts.append("[防守]")
        elif team == "attacker":
            if cell.activated:
                parts.append("[已激活]")
                block = self._bfs_attacker_block(cell.id)
                energy_n = self._count_energy_contacts(block)
                if energy_n >= 2:
                    parts.append(f"[能源+{energy_n}]")
            else:
                parts.append("[未激活]")
        return "".join(parts)

    def check_top_victory(self) -> None:
        if self.game_over:
            return
        l1 = self.cells[0]
        if l1.owner == "attacker" and l1.activated:
            self.game_over = True
            self.winner = "attacker"
            self.win_type = "top"
            self._log(
                f"攻击方顶端直胜！直接获胜",
                "victory",
            )

    def _idx_in_layer(self, cell_id: int) -> int:
        layer = self.cells[cell_id].layer
        start = layer * (layer - 1) // 2
        return cell_id - start

    def _team_cn(self, team: str | None) -> str:
        if team == "defender":
            return "防守方"
        if team == "attacker":
            return "攻击方"
        if team == "draw":
            return "平局"
        return "未知"

    def get_scores(self) -> dict:
        return {"defender": self.defender_score, "attacker": self.attacker_score}

    def get_board(self) -> list[dict]:
        return [c.to_dict() for c in self.cells]

    def get_l1_status(self) -> dict:
        return {
            "holder": self.l1_high_team,
            "high_score": self.l1_high_score,
            "high_tp": self.l1_high_tp,
        }

    def export_tasks(self) -> list[dict]:
        return [
            {
                "id": c.id,
                "diff_score": c.diff_score,
                "difficulty_label": c.difficulty_label,
                "task_name": c.task_name,
                "task_bonus": c.task_bonus,
                "total_score": c.total_score,
            }
            for c in self.cells[:21]
        ]

    def to_state_dict(self) -> dict[str, Any]:
        return {
            "board": self.get_board(),
            "scores": self.get_scores(),
            "l1": self.get_l1_status(),
            "elapsed": round(self.elapsed(), 2),
            "time_limit": self.time_limit_minutes,
            "events": [e.to_dict() for e in self.events[:50]],
            "game_over": self.game_over,
            "winner": self.winner,
            "win_type": self.win_type,
            "started": self.started,
        }
