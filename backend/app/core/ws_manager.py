"""WebSocket 连接管理器（todo 15）：单进程按 match_id 订阅广播。

设计：每条连接持有一个 :class:`asyncio.Queue`。WS 端点为该连接启动一个
发送任务，从队列取消息并 ``send_json``；HTTP 路由 / 服务层（同步线程）
通过 :meth:`ConnectionManager.broadcast` 仅做 ``put_nowait`` 入队 ——
跨线程投递不依赖事件循环引用，也绝不阻塞业务请求。实际网络发送由发送
任务在事件循环上执行（TestClient / uvicorn 均为单进程单循环，满足）。

慢消费者保护：队列满（QUEUE_MAXSIZE）即断开该连接，避免内存无界增长。

Metis E13 约束：本管理器只做连接登记与推送，不持有任何鉴权逻辑
（鉴权在 app/api/ws.py 的端点内完成）；不广播敏感管理数据。
"""

from __future__ import annotations

import asyncio
import threading

from starlette.websockets import WebSocket

# 每条连接发送队列容量；写满说明消费过慢，直接断开。
QUEUE_MAXSIZE = 200


class _Connection:
    """一条 WS 连接的包装：socket + 发送队列 + 关闭标记。"""

    __slots__ = ("websocket", "queue", "closed")

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self.closed = False


class ConnectionManager:
    """match_id -> 连接集合 的单进程连接管理器。

    线程安全：``connect`` / ``disconnect`` / ``broadcast`` 均可在事件循环
    线程或同步路由的工作线程中调用。
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[_Connection]] = {}
        self._lock = threading.Lock()

    def connect(self, match_id: int, websocket: WebSocket) -> _Connection:
        """登记一条连接并返回包装对象（WS 端点持它做收发）。"""
        conn = _Connection(websocket)
        with self._lock:
            self._connections.setdefault(match_id, set()).add(conn)
        return conn

    def disconnect(self, match_id: int, conn: _Connection) -> None:
        """移除连接（幂等）；调用方负责取消其发送任务。"""
        conn.closed = True
        with self._lock:
            conns = self._connections.get(match_id)
            if conns is not None:
                conns.discard(conn)
                if not conns:
                    self._connections.pop(match_id, None)

    def active_connections(self, match_id: int) -> int:
        """当前 match 的在线连接数（测试 / 监控用）。"""
        with self._lock:
            return len(self._connections.get(match_id, set()))

    def broadcast(self, match_id: int, message: dict) -> None:
        """把消息投递给 match 的所有连接；无连接时静默跳过。

        仅入队（put_nowait，线程安全），实际发送由各连接的发送任务完成。
        """
        with self._lock:
            conns = list(self._connections.get(match_id, set()))
        for conn in conns:
            if conn.closed:
                continue
            try:
                conn.queue.put_nowait(message)
            except asyncio.QueueFull:
                self.disconnect(match_id, conn)


manager = ConnectionManager()
