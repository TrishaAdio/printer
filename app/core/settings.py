"""User settings persisted as JSON in the per-user data directory.

Writes are atomic (temp file + replace) because a half-written settings file
that kills the app on next launch is a genuinely awful bug to ship.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from . import env
from .logging_setup import get as get_logger

log = get_logger("settings")

DEFAULTS: dict[str, Any] = {
    # Appearance
    "theme": "dark",
    "accent": "#5B8CFF",
    "accent2": "#B06BFF",
    "blur_strength": 0.85,
    "grain_opacity": 0.045,
    "desktop_blur": True,          # ask Windows to blur whatever is behind us
    "acrylic_mode": "blur",        # blur | acrylic | off  (Win10 acrylic can drag poorly)
    "animations": True,
    "reduce_motion": False,
    # Intro
    "intro_enabled": True,
    "intro_sound": True,
    # Audio
    "sound_enabled": True,
    "sound_volume": 0.55,
    # Behaviour
    "last_printer": "",
    "recursive_folders": True,
    "confirm_over_pages": 50,      # ask before a batch larger than this
    "history_days": 90,
    "restore_queue": True,
    "minimise_to_tray": False,
    "window_width": 1180,
    "window_height": 760,
    # Default print options, mirrored from PrintOptions field names
    "defaults": {
        "copies": 1,
        "collate": True,
        "color": True,
        "duplex": "simplex",
        "orientation": "auto",
        "paper_size": 0,
        "paper_source": 0,
        "media_type": 0,
        "quality": "normal",
        "render_dpi": 0,
        "scale_mode": "fit",
        "scale_percent": 100,
        "borderless": False,
        "extra_margin_mm": 0.0,
        "nup": 1,
        "page_subset": "all",
        "reverse": False,
        "auto_rotate": True,
        "sharpen": False,
        "separate_jobs": True,
        "manual_duplex": False,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Settings:
    def __init__(self) -> None:
        self._path = env.data_dir() / "settings.json"
        self._lock = threading.RLock()
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    @property
    def path(self):
        return self._path

    def load(self) -> None:
        with self._lock:
            if not self._path.exists():
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = _deep_merge(DEFAULTS, raw)
            except (OSError, ValueError) as exc:
                log.warning("settings unreadable, using defaults: %s", exc)
                self._data = dict(DEFAULTS)

    def save(self) -> None:
        with self._lock:
            tmp = self._path.with_suffix(".tmp")
            try:
                tmp.write_text(
                    json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                os.replace(tmp, self._path)
            except OSError as exc:
                log.warning("could not save settings: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if "." in key:
                node: Any = self._data
                for part in key.split("."):
                    if not isinstance(node, dict) or part not in node:
                        return default
                    node = node[part]
                return node
            return self._data.get(key, default)

    def set(self, key: str, value: Any, autosave: bool = True) -> None:
        with self._lock:
            if "." in key:
                parts = key.split(".")
                node = self._data
                for part in parts[:-1]:
                    node = node.setdefault(part, {})
                node[parts[-1]] = value
            else:
                self._data[key] = value
        if autosave:
            self.save()

    def defaults_dict(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data.get("defaults", {}))

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def reset(self) -> None:
        with self._lock:
            self._data = dict(DEFAULTS)
        self.save()


settings = Settings()
