"""Environment discovery: where we run, where we store things, where assets live.

Kept dependency free so every other module can import it safely.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
IS_FROZEN = bool(getattr(sys, "frozen", False))

#: True when the real Windows printing stack is importable. Everything else
#: falls back to the simulation backend so the UI stays fully explorable.
try:  # pragma: no cover - platform dependent
    if IS_WINDOWS:
        import win32print  # noqa: F401

        HAS_WIN32 = True
    else:
        HAS_WIN32 = False
except Exception:  # pragma: no cover - missing pywin32
    HAS_WIN32 = False

#: Set GLASSPRINT_SIMULATE=1 to force the simulation backend on Windows too.
FORCE_SIMULATION = os.environ.get("GLASSPRINT_SIMULATE", "") not in ("", "0", "false", "False")

SIMULATED = FORCE_SIMULATION or not HAS_WIN32


def app_root() -> Path:
    """Directory that holds the bundled ``assets`` folder.

    PyInstaller onefile unpacks data next to ``sys._MEIPASS``; onedir and a
    plain source checkout both resolve relative to this file.
    """
    if IS_FROZEN:
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base) / "app"
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return app_root() / "assets"


def qml_dir() -> Path:
    return app_root() / "ui" / "qml"


def data_dir() -> Path:
    """Per-user writable directory for settings, history and logs."""
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / "GlassPrint"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "GlassPrint"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path
