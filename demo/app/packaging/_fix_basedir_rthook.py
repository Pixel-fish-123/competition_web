r"""PyInstaller runtime hook — fixes the onefile BASE_DIR mismatch.

main/main.py computes BASE_DIR = Path(__file__).resolve().parent.parent.
PyInstaller onefile flattens the entry script to <_MEIPASS>\main.py, so in
frozen mode BASE_DIR resolves to %TEMP% (ONE level above _MEIPASS), while the
bundled frontend/ and config/ folders live under _MEIPASS. The app therefore
looks for %TEMP%\frontend and %TEMP%\config, which do not exist — the
StaticFiles mount at app startup would crash with "Directory ... does not
exist".

This hook bridges the gap: it creates %TEMP%\frontend and %TEMP%\config as
directory junctions pointing at the live _MEIPASS copies. Junctions require no
admin rights (unlike symlinks), leave no duplicate content, and are re-created
on every boot so they always reference the current _MEIPASS. A stale junction
left over from a previous run is removed first. Real directories that already
occupy the name are left untouched.
"""

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FILE_ATTRIBUTE_REPARSE_POINT = 0x400  # 1024


def _log(msg: str) -> None:
    log_path = Path(tempfile.gettempdir()) / "triangle_controller.log"
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [rthook] {msg}\n")
    except Exception:
        pass


def _is_junction(path: Path) -> bool:
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    except Exception as e:
        _log(f"_is_junction({path}) ctypes error: {e!r}")
        return False
    if attrs < 0:
        return False
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def _ensure_mirror(name: str) -> None:
    meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    src = meipass / name
    dst = Path(tempfile.gettempdir()) / name
    _log(
        f"mirror start: name={name} _MEIPASS={meipass} "
        f"src_exists={src.is_dir()} dst={dst}"
    )
    if not src.is_dir():
        _log(f"SKIP: source missing {src}")
        return
    if _is_junction(dst):
        _log(f"removing stale junction {dst}")
        try:
            os.rmdir(dst)
        except OSError as e:
            _log(f"rmdir stale junction failed: {e!r}")
            return
    elif dst.exists():
        _log(f"SKIP: real directory exists at {dst}")
        return
    try:
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except Exception as e:
        _log(f"mklink FAILED: {e!r}")
        try:
            _log(f"mklink stderr: {proc.stderr.strip()}")
        except Exception:
            pass
        return
    _log(f"mklink OK: {proc.stdout.strip()}")


_ensure_mirror("frontend")
_ensure_mirror("config")
_log("rthook done")
