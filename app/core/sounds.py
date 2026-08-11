"""Interface sound effects.

Uses QtMultimedia's low latency ``QSoundEffect`` when it is available and falls
back to ``winsound`` otherwise. Either way, failing to play a sound never
interferes with printing, so every path here swallows its errors.
"""

from __future__ import annotations

import contextlib
import threading

from . import env
from .logging_setup import get as get_logger
from .settings import settings

log = get_logger("sounds")

#: Two instances of the sounds that can retrigger quickly, so a fast pointer
#: does not cut off the previous tick.
POOL_SIZES = {"hover": 3, "click": 3, "toast": 2, "drop": 2}

NAMES = ("intro", "hover", "click", "drop", "start", "complete", "error", "toast")


class SoundPlayer:
    def __init__(self) -> None:
        self._pools: dict[str, list[object]] = {}
        self._cursor: dict[str, int] = {}
        self._backend = "none"
        self._lock = threading.RLock()
        self._ready = False

    # ------------------------------------------------------------------ setup

    def preload(self) -> None:
        """Build the effect pool. Safe to call more than once."""
        if self._ready:
            return
        self._ready = True
        directory = env.assets_dir() / "sounds"
        if not directory.is_dir():
            log.warning("no sounds directory at %s", directory)
            return

        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
        except Exception as exc:
            log.info("QtMultimedia unavailable (%s), falling back", exc)
            self._backend = "winsound" if env.IS_WINDOWS else "none"
            return

        volume = float(settings.get("sound_volume", 0.55))
        for name in NAMES:
            path = directory / f"{name}.wav"
            if not path.exists():
                continue
            pool = []
            for _ in range(POOL_SIZES.get(name, 1)):
                try:
                    effect = QSoundEffect()
                    effect.setSource(QUrl.fromLocalFile(str(path)))
                    effect.setVolume(volume)
                    pool.append(effect)
                except Exception as exc:
                    log.debug("cannot prepare %s: %s", name, exc)
            if pool:
                self._pools[name] = pool
                self._cursor[name] = 0
        self._backend = "qt" if self._pools else ("winsound" if env.IS_WINDOWS else "none")
        log.info("sound backend: %s (%d effects)", self._backend, len(self._pools))

    def set_volume(self, volume: float) -> None:
        volume = max(0.0, min(1.0, float(volume)))
        with self._lock:
            for pool in self._pools.values():
                for effect in pool:
                    with contextlib.suppress(Exception):
                        effect.setVolume(volume)

    # ------------------------------------------------------------------- play

    def play(self, name: str, force: bool = False) -> None:
        if not force and not settings.get("sound_enabled", True):
            return
        if name == "intro" and not settings.get("intro_sound", True):
            return
        self.preload()

        if self._backend == "qt":
            self._play_qt(name)
        elif self._backend == "winsound":
            self._play_winsound(name)

    def _play_qt(self, name: str) -> None:
        with self._lock:
            pool = self._pools.get(name)
            if not pool:
                return
            index = self._cursor.get(name, 0)
            effect = pool[index % len(pool)]
            self._cursor[name] = (index + 1) % len(pool)
        try:
            # A freshly started effect that is still loading simply does nothing,
            # which is the right outcome for a hover tick.
            effect.play()
        except Exception as exc:
            log.debug("cannot play %s: %s", name, exc)

    def _play_winsound(self, name: str) -> None:
        path = env.assets_dir() / "sounds" / f"{name}.wav"
        if not path.exists():
            return

        def run() -> None:
            try:
                import winsound

                winsound.PlaySound(
                    str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
                )
            except Exception as exc:
                log.debug("winsound failed for %s: %s", name, exc)

        threading.Thread(target=run, name=f"sfx-{name}", daemon=True).start()

    def stop_all(self) -> None:
        with self._lock:
            for pool in self._pools.values():
                for effect in pool:
                    with contextlib.suppress(Exception):
                        effect.stop()


sounds = SoundPlayer()
