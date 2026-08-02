"""三角占领玩法插件（todo 13）：demo 赛时控制器（triangle_occupy）的适配层。

``controller/`` 子包从 demo 原样复制（规则逻辑零改动，见 controller/__init__.py），
本文件只做插件契约适配（Metis C4 无全局歌曲库 / E9 会话时钟 / E11 输入校验）。

会话状态设计：
- state dict 只保存可 JSON 序列化的字段（match_id / controller_state /
  elapsed_minutes / sides / cells_data / started_at），因此 POST /session
  响应（routes.py 原样返回 state）可以正常序列化，不会因活实例而 500。
- 活的 :class:`GameController` 实例保存在模块级 ``_CONTROLLERS``
  （``id(state)`` -> 实例），与内存会话存储中的 state 对象一一对应；
  session 生命周期内跨 submit_result 保持同一实例，棋盘进度不丢失。
- todo 14（GameSession DB 持久化）将把 cells_data + controller_state +
  elapsed_minutes 入库；重启后无活实例，走 :meth:`_restore_controller`
  重建并校准时钟（Metis E9：``game._start_ts = now - elapsed_minutes * 60``）。

权限模型（用户 2026-08-02 最终确认）：路由层已限定仅 admin/referee 可
提交操作（require_referee），插件只校验 participant_id 确为本局两名选手
之一。选手对棋盘只读。
"""

from __future__ import annotations

import time
from typing import Any

from app.plugins.base import GameplayPlugin
from app.plugins.triangle_occupy.controller import song_lib
from app.plugins.triangle_occupy.controller.game import GameController

# id(state) -> 活的 GameController 实例（仅内存持有，不随 state 序列化）。
_CONTROLLERS: dict[int, GameController] = {}

VALID_ACTIONS = frozenset({"occupy", "cancel", "reoccupy", "set_time"})
VALID_TEAMS = frozenset({"defender", "attacker"})


class TriangleOccupyPlugin(GameplayPlugin):
    name = "triangle_occupy"
    version = "1.0.0"

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _resolve_sides(self, config: dict) -> dict:
        """解析 config["sides"]（participant_id -> defender/attacker）。

        缺失/为空时按 plan 默认：participant_a -> defender、
        participant_b -> attacker。
        JSON 对象键经过 HTTP 后是字符串（"101"），而路由层的
        participant_id 是 int；这里把纯数字字符串键规范化为 int，
        保证两边一致。
        """
        sides = config.get("sides")
        if not isinstance(sides, dict) or not sides:
            return {"participant_a": "defender", "participant_b": "attacker"}
        normalized: dict[Any, str] = {}
        for pid, team in sides.items():
            if team not in VALID_TEAMS:
                raise ValueError("阵营映射非法：仅支持 defender/attacker")
            key: Any = pid
            if isinstance(pid, str):
                try:
                    key = int(pid)
                except ValueError:
                    key = pid
            normalized[key] = team
        return normalized

    def _build_game(self, config: dict) -> tuple[GameController, list[dict]]:
        """从 config 构造初始化的 GameController（Metis C4：歌曲库由 config 携带）。

        返回 (game, cells_data)：cells_data 为可 JSON 序列化的 21 格任务数据，
        随 state 持久化（todo 14 DB 恢复时重建棋盘用）。
        """
        song_lib_data = config.get("song_lib")
        if song_lib_data is None:
            raise ValueError("歌曲库缺失或格式错误")
        try:
            songs = song_lib.parse_song_library(song_lib_data)
        except ValueError as exc:
            # 结构非法统一报"缺失或格式错误"；<23 首的 ValueError 由
            # generate_tasks_from_songs 抛出并原样透传（"歌曲库至少需要 23 首"）。
            raise ValueError("歌曲库缺失或格式错误") from exc

        seed = config.get("seed")
        if seed is not None and not isinstance(seed, (int, float, str, bytes)):
            raise ValueError("seed 必须是数字或字符串")
        cells = song_lib.generate_tasks_from_songs(songs, seed=seed)

        game = GameController()
        game.init(cells)
        try:
            limit = float(config.get("time_limit_minutes", 25.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("time_limit_minutes 必须是数字") from exc
        if limit <= 0:
            raise ValueError("time_limit_minutes 必须为正数")
        game.time_limit_minutes = limit
        return game, cells

    def _restore_controller(self, state: dict) -> GameController:
        """从序列化 state 重建控制器（todo 14 DB 恢复桥；Metis E9 时钟修复）。"""
        game = GameController()
        cells = state.get("cells_data")
        if cells is None:
            raise ValueError("会话状态缺失棋盘数据")
        game.init(cells)
        game._start_ts = time.time() - state.get("elapsed_minutes", 0.0) * 60
        cs = state.get("controller_state") or {}
        if isinstance(cs.get("time_limit"), (int, float)):
            game.time_limit_minutes = float(cs["time_limit"])
        return game

    def _get_controller(self, state: dict) -> GameController:
        """取当前会话的活实例；缺失则重建并登记（覆盖重启/DB 恢复场景）。"""
        controller = _CONTROLLERS.get(id(state))
        if controller is None:
            controller = self._restore_controller(state)
            _CONTROLLERS[id(state)] = controller
        return controller

    def _keep_controller(self, state: dict, controller: GameController) -> None:
        _CONTROLLERS[id(state)] = controller

    def _drop_controller(self, state: dict) -> None:
        _CONTROLLERS.pop(id(state), None)

    # ------------------------------------------------------------------
    # GameplayPlugin 契约
    # ------------------------------------------------------------------

    def create_session(self, match_id: int, config: dict) -> dict:
        config = config or {}
        game, cells = self._build_game(config)
        state = {
            "match_id": match_id,
            "controller_state": game.to_state_dict(),
            "elapsed_minutes": game.elapsed(),
            "sides": self._resolve_sides(config),
            "started_at": time.time(),
            "cells_data": cells,
        }
        self._keep_controller(state, game)
        return state

    def get_state(self, session_id: int, state: dict) -> dict:
        """公开视图：controller_state 合并 elapsed，裁剪私有字段。"""
        controller = self._get_controller(state)
        controller_state = controller.to_state_dict()
        return {
            "match_id": state.get("match_id"),
            "controller_state": controller_state,
            "elapsed_minutes": round(controller_state["elapsed"], 2),
            "sides": dict(state.get("sides", {})),
            "game_over": controller_state["game_over"],
            "winner": controller_state["winner"],
        }

    def validate_result(
        self, session_id: int, state: dict, participant_id: int, payload: dict
    ) -> bool:
        """结构性校验（Metis E7：只做值域，不校验得分真实性）。"""
        payload = payload or {}
        if payload.get("action") not in VALID_ACTIONS:
            return False
        if participant_id not in state.get("sides", {}):
            return False
        action = payload["action"]
        if action in ("occupy", "cancel", "reoccupy"):
            cell_id = payload.get("cell_id")
            if not isinstance(cell_id, int) or isinstance(cell_id, bool):
                return False
            if not 0 <= cell_id <= 20:
                return False
        elif action == "set_time":
            minutes = payload.get("minutes")
            if not isinstance(minutes, (int, float)) or isinstance(minutes, bool):
                return False
            if minutes < 0:
                return False
        return True

    def submit_result(
        self, session_id: int, state: dict, participant_id: int, payload: dict
    ) -> dict:
        payload = payload or {}
        sides = state.get("sides", {})
        if participant_id not in sides:
            raise ValueError("非本局参与者")

        action = payload.get("action")
        if action not in VALID_ACTIONS:
            raise ValueError("非法操作")

        controller = self._get_controller(state)
        result: dict[str, Any] = {"action": action}
        cell_id: int | None = None

        if action in ("occupy", "cancel", "reoccupy"):
            cell_id = payload.get("cell_id")
            if not isinstance(cell_id, int) or isinstance(cell_id, bool):
                raise ValueError("缺少格子 ID")
            if not 0 <= cell_id <= 20:
                raise ValueError("非法格子 ID")
            result["cell_id"] = cell_id

        if action == "occupy":
            team = sides[participant_id]
            score = payload.get("score")
            tp = payload.get("tp")
            for name, val in (("score", score), ("tp", tp)):
                if val is not None and (
                    not isinstance(val, (int, float)) or isinstance(val, bool)
                ):
                    raise ValueError(f"{name} 必须是数字")
            if cell_id == 0 and score is None:
                raise ValueError("L1 占领需要 score 参数")
            ok = controller.occupy(cell_id, team, score, tp)
            result["ok"] = ok
            if cell_id == 0:
                # demo 的 _occupy_l1 对 L1 恒返回 True；挑战失败需看 owner 是否易主。
                result["challenge_failed"] = controller.cells[0].owner != team
        elif action == "cancel":
            result["ok"] = controller.cancel_occupy(cell_id)
        elif action == "reoccupy":
            result["ok"] = controller.reoccupy(cell_id)
        elif action == "set_time":
            minutes = payload.get("minutes")
            if not isinstance(minutes, (int, float)) or isinstance(minutes, bool):
                raise ValueError("set_time 需要 minutes")
            if minutes < 0:
                raise ValueError("time_limit 不能为负")
            controller.time_limit_minutes = float(minutes)
            result["ok"] = True
            result["minutes"] = float(minutes)

        new_state = dict(state)
        new_state["controller_state"] = controller.to_state_dict()
        new_state["elapsed_minutes"] = controller.elapsed()
        new_state["last_action"] = result
        self._keep_controller(new_state, controller)
        return new_state

    def end_session(self, session_id: int, state: dict) -> dict:
        controller = self._get_controller(state)
        controller.end_game()
        self._drop_controller(state)

        # 阵营 -> 选手 反向映射（平局时无胜者映射）。
        reverse: dict[str, Any] = {}
        for pid, team in state.get("sides", {}).items():
            reverse.setdefault(team, pid)

        if controller.winner == "draw":
            return {
                "winner": None,
                "is_draw": True,
                "score_a": controller.defender_score,
                "score_b": controller.attacker_score,
            }
        return {
            "winner": reverse.get(controller.winner),
            "is_draw": False,
            "score_a": controller.defender_score,
            "score_b": controller.attacker_score,
        }


plugin = TriangleOccupyPlugin()
