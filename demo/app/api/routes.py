from __future__ import annotations
import asyncio
import base64
import collections
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request, WebSocket, WebSocketDisconnect
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

# --- 成绩上传协议 v1（/api/v1/*）------------------------------------------
# 玩家设备/机台通过 HTTP 上传成绩，由控制器自动完成 歌曲→格子 映射、
# 普通格占领与 L1 挑战。协议文档见 app/docs/成绩上传协议.md。
_V1_RATE_BURST = 5                 # 每 (team, player) 60s 内最多 5 次
_V1_RATE_WINDOW = 60.0
_V1_RATE_MIN_INTERVAL = 3.0        # 两次上传最小间隔 3s
_V1_DEDUPE_SECONDS = 60.0          # 同歌同队同玩家短时间去重窗口
_V1_BATCH_MAX = 50                 # 单次批量上限
_V1_CACHE_MAX = 5000
# 严格任务校验：上传成绩必须满足格子任务要求（STRICT_TASK_CHECK=0 可关闭）
_STRICT_TASK_CHECK = os.environ.get("STRICT_TASK_CHECK", "1") != "0"

_MATCH_TOKEN: str | None = None
_TEAM_TOKENS: dict[str, str] = {}
_result_cache: dict[str, dict] = {}  # client_msg_id -> {"status": int, "body": dict}
_recent_results: dict[tuple[str, str, str], tuple[float, str]] = {}  # (team, song, player) -> (ts, msg_id)
_rl: dict[tuple[str, str], collections.deque] = {}  # (team, player) -> timestamps
_v1_lock = asyncio.Lock()

# --- Auto-exit watchdog -----------------------------------------------------
# When every browser tab is closed (all WebSocket clients gone) for a sustained
# period, the controller process should exit by itself. The check MUST NOT live
# in /api/tick (that stops being called once the browser is closed), so it runs
# in a background daemon thread. os._exit(0) works in both dev (`python
# main/main.py`) and frozen (`三角占领赛时控制器.exe`) mode.
# Headless mode is used for API smoke tests, which never hold a WebSocket
# open, so the watchdog is disabled there.
_EXIT_GRACE_SECONDS = 10.0
_CHECK_INTERVAL_SECONDS = 2.0
_HEADLESS = "--headless" in sys.argv
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
        if _HEADLESS:
            # API smoke mode never keeps a WebSocket open; never self-exit.
            _no_client_since = None
            continue
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
        try:
            game.init(req.cells_data)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})
    elif _songs is None:
        return JSONResponse(status_code=400, content={"ok": False, "error": "请先导入歌曲库"})
    else:
        try:
            cells_data = generate_tasks_from_songs(_songs, req.seed)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})
        game.init(cells_data)
    _reset_v1_tokens()
    await broadcast_state()
    return {
        "ok": True,
        "tokens": {
            "match": _MATCH_TOKEN,
            "defender": _TEAM_TOKENS["defender"],
            "attacker": _TEAM_TOKENS["attacker"],
        },
        "state": game.to_state_dict(),
    }


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
    if not math.isfinite(req.minutes) or req.minutes <= 0:
        return JSONResponse(status_code=400, content={"ok": False, "error": "时间限制必须是正数（分钟）"})
    game.time_limit_minutes = req.minutes
    await broadcast_state()
    return {"ok": True, "state": game.to_state_dict()}


@router.post("/api/pause")
async def api_pause():
    if not game.started or game.game_over:
        return JSONResponse(status_code=400, content={"ok": False, "error": "比赛未进行中，无法暂停"})
    game.toggle_pause()
    await broadcast_state()
    return {"ok": True, "paused": game.paused, "state": game.to_state_dict()}


@router.post("/api/exit")
async def api_exit(background_tasks: BackgroundTasks):
    """退出工具：直接结束控制器进程（本地裁判端用）。

    响应先返回给浏览器，再由后台任务 os._exit(0) 终止进程；
    与 auto-exit watchdog 的退出机制一致，dev 与打包 exe 均可用。
    """
    background_tasks.add_task(os._exit, 0)
    return {"ok": True, "message": "控制器即将退出"}


@router.get("/api/tick")
async def api_tick():
    game._sync_elapsed()
    if game._check_timeout():
        await broadcast_state()
    return {"elapsed": round(game.elapsed(), 2),
            "time_limit": game.time_limit_minutes,
            "game_over": game.game_over,
            "paused": game.paused,
            "l1_energy": game.l1_energy,
            "l1_energy_progress": game._l1_energy_progress()}


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
        return JSONResponse(status_code=413, content={"ok": False, "error": "图片数据过大，不能超过约 21 MB（base64 约 26.7 MB）"})
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


# =====================================================================
# 成绩上传协议 v1
# =====================================================================


def _reset_v1_tokens() -> None:
    """开局时生成（或从环境变量读取）比赛令牌与两个阵营令牌，并清空缓存。"""
    global _MATCH_TOKEN, _TEAM_TOKENS
    _MATCH_TOKEN = os.environ.get("MATCH_TOKEN") or secrets.token_hex(16)
    _TEAM_TOKENS = {
        "defender": os.environ.get("DEFENDER_TEAM_TOKEN") or secrets.token_hex(8),
        "attacker": os.environ.get("ATTACKER_TEAM_TOKEN") or secrets.token_hex(8),
    }
    _result_cache.clear()
    _recent_results.clear()
    _rl.clear()


def _v1_error(status: int, code: str, message: str, request_id: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"ok": False, "code": code, "message": message}
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=status, content=body)


def _v1_team_from_token(token: str) -> str | None:
    """按阵营令牌识别阵营；无效返回 None。"""
    for team in ("defender", "attacker"):
        if _TEAM_TOKENS.get(team) and hmac.compare_digest(token, _TEAM_TOKENS[team]):
            return team
    return None


def _v1_auth_ok(match_token: str | None, team_token: str | None) -> tuple[bool, str | None, int]:
    """校验比赛令牌与阵营令牌。返回 (ok, auth_team, http_status)。"""
    if _MATCH_TOKEN is None:
        return False, None, 409
    if not match_token or not team_token:
        return False, None, 401
    if not hmac.compare_digest(match_token, _MATCH_TOKEN):
        return False, None, 401
    auth_team = _v1_team_from_token(team_token)
    if auth_team is None:
        return False, None, 401
    return True, auth_team, 200


def _v1_signature_check(
    path: str,
    headers,
    client_msg_id: str,
    raw_body: bytes,
) -> str | None:
    """可选 HMAC-SHA256 签名校验；无签名头返回 None，失败返回错误码。"""
    ts = headers.get("x-timestamp")
    sig = headers.get("x-signature")
    if ts is None and sig is None:
        return None
    if _MATCH_TOKEN is None or ts is None or sig is None:
        return "MISSING_AUTH"
    try:
        ts_i = int(ts)
    except (TypeError, ValueError):
        return "BAD_SIGNATURE"
    if abs(time.time() - ts_i) > 300:
        return "STALE_REQUEST"
    canonical = f"POST\n{path}\n{ts}\n{client_msg_id}\n".encode("utf-8") + raw_body
    expected = hmac.new(_MATCH_TOKEN.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig.strip()):
        return "BAD_SIGNATURE"
    return None


def _v1_validate_upload(data: Any) -> tuple[dict | None, str | None]:
    """校验单条上传结构，返回 (规范化数据, 错误信息)；错误信息为 None 表示成功。"""
    if not isinstance(data, dict):
        return None, "请求体必须是 JSON 对象"
    api_version = data.get("api_version")
    if api_version is not None and api_version != "1":
        return None, "api_version 仅支持 1"
    msg_id = data.get("client_msg_id")
    if not isinstance(msg_id, str) or not msg_id.strip() or len(msg_id) > 64:
        return None, "client_msg_id 缺失或格式错误（1-64 字符）"
    team = data.get("team")
    if team not in ("defender", "attacker"):
        return None, "team 仅接受 defender / attacker"
    player = data.get("player")
    if not isinstance(player, dict):
        return None, "player 必须是对象"
    pid = player.get("id")
    if not isinstance(pid, str) or not pid.strip() or len(pid) > 64:
        return None, "player.id 缺失或格式错误（1-64 字符）"
    pname = player.get("name")
    if pname is not None and not isinstance(pname, str):
        return None, "player.name 必须是字符串"
    song = data.get("song")
    if not isinstance(song, dict):
        return None, "song 必须是对象"
    sname = song.get("name")
    if not isinstance(sname, str) or not sname.strip():
        return None, "song.name 缺失"
    for key in ("level", "type"):
        if song.get(key) is not None and not isinstance(song.get(key), str):
            return None, f"song.{key} 必须是字符串"
    result = data.get("result")
    if not isinstance(result, dict):
        return None, "result 必须是对象"
    score = result.get("score")
    if score is not None:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return None, "result.score 必须是 0-10000000 的整数"
        if isinstance(score, float) and not score.is_integer():
            return None, "result.score 必须是 0-10000000 的整数"
        if not (0 <= score <= 10_000_000):
            return None, "result.score 必须是 0-10000000 的整数"
        score = int(score)
    tp = result.get("tp")
    if tp is not None:
        if isinstance(tp, bool) or not isinstance(tp, (int, float)):
            return None, "result.tp 必须是 0-100 的数字"
        if not (0 <= tp <= 100.0):
            return None, "result.tp 必须是 0-100 的数字"
        tp = float(tp)
    for key in ("miss", "bad", "good"):
        v = result.get(key)
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            return None, f"result.{key} 必须是非负整数"
    for key in ("full_combo", "mm"):
        if result.get(key) is not None and not isinstance(result.get(key), bool):
            return None, f"result.{key} 必须是布尔值"
    client_ts = data.get("client_ts")
    if client_ts is not None and not isinstance(client_ts, str):
        return None, "client_ts 必须是字符串"
    device = data.get("device")
    if device is not None:
        if not isinstance(device, dict):
            return None, "device 必须是对象"
        for key in ("id", "app"):
            if device.get(key) is not None and not isinstance(device.get(key), str):
                return None, f"device.{key} 必须是字符串"
    return {
        "client_msg_id": msg_id.strip(),
        "team": team,
        "player_id": pid.strip(),
        "player_name": pname.strip() if isinstance(pname, str) else "",
        "song_name": sname.strip(),
        "score": score,
        "tp": tp,
        "full_combo": result.get("full_combo"),
        "mm": result.get("mm"),
        "miss": result.get("miss"),
        "bad": result.get("bad"),
        "good": result.get("good"),
        "client_ts": client_ts,
        "device": device or {},
    }, None


def _v1_rate_limited(team: str, player_id: str) -> tuple[bool, float]:
    """滑动窗口限流：60s 内最多 5 次、最小间隔 3s。返回 (是否超限, Retry-After 秒数)。"""
    now = time.time()
    key = (team, player_id)
    dq = _rl.setdefault(key, collections.deque())
    while dq and now - dq[0] > _V1_RATE_WINDOW:
        dq.popleft()
    if len(dq) >= _V1_RATE_BURST:
        return True, max(1.0, _V1_RATE_WINDOW - (now - dq[0]))
    if dq and now - dq[-1] < _V1_RATE_MIN_INTERVAL:
        return True, max(1.0, _V1_RATE_MIN_INTERVAL - (now - dq[-1]))
    dq.append(now)
    # 键数封顶：只保留仍在滑动窗口内的活跃 (team, player)，避免无限累积。
    if len(_rl) > _V1_CACHE_MAX:
        stale = [k for k, d in _rl.items() if not d or now - d[-1] > _V1_RATE_WINDOW]
        for k in stale:
            _rl.pop(k, None)
    return False, 0.0


def _v1_find_cell(song_name: str):
    """按歌名在当前 21 个任务格中查找格子；找不到返回 None。"""
    return next((c for c in game.cells[:21] if c.song_name == song_name), None)


_TASK_MM_RE = re.compile(r"达成\s*MM", re.I)
_TASK_FC_RE = re.compile(r"达成\s*FULL\s*COMBO", re.I)
_TASK_TP_RE = re.compile(r"达成\s*tp\s*([\d.]+)\s*以上", re.I)
_TASK_W_RE = re.compile(r"达成\s*([\d.]+)\s*w以上", re.I)
_TASK_MBG_RE = re.compile(r"达成\s*miss\s*<=\s*(\d+)\s*,\s*bad\s*<=\s*(\d+)\s*,\s*good\s*<=\s*(\d+)", re.I)


def _task_issue(task_name: str, result: dict) -> str | None:
    """按任务名校验成绩，返回第一个未满足的条件描述；满足返回 None。

    严格模式下（STRICT_TASK_CHECK=1）缺失关键字段视为不满足并给出明确错误，
    不再把「无法校验」当成「通过」（否则 MM 任务不传 mm 也会被放行）。
    """
    if not task_name or "L1" in task_name:
        return None
    if _TASK_MM_RE.search(task_name):
        if result.get("mm") is not True:
            return "缺少 MM 达成标记（mm=true）" if result.get("mm") is None else "未达成 MM"
        return None
    if _TASK_FC_RE.search(task_name):
        if result.get("full_combo") is not True:
            return "缺少 FULL COMBO 达成标记（full_combo=true）" if result.get("full_combo") is None else "未达成 FULL COMBO"
        return None
    if _TASK_TP_RE.search(task_name):
        need = float(_TASK_TP_RE.search(task_name).group(1))
        tp = result.get("tp")
        if tp is None:
            return "缺少 tp 成绩"
        if tp < need:
            return f"tp={tp} < {need}"
        return None
    if _TASK_W_RE.search(task_name):
        need = float(_TASK_W_RE.search(task_name).group(1)) * 10000
        score = result.get("score")
        if score is None:
            return "缺少 score 成绩"
        if score < need:
            return f"score={score:,} < {need:,.0f}"
        return None
    if _TASK_MBG_RE.search(task_name):
        m = _TASK_MBG_RE.search(task_name)
        lim_m, lim_b, lim_g = int(m.group(1)), int(m.group(2)), int(m.group(3))
        for key, lim, label in (
            ("miss", lim_m, "miss"),
            ("bad", lim_b, "bad"),
            ("good", lim_g, "good"),
        ):
            if result.get(key) is None:
                return f"缺少 {label} 统计"
        if result["miss"] > lim_m:
            return f"miss={result['miss']} > {lim_m}"
        if result["bad"] > lim_b:
            return f"bad={result['bad']} > {lim_b}"
        if result["good"] > lim_g:
            return f"good={result['good']} > {lim_g}"
        return None
    return None


def _v1_elapsed() -> str:
    total = int(game.elapsed() * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


async def _v1_handle_item(data: dict, request_id: str) -> tuple[int, dict]:
    """处理一条已通过结构校验的成绩上传（含幂等/去重/状态/映射/占领）。"""
    msg_id = data["client_msg_id"]
    cached = _result_cache.get(msg_id)
    if cached is not None:
        return cached["status"], cached["body"]

    if not game.started:
        return 409, {"ok": False, "code": "MATCH_NOT_STARTED", "message": "比赛未开局", "request_id": request_id}
    if game.game_over:
        return 409, {"ok": False, "code": "MATCH_ENDED", "message": "比赛已结束", "request_id": request_id}

    song_name = data["song_name"]
    cell = _v1_find_cell(song_name)
    if cell is None:
        if _songs is not None and any(s.name == song_name for s in _songs):
            return 404, {"ok": False, "code": "SONG_NOT_IN_TASKS", "message": f"歌曲不在本局任务表中：{song_name}", "request_id": request_id}
        return 404, {"ok": False, "code": "SONG_NOT_FOUND", "message": f"歌曲不在歌曲库中：{song_name}", "request_id": request_id}

    dedupe_key = (data["team"], song_name, data["player_id"])
    now = time.time()
    prev = _recent_results.get(dedupe_key)
    if prev is not None and prev[1] != msg_id and now - prev[0] <= _V1_DEDUPE_SECONDS:
        return 409, {"ok": False, "code": "DUPLICATE_RESULT", "message": "同一歌曲短时间内已有上报", "request_id": request_id}

    outcome = ""
    async with _v1_lock:
        cell = _v1_find_cell(song_name)
        if cell is None:
            return 404, {"ok": False, "code": "SONG_NOT_IN_TASKS", "message": f"歌曲不在本局任务表中：{song_name}", "request_id": request_id}
        if cell.id == 0:
            if data["score"] is None:
                return 400, {"ok": False, "code": "VALIDATION_ERROR", "message": "L1 挑战必须提供 result.score", "request_id": request_id}
            game.occupy(0, data["team"], data["score"], data["tp"])
            outcome = "l1_holder" if game.l1_high_team == data["team"] else "l1_challenged_lost"
            await broadcast_state()
        elif cell.owner is None:
            if _STRICT_TASK_CHECK:
                issue = _task_issue(cell.task_name, data)
                if issue is not None:
                    return 422, {"ok": False, "code": "TASK_NOT_SATISFIED", "message": f"成绩不满足任务要求（{issue}）：{cell.task_name}", "request_id": request_id}
            game.occupy(cell.id, data["team"], data["score"], data["tp"])
            outcome = "occupied"
            await broadcast_state()
        else:
            outcome = "already_occupied"

    cell = _v1_find_cell(song_name)
    body = {
        "ok": True,
        "code": "RESULT_PROCESSED",
        "outcome": outcome,
        "data": {
            "cell_id": cell.id if cell is not None else None,
            "song_name": song_name,
            "task_name": cell.task_name if cell is not None else "",
            "team": data["team"],
            "l1_holder": game.l1_high_team,
            "scores": game.get_scores(),
            "elapsed": _v1_elapsed(),
            "event": game.events[0].text if game.events else "",
        },
        "request_id": request_id,
    }
    _result_cache[msg_id] = {"status": 200, "body": body}
    _recent_results[dedupe_key] = (now, msg_id)
    if len(_result_cache) > _V1_CACHE_MAX:
        _result_cache.pop(next(iter(_result_cache)))
    if len(_recent_results) > _V1_CACHE_MAX:
        _recent_results.pop(next(iter(_recent_results)))
    return 200, body


@router.post("/api/v1/results")
async def api_v1_result(request: Request):
    request_id = secrets.token_hex(6)
    raw = await request.body()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return _v1_error(400, "INVALID_JSON", "请求体不是合法 JSON", request_id)

    ok, auth_team, status = _v1_auth_ok(
        request.headers.get("x-match-token"), request.headers.get("x-team-token")
    )
    if not ok:
        code = "MATCH_NOT_STARTED" if status == 409 else "MISSING_AUTH" if not request.headers.get("x-match-token") or not request.headers.get("x-team-token") else "INVALID_TOKEN"
        return _v1_error(status, code, "鉴权失败" if status == 401 else "比赛未开局，请先 POST /api/init", request_id)

    msg_hint = data.get("client_msg_id") if isinstance(data.get("client_msg_id"), str) else ""
    sig_err = _v1_signature_check("/api/v1/results", request.headers, msg_hint, raw)
    if sig_err is not None:
        return _v1_error(401, sig_err, "签名校验失败", request_id)

    item, verr = _v1_validate_upload(data)
    if verr is not None:
        return _v1_error(400, "VALIDATION_ERROR", verr, request_id)
    if item["team"] != auth_team:
        return _v1_error(403, "TEAM_TOKEN_MISMATCH", "team 与 X-Team-Token 阵营不一致", request_id)

    # 幂等：同 client_msg_id 重放直接返回首次结果（不受限流影响）
    cached = _result_cache.get(item["client_msg_id"])
    if cached is not None:
        return JSONResponse(status_code=cached["status"], content=cached["body"])
    # 去重：同 (team, song, player) 短时间重复上报
    if game.started and not game.game_over:
        dup_cell = _v1_find_cell(item["song_name"])
        if dup_cell is not None:
            prev = _recent_results.get((item["team"], item["song_name"], item["player_id"]))
            if prev is not None and prev[1] != item["client_msg_id"] and time.time() - prev[0] <= _V1_DEDUPE_SECONDS:
                return _v1_error(409, "DUPLICATE_RESULT", "同一歌曲短时间内已有上报", request_id)

    limited, retry_after = _v1_rate_limited(item["team"], item["player_id"])
    if limited:
        resp = _v1_error(429, "RATE_LIMITED", "上传过于频繁，请稍后重试", request_id)
        resp.headers["Retry-After"] = str(int(retry_after))
        return resp

    status, body = await _v1_handle_item(item, request_id)
    return JSONResponse(status_code=status, content=body)


@router.post("/api/v1/results/batch")
async def api_v1_results_batch(request: Request):
    request_id = secrets.token_hex(6)
    raw = await request.body()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return _v1_error(400, "INVALID_JSON", "请求体不是合法 JSON", request_id)

    ok, auth_team, status = _v1_auth_ok(
        request.headers.get("x-match-token"), request.headers.get("x-team-token")
    )
    if not ok:
        code = "MATCH_NOT_STARTED" if status == 409 else "MISSING_AUTH" if not request.headers.get("x-match-token") or not request.headers.get("x-team-token") else "INVALID_TOKEN"
        return _v1_error(status, code, "鉴权失败" if status == 401 else "比赛未开局，请先 POST /api/init", request_id)

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return _v1_error(400, "VALIDATION_ERROR", "items 必须是数组", request_id)
    if len(items) > _V1_BATCH_MAX:
        return _v1_error(400, "VALIDATION_ERROR", f"单次最多 {_V1_BATCH_MAX} 条", request_id)

    envelope_msg = data.get("client_msg_id") if isinstance(data.get("client_msg_id"), str) else ""
    sig_err = _v1_signature_check("/api/v1/results/batch", request.headers, envelope_msg, raw)
    if sig_err is not None:
        return _v1_error(401, sig_err, "签名校验失败", request_id)

    out: list[dict] = []
    for i, it in enumerate(items):
        item, verr = _v1_validate_upload(it)
        if verr is not None:
            out.append({"index": i, "ok": False, "code": "VALIDATION_ERROR", "message": verr})
            continue
        if item["team"] != auth_team:
            out.append({"index": i, "ok": False, "code": "TEAM_TOKEN_MISMATCH", "message": "team 与 X-Team-Token 阵营不一致"})
            continue
        cached = _result_cache.get(item["client_msg_id"])
        if cached is not None:
            body = dict(cached["body"])
            body["index"] = i
            out.append(body)
            continue
        if game.started and not game.game_over:
            dup_cell = _v1_find_cell(item["song_name"])
            if dup_cell is not None:
                prev = _recent_results.get((item["team"], item["song_name"], item["player_id"]))
                if prev is not None and prev[1] != item["client_msg_id"] and time.time() - prev[0] <= _V1_DEDUPE_SECONDS:
                    out.append({"index": i, "ok": False, "code": "DUPLICATE_RESULT", "message": "同一歌曲短时间内已有上报"})
                    continue
        limited, _ = _v1_rate_limited(item["team"], item["player_id"])
        if limited:
            out.append({"index": i, "ok": False, "code": "RATE_LIMITED", "message": "上传过于频繁，请稍后重试"})
            continue
        status, body = await _v1_handle_item(item, request_id)
        body = dict(body)
        body["index"] = i
        out.append(body)
    return {"ok": True, "items": out}


@router.get("/api/v1/tasks")
async def api_v1_tasks(request: Request):
    ok, _, status = _v1_auth_ok(
        request.headers.get("x-match-token"), request.headers.get("x-team-token")
    )
    if not ok:
        code = "MATCH_NOT_STARTED" if status == 409 else "MISSING_AUTH" if not request.headers.get("x-match-token") or not request.headers.get("x-team-token") else "INVALID_TOKEN"
        return _v1_error(status, code, "鉴权失败" if status == 401 else "比赛未开局，请先 POST /api/init")
    tasks = []
    for c in game.cells[:21]:
        tasks.append({
            "cell_id": c.id,
            "is_l1": c.id == 0,
            "song_name": c.song_name,
            "song_level": c.song_level,
            "task_name": c.task_name,
            "total_score": c.total_score,
            "occupied_by": c.owner,
            "claimable": c.id == 0 or c.owner is None,
        })
    return {"ok": True, "tasks": tasks}


@router.get("/api/v1/results/{client_msg_id}")
async def api_v1_result_status(client_msg_id: str, request: Request):
    ok, _, status = _v1_auth_ok(
        request.headers.get("x-match-token"), request.headers.get("x-team-token")
    )
    if not ok:
        code = "MATCH_NOT_STARTED" if status == 409 else "MISSING_AUTH" if not request.headers.get("x-match-token") or not request.headers.get("x-team-token") else "INVALID_TOKEN"
        return _v1_error(status, code, "鉴权失败" if status == 401 else "比赛未开局，请先 POST /api/init")
    cached = _result_cache.get(client_msg_id)
    if cached is None:
        return _v1_error(404, "NOT_FOUND", "未找到该 client_msg_id 的处理记录")
    return JSONResponse(status_code=cached["status"], content=cached["body"])


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
