"""玩法插件 HTTP 路由（todo 12）：为每个已注册插件自动挂载
``/api/gameplay/<name>/*`` 路由。

路由（每个插件一套）:
- POST /session                   创建对局会话（admin/referee）
- GET  /session/{id}/state        查询会话状态（任意登录用户，选手只读）
- POST /session/{id}/action       提交选手/裁判操作（admin/referee）
- POST /session/{id}/end          结束对局（admin/referee）

权限（用户 2026-08-02 最终确认）：对局中仅 referee/admin 可操作棋盘
（创建会话/提交操作/结束对局），选手只读（仅可查询会话状态）。

会话存储：当前为进程内内存 dict（{session_id: {"plugin", "state"}}），
服务重启即丢失；todo 14 引入 GameSession 模型后改为 DB 持久化。

所有插件抛出的 :class:`ValueError` 统一转换为 HTTP 400（detail=str(e)）。
"""

from __future__ import annotations

import itertools

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.core.rbac import get_current_user, require_referee
from app.core.ws_manager import manager
from app.models.user import User
from app.plugins.base import GameplayPlugin
from app.plugins.registry import registry

# 会话存储（内存版，todo 14 换 DB 持久化）：
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
    participant_id: int
    payload: dict = {}


def _get_plugin(name: str) -> GameplayPlugin:
    plugin = registry.get(name)
    if plugin is None:
        raise HTTPException(status_code=404, detail="玩法插件不存在")
    return plugin


def _get_session(session_id: int) -> dict:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="对局会话不存在")
    return session


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
        """提交选手/裁判操作（仅 admin/referee）。先 validate 后 submit。"""
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
        """结束对局（仅 admin/referee）；返回最终结果并从存储移除。"""
        session = _get_session(session_id)
        try:
            result = plugin.end_session(session_id, session["state"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        _sessions.pop(session_id, None)
        # todo 15：会话结束广播，通知订阅者对局已完结。
        manager.broadcast(
            session.get("match_id"),
            {"type": "session_ended", "session_id": session_id},
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
