from __future__ import annotations
import asyncio
import base64
import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from controller import GameController
from controller.song_lib import parse_song_library, generate_tasks_from_songs

router = APIRouter()
game = GameController()

# Exports land in an `exports/` folder next to the executable (frozen/PyInstaller
# mode) or at the project root (dev mode, `python main/main.py`).
if getattr(sys, "frozen", False):
    EXPORT_DIR = Path(sys.executable).resolve().parent / "exports"
else:
    EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

_songs: list | None = None

_clients: set[WebSocket] = set()

# --- Auto-exit watchdog -----------------------------------------------------
# When every browser tab is closed (all WebSocket clients gone) for a sustained
# period, the controller process should exit by itself. The check MUST NOT live
# in /api/tick (that stops being called once the browser is closed), so it runs
# in a background daemon thread. os._exit(0) works in both dev (`python
# main/main.py`) and frozen (`三角占领赛时控制器.exe`) mode.
_EXIT_GRACE_SECONDS = 10.0
_CHECK_INTERVAL_SECONDS = 2.0
_no_client_since: float | None = None
_autoexit_stop = threading.Event()


def _autoexit_log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass
    try:
        log_path = Path(tempfile.gettempdir()) / "triangle_controller.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _auto_exit_loop() -> None:
    global _no_client_since
    while not _autoexit_stop.is_set():
        _autoexit_stop.wait(_CHECK_INTERVAL_SECONDS)
        if _autoexit_stop.is_set():
            return
        if len(_clients) > 0:
            # A client (re)connected: cancel any pending exit.
            _no_client_since = None
            continue
        if not game.started:
            # Don't exit just because a page loaded and closed before init.
            _no_client_since = None
            continue
        now = time.time()
        if _no_client_since is None:
            _no_client_since = now
            continue
        if now - _no_client_since >= _EXIT_GRACE_SECONDS:
            _autoexit_log(
                f"[auto-exit] no websocket clients for "
                f"{_EXIT_GRACE_SECONDS:.0f}s, exiting"
            )
            os._exit(0)


threading.Thread(
    target=_auto_exit_loop, name="auto-exit-watchdog", daemon=True
).start()


async def broadcast_state() -> None:
    if not _clients:
        return
    state = game.to_state_dict()
    dead: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_json({"type": "state_update", **state})
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


class InitReq(BaseModel):
    mode: str = "random"
    cells_data: list[dict] | None = None
    seed: int | None = None


class OccupyReq(BaseModel):
    cell_id: int
    team: str
    score: int | None = None
    tp: float | None = None


class CancelReq(BaseModel):
    cell_id: int


class TimeLimitReq(BaseModel):
    minutes: float


@router.post("/api/init")
async def api_init(req: InitReq):
    if req.mode == "custom" and req.cells_data:
        game.init(req.cells_data)
    elif _songs is None:
        return JSONResponse(status_code=400, content={"ok": False, "error": "请先导入歌曲库"})
    else:
        try:
            cells_data = generate_tasks_from_songs(_songs, req.seed)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})
        game.init(cells_data)
    await broadcast_state()
    return {"ok": True, "state": game.to_state_dict()}


@router.post("/api/songs")
async def api_songs(body: dict[str, Any]):
    if game.started and not game.game_over:
        return JSONResponse(status_code=400, content={"ok": False, "error": "开局中禁止覆盖歌曲库"})
    try:
        songs = parse_song_library(body)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})
    global _songs
    _songs = songs
    return {"ok": True, "count": len(songs)}


@router.get("/api/songs")
async def api_songs_get():
    songs = [{"name": s.name, "type": s.type, "level": s.level, "diff_score": s.diff_score}
             for s in _songs] if _songs else []
    return {"songs": songs, "loaded": _songs is not None}


@router.post("/api/occupy")
async def api_occupy(req: OccupyReq):
    ok = game.occupy(req.cell_id, req.team, req.score, req.tp)
    await broadcast_state()
    return {"ok": ok, "state": game.to_state_dict()}


@router.post("/api/cancel")
async def api_cancel(req: CancelReq):
    ok = game.cancel_occupy(req.cell_id)
    await broadcast_state()
    return {"ok": ok, "state": game.to_state_dict()}


@router.post("/api/end")
async def api_end():
    ok = game.end_game()
    await broadcast_state()
    return {"ok": ok, "state": game.to_state_dict()}


@router.post("/api/time_limit")
async def api_time_limit(req: TimeLimitReq):
    game.time_limit_minutes = req.minutes
    await broadcast_state()
    return {"ok": True, "state": game.to_state_dict()}


@router.get("/api/tick")
async def api_tick():
    game._sync_elapsed()
    if game._check_timeout():
        await broadcast_state()
    return {"elapsed": round(game.elapsed(), 2),
            "time_limit": game.time_limit_minutes,
            "game_over": game.game_over}


@router.get("/api/state")
async def api_state():
    return game.to_state_dict()


@router.get("/api/tasks")
async def api_tasks():
    return game.export_tasks()


@router.get("/api/scores")
async def api_scores():
    return game.get_scores()


def _unique_export_path(filename: str) -> Path:
    """Return a non-existing path so repeated exports never overwrite files."""
    candidate = EXPORT_DIR / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(1, 10000):
        candidate = EXPORT_DIR / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("导出文件名冲突过多")


def _export_timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1_000_000:06d}"


@router.get("/api/events/export")
async def api_events_export(save: str | None = None):
    events = [e.to_dict() for e in game.events]
    ts = _export_timestamp()
    body = json.dumps(events, ensure_ascii=False, indent=2)
    filename = f"events_{ts}.json"
    if save == "1":
        # Save-to-disk mode: write the file and return its path instead of a download.
        full_path = _unique_export_path(filename)
        full_path.write_text(body, encoding="utf-8", newline="")
        return {"ok": True, "path": str(full_path), "filename": full_path.name}
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/screenshot")
async def api_screenshot(body: dict[str, Any]):
    image = body.get("image", "")
    filename = body.get("filename", "")
    if not isinstance(image, str) or not image.strip():
        return JSONResponse(status_code=400, content={"ok": False, "error": "缺少 image 数据"})
    # Sanitize: keep only the final path component and require a .png suffix.
    filename = Path(filename or "").name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.png", filename, re.IGNORECASE):
        return JSONResponse(status_code=400, content={"ok": False, "error": "文件名必须以 .png 结尾"})
    if image.startswith("data:"):
        # Strip a "data:image/png;base64," style prefix if present.
        header, _, b64 = image.partition(",")
        if "base64" not in header:
            return JSONResponse(status_code=400, content={"ok": False, "error": "仅支持 base64 图片数据"})
        b64 = b64.strip()
    else:
        b64 = image.strip()
    if len(b64) > 28_000_000:
        return JSONResponse(status_code=413, content={"ok": False, "error": "图片数据过大，不能超过 21 MB"})
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "base64 解码失败"})
    if not raw:
        return JSONResponse(status_code=400, content={"ok": False, "error": "图片数据为空"})
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "图片不是有效的 PNG 文件"})
    full_path = _unique_export_path(filename)
    full_path.write_bytes(raw)
    return {"ok": True, "path": str(full_path), "filename": full_path.name}


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    try:
        await ws.send_json({"type": "state_update", **game.to_state_dict()})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _clients.discard(ws)
    except Exception:
        _clients.discard(ws)
