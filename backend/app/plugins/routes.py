"""玩法插件 HTTP 路由（todo 12）：为每个已注册插件自动挂载
``/api/gameplay/<name>/*`` 路由。

路由（每个插件一套）:
- POST /session                   创建对局会话（admin/referee）
- GET  /session/{id}/state        查询会话状态（任意登录用户，选手只读）
- POST /session/{id}/action       提交选手/裁判操作（admin/referee）
- POST /session/{id}/end          结束对局（admin/referee）

权限（用户 2026-08-02 最终确认）：对局中仅 referee/admin 可操作棋盘
（创建会话/提交操作/结束对局），选手只读（仅可查询会话状态）。

会话存储：GameSession DB 桥已实现（_load_db_session 回退装载 +
_persist_session 回写），_sessions 仅作进程内缓存加速。

所有插件抛出的 :class:`ValueError` 统一转换为 HTTP 400（detail=str(e)）。
"""

from __future__ import annotations

import itertools
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.core.rbac import get_current_user, require_referee
from app.core.ws_manager import manager
from app.db import SessionLocal
from app.models.match import GameSession
from app.models.user import User
from app.plugins.base import GameplayPlugin
from app.plugins.registry import registry

# 会话存储（进程内缓存加速；DB 桥已实现——_load_db_session 回退装载 +
# _persist_session 回写，见下方实现）：
#   session_id -> {"plugin": GameplayPlugin, "state": dict, "match_id": int}
#   match_id 供 todo 15 的 WS 广播定位订阅频道（对局状态实时推送）。
_sessions: dict[int, dict] = {}
_session_seq = itertools.count(1)

# 已挂载路由的插件名，保证 mount_gameplay_routes 幂等（避免重复 include_router）。
_mounted_plugins: set[str] = set()

UNAUTHORIZED_DETAIL = "未登录或登录已失效"
FORBIDDEN_DETAIL = "权限不足"


class SessionCreate(BaseModel):
    match_id: int
    config: dict = {}


class ActionPayload(BaseModel):
    # participant_id = 被操作的参赛单位 id（裁判替该方操作棋盘）。
    # 注意：不是"发起人"身份 —— 操作者身份由 require_referee 强制；
    # 插件侧只把它当作 sides 映射的键（合法 side 成员校验）。
    participant_id: int
    payload: dict = {}


def _get_plugin(name: str) -> GameplayPlugin:
    plugin = registry.get(name)
    if plugin is None:
        raise HTTPException(status_code=404, detail="玩法插件不存在")
    return plugin


def _load_db_session(session_id: int) -> dict | None:
    """DB 持久化会话（/api/matches/{id}/start 路径）的回退装载。

    玩法 action/end 路由原本只认内存 ``_sessions``，而 start_match 只落库
    GameSession，导致前端对局页流程（start -> WS session_id -> action/end）
    404「对局会话不存在」。这里把 ``_sessions`` 当作缓存，内存缺失时按
    session_id 从 GameSession 表恢复（todo 14 的 DB 桥；插件侧
    _restore_controller 负责重建活控制器并校准时钟）。
    """
    with SessionLocal() as db:
        gs = db.get(GameSession, session_id)
        if gs is None:
            return None
        plugin = registry.get(gs.plugin_name)
        if plugin is None:
            raise HTTPException(status_code=404, detail="玩法插件不存在")
        state = gs.state_json or {}
        # JSON 往返后 sides 的键变成字符串（"3"/"4"），validate_result 用 int
        # participant_id 匹配；与插件 create_session 的 _resolve_sides 一致的
        # 规范化，保证 DB 恢复的会话行为与内存会话一致。
        sides = state.get("sides")
        if isinstance(sides, dict):
            state = dict(state)
            state["sides"] = {
                int(k) if isinstance(k, str) and k.isdigit() else k: v
                for k, v in sides.items()
            }
        return {
            "plugin": plugin,
            "state": state,
            "match_id": gs.match_id,
            "db": gs.id,  # 标记 DB 持久化：操作后回写 state_json
        }


def _get_session(session_id: int) -> dict:
    session = _sessions.get(session_id)
    if session is None:
        session = _load_db_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="对局会话不存在")
        _sessions[session_id] = session
    return session


def _persist_session(session: dict, state: dict, ended: bool = False) -> None:
    """DB 持久化会话操作后回写 state_json（尽力而为，失败不影响玩法操作）。

    仅对来自 GameSession 表的会话生效（``db`` 标记）；纯内存会话（测试/插件
    直建路径）不落库，行为与原来完全一致。
    """
    db_id = session.get("db")
    if db_id is None:
        return
    try:
        with SessionLocal() as db:
            gs = db.get(GameSession, db_id)
            if gs is not None:
                gs.state_json = state
                if ended:
                    gs.ended_at = datetime.now(timezone.utc)
                db.commit()
    except Exception:
        # 持久化是尽力而为的增强，不应让玩法操作因落库失败而 5xx。
        pass


def _build_plugin_router(plugin: GameplayPlugin) -> APIRouter:
    """为一个插件构造 /api/gameplay/<name>/* 路由。"""
    router = APIRouter(prefix=f"/api/gameplay/{plugin.name}", tags=[f"gameplay-{plugin.name}"])

    @router.post("/session")
    def create_session(
        payload: SessionCreate,
        staff: User = Depends(require_referee),
    ):
        """创建对局会话（仅 admin/referee）。"""
        try:
            state = plugin.create_session(payload.match_id, payload.config)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        session_id = next(_session_seq)
        _sessions[session_id] = {
            "plugin": plugin,
            "state": state,
            "match_id": payload.match_id,
        }
        return {"session_id": session_id, "state": state}

    @router.get("/session/{session_id}/state")
    def get_session_state(
        session_id: int,
        user: User = Depends(get_current_user),
    ):
        """查询会话状态（任意登录用户；选手只读）。"""
        session = _get_session(session_id)
        try:
            state = plugin.get_state(session_id, session["state"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"session_id": session_id, "state": state}

    @router.post("/session/{session_id}/action")
    def submit_action(
        session_id: int,
        payload: ActionPayload,
        staff: User = Depends(require_referee),
    ):
        """提交选手/裁判操作（仅 admin/referee）。先 validate 后 submit。

        ``participant_id`` = 被操作的参赛单位 id（裁判替该方操作；前端
        MatchPlay 按替操作方推导 participant_a/b）。sides 校验即检查该参赛
        单位是否为合法 side 成员。操作者身份由本路由层 require_referee
        强制，插件层不感知身份。
        """
        session = _get_session(session_id)
        try:
            valid = plugin.validate_result(
                session_id, session["state"], payload.participant_id, payload.payload
            )
            if not valid:
                raise ValueError("非法操作")
            new_state = plugin.submit_result(
                session_id, session["state"], payload.participant_id, payload.payload
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        session["state"] = new_state
        _persist_session(session, new_state)
        # todo 15：玩法操作后把最新公开状态广播给该对局的 WS 订阅者。
        try:
            view = plugin.get_state(session_id, new_state)
        except ValueError:
            view = new_state
        manager.broadcast(
            session.get("match_id"),
            {"type": "state_update", "session_id": session_id, "state": view},
        )
        return {"ok": True, "state": new_state}

    @router.post("/session/{session_id}/end")
    def end_session(
        session_id: int,
        staff: User = Depends(require_referee),
    ):
        """结束对局（仅 admin/referee）；返回最终结果并从存储移除。

        participant_id 语义见 submit_action：被操作的参赛单位 id（裁判替该方
        操作）；操作者身份由本路由层 require_referee 强制，插件不感知身份。
        """
        session = _get_session(session_id)
        # 关键：必须在 end_session 之前捕获活控制器 —— end_session 内部会
        # 调用 controller.end_game()（置 game_over=True）然后 _drop_controller
        # 丢弃活实例；若事后才取控制器，_get_controller 会从陈旧的
        # controller_state 重建（game_over=False），最终状态即失真。
        # 仅三角占领等"活控制器"型插件提供 _get_controller；其余插件
        # （如测试 FakePlugin）没有该方法，保持原行为（无最终状态注入）。
        controller = (
            plugin._get_controller(session["state"])
            if hasattr(plugin, "_get_controller")
            else None
        )
        try:
            result = plugin.end_session(session_id, session["state"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        if controller is not None:
            # 用收局后的活控制器构造最终状态（只有此刻捕获的控制器才含正确胜负）。
            final_state = dict(session["state"])
            final_state["controller_state"] = controller.to_state_dict()
            final_state["elapsed_minutes"] = controller.elapsed()
        else:
            final_state = session["state"]
        # DB 持久化会话：回写最终状态（含 cells_data，供 DB 恢复桥）并置 ended_at。
        _persist_session(session, final_state, ended=True)
        _sessions.pop(session_id, None)
        # todo 15：会话结束广播，通知订阅者对局已完结。view 由注入最终
        # controller_state 的 final_state 重建：get_state 对 final_state 无活
        # 实例 -> _restore_controller 读取该状态 -> game_over=True 正确。
        try:
            view = plugin.get_state(session_id, final_state)
        except ValueError:
            view = final_state
        if controller is not None:
            # final_state 是本地临时 dict，收尾后即失效；其 id 可能被后续会话
            # 复用，必须移除为它重建的控制器，避免陈旧棋盘泄漏到新会话。
            plugin._drop_controller(final_state)
        manager.broadcast(
            session.get("match_id"),
            {"type": "session_ended", "session_id": session_id, "state": view},
        )
        return {"session_id": session_id, "result": result}

    return router


def mount_gameplay_routes(app: FastAPI) -> None:
    """为 registry 中每个已注册插件挂载 /api/gameplay/<name>/* 路由。

    幂等：同一插件名只会挂载一次。应在插件注册完成后调用
    （main.py 的 lifespan 在 register_default_plugins() 之后调用）。
    """
    for plugin in registry.all():
        if plugin.name in _mounted_plugins:
            continue
        app.include_router(_build_plugin_router(plugin))
        _mounted_plugins.add(plugin.name)
