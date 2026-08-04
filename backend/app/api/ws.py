"""WebSocket 对局状态订阅端点（todo 15）。

``/ws/matches/{match_id}``（WebSocket 升级）：
- Cookie 鉴权：与 HTTP 侧 ``get_current_user`` 相同的解码逻辑（token
  cookie -> JWT -> 校验用户 active），失败以 **4401** 拒绝 —— WS 场景
  下没有 HTTP 状态码，4401 即"未授权"（401 的 WS 语义等价物）。
- 订阅白名单（Metis E13）：仅 admin、该比赛 ``referee_ids`` 成员、以及
  参赛双方（个体报名 = user_id 相等；队伍报名 = 该队 TeamMember）可订阅；
  其余以 **1008** 拒绝。
- 连接建立后推送初始状态帧：对局进行中 -> {"type": "match_started",
  "match_id": ...}，否则 -> {"type": "no_session"}。
- 消息频率限制（Metis E13）：每连接每秒 ≤ 10 条文本消息，超限以 1008
  断开。
- 对局状态变更由 match_service 调用 ws_manager.broadcast 推送
  （match_started / score_update；玩法已从对局流程解耦，不再推送棋盘
  状态帧）。
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.core.ws_manager import _Connection, manager
from app.db import SessionLocal
from app.models.competition import Competition
from app.models.match import Match
from app.models.team import TeamMember
from app.models.user import User

router = APIRouter()

COOKIE_NAME = "token"

# WS 关闭码：4401 = 未授权（HTTP 401 的 WS 语义），1008 = 策略违反（403/频率超限）。
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 1008
CLOSE_RATE_LIMIT = 1008

# 消息频率限制（Metis E13）：1 秒窗口内最多 RATE_LIMIT_MAX 条客户端消息。
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW_SECONDS = 1.0


def _resolve_user(websocket: WebSocket) -> User | None:
    """镜像 rbac.get_current_user 的 Cookie 解码逻辑；任何失败返回 None。"""
    token = websocket.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except jwt.InvalidTokenError:
        return None
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or user.status != "active":
            return None
        return user


def _is_subscriber_allowed(
    db: Session, match: Match, competition: Competition, user: User
) -> bool:
    """Metis E13 订阅白名单：admin / 该场裁判 / 参赛双方成员。"""
    if user.role == "admin":
        return True
    if user.id in (competition.referee_ids or []):
        return True
    for participant_id in (match.participant_a, match.participant_b):
        if participant_id is None:
            continue
        if user.id == participant_id:
            return True
        member = (
            db.query(TeamMember)
            .filter(
                TeamMember.team_id == participant_id,
                TeamMember.user_id == user.id,
            )
            .first()
        )
        if member is not None:
            return True
    return False


def _load_initial_state(match_id: int) -> dict | None:
    """返回初始状态帧；对局进行中 -> {"type": "match_started", "match_id": ...}，
    未进行 -> None（端点回退为 {"type": "no_session"}）。

    玩法已从对局流程解耦：不再加载 GameSession 棋盘状态，只告知前端对局
    是否已经开始。
    """
    with SessionLocal() as db:
        match = db.get(Match, match_id)
        if match is not None and match.status == "in_progress":
            return {"type": "match_started", "match_id": match_id}
    return None


async def _send_loop(websocket: WebSocket, match_id: int, conn: _Connection) -> None:
    """发送任务：从连接队列取消息推送；连接失效时清理登记。"""
    try:
        while True:
            message = await conn.queue.get()
            await websocket.send_json(message)
    except Exception:
        # 发送失败（客户端断开 / 已 close）——交给 finally 清理。
        pass
    finally:
        manager.disconnect(match_id, conn)


@router.websocket("/ws/matches/{match_id}")
async def match_ws(websocket: WebSocket, match_id: int) -> None:
    """对局状态订阅端点：鉴权 -> 初始状态帧 -> 广播接收 + 频率限制。"""
    user = _resolve_user(websocket)
    if user is None:
        await websocket.close(code=CLOSE_UNAUTHENTICATED, reason="未登录或登录已失效")
        return

    with SessionLocal() as db:
        match = db.get(Match, match_id)
        if match is None:
            await websocket.close(code=CLOSE_FORBIDDEN, reason="对局不存在")
            return
        competition = db.get(Competition, match.competition_id)
        allowed = _is_subscriber_allowed(db, match, competition, user)
    if not allowed:
        await websocket.close(code=CLOSE_FORBIDDEN, reason="权限不足")
        return

    await websocket.accept()

    conn = manager.connect(match_id, websocket)
    sender = asyncio.create_task(_send_loop(websocket, match_id, conn))

    try:
        initial = _load_initial_state(match_id)
        if initial is None:
            await websocket.send_json({"type": "no_session"})
        else:
            await websocket.send_json(initial)
    except Exception:
        # 初始帧发送失败（连接已断开）——直接进入清理。
        pass

    # 接收循环：检测断开 + 频率限制。客户端订阅为主，正常不主动发消息。
    timestamps: list[float] = []
    try:
        while True:
            await websocket.receive_text()
            now = time.monotonic()
            timestamps.append(now)
            cutoff = now - RATE_LIMIT_WINDOW_SECONDS
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) > RATE_LIMIT_MAX:
                await websocket.close(code=CLOSE_RATE_LIMIT, reason="消息频率超限")
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(match_id, conn)
        sender.cancel()
        with suppress(asyncio.CancelledError):
            await sender
