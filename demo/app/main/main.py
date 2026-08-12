from __future__ import annotations
import asyncio
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Running `python main/main.py` by path puts only this script's folder (main/)
# on sys.path, but the `api` package lives at the project root. Add the root
# so the import below resolves regardless of the working directory.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes import router, game as controller_game, broadcast_state

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

HEADLESS = "--headless" in sys.argv

_LOG_LOCK = threading.Lock()


def _log_exception(exc_type, exc_value, exc_tb) -> None:
    import traceback

    _log("[exception] " + "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))


sys.excepthook = _log_exception  # windowed exe has no console; log crashes to temp file


if getattr(sys, "frozen", False):
    # PyInstaller windowed mode sets sys.stdout/sys.stderr to None, which
    # crashes uvicorn's log formatters (they call sys.stdout/stderr.isatty()).
    # Redirect them to the temp log file so logging works and output is kept.
    _log_stream = open(
        Path(tempfile.gettempdir()) / "triangle_controller.log",
        "a",
        encoding="utf-8",
        errors="replace",
    )
    if sys.stdout is None:
        sys.stdout = _log_stream
    if sys.stderr is None:
        sys.stderr = _log_stream


def _log(msg: str) -> None:
    """Log to the temp file (and console in dev).

    In frozen windowed mode sys.stdout is redirected to the same temp file,
    so skip print() there to avoid duplicate lines.
    """
    if not getattr(sys, "frozen", False):
        try:
            print(msg, flush=True)
        except Exception:
            pass
    try:
        log_path = Path(tempfile.gettempdir()) / "triangle_controller.log"
        with _LOG_LOCK, open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Runs after the server has started (uvicorn startup event).
    if not HEADLESS:
        port = int(os.environ.get("TRIANGLE_CONTROLLER_PORT", "8001"))
        try:
            ok = webbrowser.open(f"http://127.0.0.1:{port}")
            _log(f"[browser] webbrowser.open -> {ok} http://127.0.0.1:{port}")
        except Exception as e:  # pragma: no cover - defensive
            _log(f"[browser] webbrowser.open failed: {e!r}")
    # 超时判定不再依赖 /api/tick（机器人已改走 WebSocket，不再轮询该接口）：
    # 后台每 1s 检查一次剩余时间，到点结束比赛并向所有 WS 客户端推送 state_update。
    watchdog = asyncio.create_task(_timeout_watchdog())
    _log("[watchdog] 超时检查任务已启动")
    yield
    watchdog.cancel()
    _log("[watchdog] 超时检查任务已停止")


async def _timeout_watchdog() -> None:
    while True:
        await asyncio.sleep(1.0)
        try:
            controller_game._sync_elapsed()
            if controller_game._check_timeout():
                await broadcast_state()
                _log("[watchdog] 比赛超时，已结束并推送 state_update")
        except Exception as e:  # pragma: no cover - defensive
            _log(f"[watchdog] 超时检查异常：{e!r}")


app = FastAPI(title="三角占领 · 赛时控制器", lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


def _port_busy(port: int) -> bool:
    """Pre-bind check: can we bind both the wildcard and loopback address?

    Windows lets a 0.0.0.0 bind succeed even when another process holds
    127.0.0.1:port, which would silently shadow the real server — so check
    both to mirror how uvicorn actually binds.
    """
    for addr in ("0.0.0.0", "127.0.0.1"):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((addr, port))
        except OSError:
            return True
        finally:
            s.close()
    return False


def _is_our_service(port: int) -> bool:
    """True if a triangle-controller instance already answers on this port."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/state", timeout=1.5
        ) as resp:
            data = resp.read().decode("utf-8", "replace")
        return '"board"' in data
    except Exception:
        return False


def select_port(candidates=(8001, 8002, 8003)) -> tuple[int, bool]:
    """Return (port, already_running).

    - Free port  -> we run the server on it.
    - Port busy by our own instance -> reuse it (open browser only).
    - Port busy by something else   -> try the next port.
    """
    for port in candidates:
        if not _port_busy(port):
            return port, False
        if _is_our_service(port):
            return port, True
        _log(f"[port] {port} busy by another program, trying next port...")
    raise RuntimeError("端口 8001-8003 均被占用，无法启动服务")


if __name__ == "__main__":
    try:
        port, already_running = select_port()
    except RuntimeError as e:
        _log(f"[fatal] {e}")
        if getattr(sys, "frozen", False):
            import ctypes  # native error box for the windowed exe

            ctypes.windll.user32.MessageBoxW(0, str(e), "三角占领 · 赛时控制器", 0x10)
        sys.exit(1)

    os.environ["TRIANGLE_CONTROLLER_PORT"] = str(port)

    if already_running:
        if not HEADLESS:
            try:
                webbrowser.open(f"http://127.0.0.1:{port}")
            except Exception:
                pass
        _log(f"[start] existing instance on port {port}, opened browser, exiting")
        sys.exit(0)

    _log(f"[start] selected port {port} (headless={HEADLESS})")
    # Pass the app object directly: PyInstaller onefile cannot `import main`
    # by name (uvicorn would fail with "Could not import module main").
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
