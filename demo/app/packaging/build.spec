# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for 三角占领 · 赛时控制器 (single-file windowed exe).
#
# - Onefile GUI (console=False) executable.
# - collect_all(fastapi) + collect_all(uvicorn) so every submodule/data/metadata
#   of the two frameworks is bundled (uvicorn is passed the app object directly,
#   so it never needs to import the entry module by name).
# - _fix_basedir_rthook.py runtime hook bridges the onefile BASE_DIR mismatch:
#   the entry script is flattened to <_MEIPASS>\main.py, so main.py's
#   Path(__file__).parent.parent resolves to %TEMP% instead of _MEIPASS. The
#   hook creates %TEMP%\frontend and %TEMP%\config as junctions to the live
#   _MEIPASS copies.
# - datas bundle frontend/ and config/rules.json under _MEIPASS.

import os

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

for _pkg in ("fastapi", "uvicorn"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# App packages (api.routes / controller.*) are imported statically, but list
# them explicitly so the bundle survives any analysis quirk.
hiddenimports += [
    "api.routes",
    "controller",
    "controller.board",
    "controller.game",
    "controller.rules",
    "controller.task_gen",
    "controller.song_lib",
]

_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
_APP_DIR = os.path.dirname(_SPEC_DIR)

# Static frontend + external rules config land at <_MEIPASS>\frontend and
# <_MEIPASS>\config\rules.json.
datas += [
    (os.path.join(_APP_DIR, "frontend", "*"), "frontend"),
    (os.path.join(_APP_DIR, "config", "rules.json"), "config"),
]

a = Analysis(
    [os.path.join(_APP_DIR, "main", "main.py")],
    pathex=[_APP_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(_SPEC_DIR, "_fix_basedir_rthook.py")],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="三角占领赛时控制器",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
