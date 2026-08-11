"""The object QML talks to.

Everything the interface can do goes through one ``Backend`` instance exposed as
``app``. Keeping the surface in a single place means the QML never reaches into
the printing code, and the printing code never has to know a UI exists.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Property,
    QObject,
    QTimer,
    QUrl,
    Signal,
    Slot,
)

from . import APP_NAME, APP_VERSION
from .core import env, printers, testpage, win_effects
from .core.history import history
from .core.jobrunner import JobRunner
from .core.logging_setup import get as get_logger
from .core.options import NUP_CHOICES, PrintOptions
from .core.printing import engine
from .core.settings import settings
from .core.sounds import sounds
from .core.util import human_duration, iter_files
from .models import HistoryModel, QueueModel

log = get_logger("bridge")


class Backend(QObject):
    # ------------------------------------------------------------- signals
    printersChanged = Signal()
    printerChanged = Signal()
    capsChanged = Signal()
    optionsChanged = Signal()
    statusChanged = Signal()
    progressChanged = Signal()
    settingsChanged = Signal()
    toast = Signal(str, str)               # kind: info|good|warn|bad, message
    flipRequested = Signal(str, str, str)  # job id, title, message
    previewReady = Signal(str, str)        # source path, image url
    suggestPreview = Signal(str, str)      # path, name: show this one now
    previewFailed = Signal(str, str)
    batchDone = Signal(int, int, int)
    windowEffectChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._printers: list[dict[str, Any]] = []
        self._printer = ""
        self._caps: dict[str, Any] = {}
        self._options = PrintOptions.from_dict(settings.defaults_dict())
        self._window_effect = "off"
        self._preview_token = 0

        # These have to be declared properties, not plain attributes: QML can
        # only see a QObject's meta-object, so a bare Python attribute is
        # invisible to it and a bound ListView silently shows nothing.
        self._queue_model = QueueModel(self)
        self._history_model = HistoryModel(self)
        self.runner = JobRunner(self)

        self._done = 0
        self._total = 0
        self._eta = 0.0

        self._queue_model.bind(self.runner)
        self.runner.overallChanged.connect(self._on_overall)
        self.runner.pausedChanged.connect(lambda _: self.statusChanged.emit())
        self.runner.runningChanged.connect(lambda _: self.statusChanged.emit())
        self.runner.jobsChanged.connect(self.statusChanged.emit)
        self.runner.jobFinished.connect(self._on_job_finished)
        self.runner.note.connect(lambda _job, text: self.toast.emit("warn", text))
        self.runner.askFlip.connect(self.flipRequested.emit)
        self.runner.batchFinished.connect(self._on_batch_finished)

        self.refreshPrinters()
        self._history_model.refresh()

        # Printer state changes outside the app (paper out, paused, unplugged),
        # so it is polled rather than assumed.
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(4000)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start()

        pruned = history.prune(int(settings.get("history_days", 90) or 0))
        if pruned:
            log.info("pruned %d old history entries", pruned)

    # ============================================================ properties

    @Property(QObject, constant=True)
    def queue(self) -> QObject:
        return self._queue_model

    @Property(QObject, constant=True)
    def history(self) -> QObject:
        return self._history_model

    @Property(str, constant=True)
    def appName(self) -> str:
        return APP_NAME

    @Property(str, constant=True)
    def version(self) -> str:
        return APP_VERSION

    @Property(bool, constant=True)
    def simulated(self) -> bool:
        return printers.IS_SIMULATED

    @Property(str, constant=True)
    def platformNote(self) -> str:
        if printers.IS_SIMULATED:
            return "Simulation mode: no paper will move"
        return win_effects.describe()

    @Property("QVariantList", notify=printersChanged)
    def printerList(self) -> list[dict[str, Any]]:
        return self._printers

    @Property("QStringList", notify=printersChanged)
    def printerNames(self) -> list[str]:
        return [p["name"] for p in self._printers]

    @Property(str, notify=printerChanged)
    def printer(self) -> str:
        return self._printer

    @printer.setter
    def printer(self, name: str) -> None:
        self.selectPrinter(name)

    @Property(int, notify=printerChanged)
    def printerIndex(self) -> int:
        for index, item in enumerate(self._printers):
            if item["name"] == self._printer:
                return index
        return -1

    @Property("QVariantMap", notify=capsChanged)
    def caps(self) -> dict[str, Any]:
        return self._caps

    @Property("QVariantMap", notify=optionsChanged)
    def options(self) -> dict[str, Any]:
        return self._options.to_dict()

    @Property("QVariantList", constant=True)
    def nupChoices(self) -> list[int]:
        return list(NUP_CHOICES)

    @Property(int, notify=optionsChanged)
    def effectiveDpi(self) -> int:
        caps = printers.capabilities(self._printer) if self._printer else None
        return self._options.effective_dpi(caps)

    @Property(str, notify=statusChanged)
    def printerStatus(self) -> str:
        for item in self._printers:
            if item["name"] == self._printer:
                return item.get("status", "ready")
        return "offline"

    @Property(str, notify=statusChanged)
    def printerStatusText(self) -> str:
        for item in self._printers:
            if item["name"] == self._printer:
                return item.get("status_text", "")
        return "No printer selected"

    @Property(bool, notify=statusChanged)
    def paused(self) -> bool:
        return self.runner.is_paused

    @Property(bool, notify=statusChanged)
    def running(self) -> bool:
        return self.runner.is_running

    @Property("QVariantMap", notify=statusChanged)
    def counts(self) -> dict[str, int]:
        return self.runner.counts()

    @Property(float, notify=progressChanged)
    def overall(self) -> float:
        return (self._done / self._total) if self._total else 0.0

    @Property(str, notify=progressChanged)
    def progressText(self) -> str:
        if not self._total:
            return "Nothing queued"
        if self._done >= self._total:
            return f"{self._total} of {self._total} finished"
        text = f"{self._done} of {self._total} finished"
        if self._eta > 0.5:
            text += f"  |  about {human_duration(self._eta)} left"
        return text

    @Property(str, notify=statusChanged)
    def queueSummary(self) -> str:
        counts = self.runner.counts()
        if not counts["total"]:
            return "Drop files anywhere to begin"
        parts = []
        for key, label in (
            ("pending", "waiting"), ("running", "printing"), ("done", "printed"),
            ("failed", "failed"), ("cancelled", "cancelled"),
        ):
            if counts.get(key):
                parts.append(f"{counts[key]} {label}")
        return "  |  ".join(parts)

    @Property(str, notify=windowEffectChanged)
    def windowEffect(self) -> str:
        return self._window_effect

    # =============================================================== printers

    @Slot()
    def refreshPrinters(self) -> None:
        printers.invalidate()
        snapshot = printers.snapshot()
        self._printers = snapshot["printers"]
        wanted = self._printer or settings.get("last_printer", "") or ""
        chosen = printers.pick_printer(wanted)
        self.printersChanged.emit()
        if chosen != self._printer:
            self.selectPrinter(chosen)
        else:
            self._reload_caps()
        self.statusChanged.emit()

    @Slot(str)
    def selectPrinter(self, name: str) -> None:
        if not name or name == self._printer:
            return
        self._printer = name
        self._options.printer = name
        settings.set("last_printer", name)
        self._reload_caps()
        self.printerChanged.emit()
        self.optionsChanged.emit()
        self.statusChanged.emit()

    @Slot(int)
    def selectPrinterIndex(self, index: int) -> None:
        if 0 <= index < len(self._printers):
            self.selectPrinter(self._printers[index]["name"])

    def _reload_caps(self) -> None:
        if not self._printer:
            self._caps = {}
            self.capsChanged.emit()
            return
        try:
            caps = printers.capabilities(self._printer)
        except Exception as exc:
            # Belt as well as braces: printers.capabilities already degrades
            # rather than raising, but the interface must come up regardless.
            log.exception("capability reload failed")
            self._caps = {}
            self.capsChanged.emit()
            self.toast.emit("bad", f"Could not read the printer's settings: {exc}")
            return
        self._caps = caps.to_dict()
        notes = self._options.constrain_to(caps)
        self.capsChanged.emit()
        self.optionsChanged.emit()
        for note in notes:
            self.toast.emit("warn", note)

    @Slot()
    def makeDefaultPrinter(self) -> None:
        if printers.set_default_printer(self._printer):
            self.toast.emit("good", f"{self._printer} is now the Windows default")
            self.refreshPrinters()
        else:
            self.toast.emit("bad", "Windows would not change the default printer")

    @Slot()
    def openDriverProperties(self) -> None:
        """Open the vendor's own property sheet and adopt what the user chose."""
        if printers.IS_SIMULATED:
            self.toast.emit("warn", "The driver dialog needs a real printer")
            return
        window = self.parent()
        handle = 0
        try:
            handle = int(window.winId()) if hasattr(window, "winId") else 0
        except Exception:
            handle = 0
        devmode = printers.show_driver_dialog(
            self._printer, handle, printers.get_override(self._printer)
        )
        if devmode is None:
            return
        printers.set_override(self._printer, devmode)
        summary = printers.devmode_summary(devmode)
        for key, value in summary.items():
            if hasattr(self._options, key):
                setattr(self._options, key, value)
        self._options.normalise()
        self.optionsChanged.emit()
        self.toast.emit("good", "Driver settings applied to this printer")

    @Slot()
    def clearDriverOverride(self) -> None:
        printers.clear_override(self._printer)
        self.toast.emit("info", "Reverted to the driver defaults")

    @Slot()
    def openWindowsQueue(self) -> None:
        if not printers.open_printer_folder(self._printer):
            self.toast.emit("warn", "Could not open the Windows print queue")

    @Slot()
    def pausePrinter(self) -> None:
        if printers.pause_printer(self._printer):
            self.toast.emit("info", f"{self._printer} paused in Windows")
            self._poll_status()

    @Slot()
    def resumePrinter(self) -> None:
        if printers.resume_printer(self._printer):
            self.toast.emit("info", f"{self._printer} resumed")
            self._poll_status()

    @Slot()
    def purgePrinter(self) -> None:
        if printers.purge_printer(self._printer):
            self.toast.emit("info", "Windows queue cleared for this printer")
            self._poll_status()

    def _poll_status(self) -> None:
        if not self._printer:
            return
        state = printers.printer_status(self._printer)
        changed = False
        for item in self._printers:
            if item["name"] == self._printer:
                if (item.get("status") != state.get("status")
                        or item.get("status_text") != state.get("status_text")):
                    item.update(state)
                    changed = True
                break
        if changed:
            self.statusChanged.emit()

    # ================================================================ options

    @Slot(str, "QVariant")
    def setOption(self, key: str, value: Any) -> None:
        if not hasattr(self._options, key):
            log.debug("unknown option %s", key)
            return
        current = getattr(self._options, key)
        if isinstance(current, bool):
            value = bool(value)
        elif isinstance(current, int) and not isinstance(current, bool):
            try:
                value = int(value)
            except (TypeError, ValueError):
                return
        elif isinstance(current, float):
            try:
                value = float(value)
            except (TypeError, ValueError):
                return
        else:
            value = "" if value is None else str(value)
        setattr(self._options, key, value)
        self._options.normalise()

        if self._printer:
            caps = printers.capabilities(self._printer)
            for note in self._options.constrain_to(caps):
                self.toast.emit("warn", note)

        stored = settings.defaults_dict()
        if key in stored:
            settings.set(f"defaults.{key}", getattr(self._options, key))
        self.optionsChanged.emit()

    @Slot()
    def resetOptions(self) -> None:
        from .core.settings import DEFAULTS

        self._options = PrintOptions.from_dict(dict(DEFAULTS["defaults"]))
        self._options.printer = self._printer
        for key, value in DEFAULTS["defaults"].items():
            settings.set(f"defaults.{key}", value, autosave=False)
        settings.save()
        self.optionsChanged.emit()
        self.toast.emit("info", "Print options reset")

    @Slot()
    def applyOptionsToQueue(self) -> None:
        self.runner.set_options_all(self._options)
        self.toast.emit("good", "Options applied to every waiting job")

    # ================================================================== queue

    @Slot("QVariantList")
    def addUrls(self, urls: list[Any]) -> None:
        paths: list[str] = []
        for item in urls:
            try:
                url = item if isinstance(item, QUrl) else QUrl(str(item))
                local = url.toLocalFile() if url.isLocalFile() else str(item)
            except Exception:
                local = str(item)
            if local:
                paths.append(local)
        self.addPaths(paths)

    @Slot("QStringList")
    def addPaths(self, paths: list[str]) -> None:
        if not paths:
            return
        recursive = bool(settings.get("recursive_folders", True))
        expanded = iter_files(paths, recursive)
        if not expanded:
            self.toast.emit("warn", "Nothing printable in what you dropped")
            sounds.play("error")
            return

        skipped = 0
        from .core.util import SUPPORTED_EXTS

        usable = []
        for path in expanded:
            if Path(path).suffix.lower() in SUPPORTED_EXTS:
                usable.append(path)
            else:
                skipped += 1

        self._options.printer = self._printer
        created = self.runner.add_paths(usable, self._options)
        sounds.play("drop")
        if created:
            self.toast.emit(
                "good",
                f"Added {len(created)} file{'s' if len(created) != 1 else ''}"
                + (f", skipped {skipped} unsupported" if skipped else ""),
            )
            self._estimate_async(created)
            # Put the first of the batch on screen without waiting to be asked:
            # seeing the page appear is the confirmation that a drop landed.
            first = self.runner.job(created[0])
            if first is not None:
                self.suggestPreview.emit(first.path, first.name)
        else:
            self.toast.emit("info", "Those files are already queued")

    def _estimate_async(self, job_ids: list[str]) -> None:
        """Fill in page counts in the background so a big drop stays responsive."""

        def run() -> None:
            caps = printers.capabilities(self._printer) if self._printer else None
            for job_id in job_ids:
                job = self.runner.job(job_id)
                if job is None:
                    continue
                try:
                    options = PrintOptions.from_dict(job.options)
                    info = engine.estimate(job.path, options, caps)
                    job.pages = int(info.get("pages") or 0)
                    job.sheets = int(info.get("sheets") or 0)
                    if info.get("error") and job.status == "pending":
                        job.detail = info["error"]
                    self.runner.jobUpdated.emit(job.id, job.to_dict())
                except Exception as exc:
                    log.debug("estimate failed for %s: %s", job_id, exc)

        threading.Thread(target=run, name="estimator", daemon=True).start()

    @Slot()
    def start(self) -> None:
        counts = self.runner.counts()
        if not counts["pending"] and not counts["running"]:
            self.toast.emit("warn", "Add some files first")
            return
        if self.runner.is_paused:
            self.runner.resume()
        sounds.play("start")
        self.toast.emit("info", f"Printing {counts['pending']} job(s)")

    @Slot()
    def togglePause(self) -> None:
        self.runner.toggle_pause()
        sounds.play("click")

    @Slot(str)
    def cancelJob(self, job_id: str) -> None:
        self.runner.cancel(job_id)

    @Slot()
    def cancelAll(self) -> None:
        self.runner.cancel_all()
        self.toast.emit("warn", "Queue cancelled")

    @Slot(str)
    def retryJob(self, job_id: str) -> None:
        self.runner.retry(job_id)

    @Slot()
    def retryFailed(self) -> None:
        self.runner.retry_failed()

    @Slot(str)
    def removeJob(self, job_id: str) -> None:
        self.runner.remove(job_id)

    @Slot()
    def clearFinished(self) -> None:
        self.runner.clear_finished()

    @Slot()
    def clearQueue(self) -> None:
        self.runner.clear_all()

    @Slot(str, int)
    def moveJob(self, job_id: str, delta: int) -> None:
        self.runner.move(job_id, delta)

    @Slot(str, bool)
    def answerFlip(self, job_id: str, proceed: bool) -> None:
        self.runner.answer_flip(job_id, proceed)

    @Slot()
    def printTestPage(self) -> None:
        try:
            path = testpage.build_for(self._printer)
        except Exception as exc:
            self.toast.emit("bad", f"Could not build the test page: {exc}")
            return
        options = self._options.copy()
        options.printer = self._printer
        options.scale_mode = "fit"
        options.nup = 1
        options.copies = 1
        options.page_range = ""
        options.manual_duplex = False
        options.duplex = "simplex"
        self.runner.add_paths([path], options)
        self.toast.emit("info", "Test page queued")

    # ================================================================ preview

    @Slot(str)
    def requestPreview(self, path: str) -> None:
        if not path:
            return
        self._preview_token += 1
        token = self._preview_token
        cache = env.cache_dir() / "previews"
        cache.mkdir(parents=True, exist_ok=True)

        def run() -> None:
            try:
                stat = os.stat(path)
                stamp = f"{int(stat.st_mtime)}_{stat.st_size}"
            except OSError:
                stamp = str(int(time.time()))
            safe = "".join(c if c.isalnum() else "_" for c in Path(path).name)[:60]
            out = cache / f"{safe}_{stamp}.png"
            try:
                if not out.exists() and not engine.make_thumbnail(path, str(out), 1000):
                    raise RuntimeError("no preview for this file type")
                if token == self._preview_token:
                    self.previewReady.emit(path, QUrl.fromLocalFile(str(out)).toString())
            except Exception as exc:
                if token == self._preview_token:
                    self.previewFailed.emit(path, str(exc))

        threading.Thread(target=run, name="preview", daemon=True).start()

    # ================================================================ history

    @Slot(str, str)
    def refreshHistory(self, search: str = "", status: str = "all") -> None:
        self._history_model.refresh(search, status)

    @Slot(str)
    def deleteHistory(self, job_id: str) -> None:
        history.delete(job_id)
        self._history_model.refresh()

    @Slot()
    def clearHistory(self) -> None:
        history.clear()
        self._history_model.refresh()
        self.toast.emit("info", "History cleared")

    @Slot(str)
    def reprint(self, job_id: str) -> None:
        for row in self._history_model.rows():
            if row.get("id") != job_id:
                continue
            path = row.get("path") or ""
            if not path or not Path(path).exists():
                self.toast.emit("bad", "That file is no longer on disk")
                sounds.play("error")
                return
            options = PrintOptions.from_dict(row.get("options") or {})
            if not printers.has_printer(options.printer):
                options.printer = self._printer
            self.runner.add_paths([path], options)
            self.toast.emit("good", f"Queued {Path(path).name} with its original settings")
            return
        self.toast.emit("warn", "That history entry has gone")

    @Property("QVariantMap", notify=statusChanged)
    def historyStats(self) -> dict[str, Any]:
        return history.stats()

    # =============================================================== settings

    @Slot(str, result="QVariant")
    def getSetting(self, key: str) -> Any:
        return settings.get(key)

    @Slot(str, "QVariant")
    def setSetting(self, key: str, value: Any) -> None:
        settings.set(key, value)
        if key == "sound_volume":
            sounds.set_volume(float(value))
        if key in ("acrylic_mode", "desktop_blur", "accent", "theme"):
            self.applyWindowEffects()
        self.settingsChanged.emit()

    @Slot(result="QVariantMap")
    def allSettings(self) -> dict[str, Any]:
        return settings.as_dict()

    @Slot()
    def resetSettings(self) -> None:
        settings.reset()
        self.settingsChanged.emit()
        self.applyWindowEffects()
        self.toast.emit("info", "Settings reset")

    @Slot(str)
    def playSound(self, name: str) -> None:
        sounds.play(name)

    @Slot()
    def applyWindowEffects(self) -> None:
        window = self.parent()
        if window is None or not hasattr(window, "winId"):
            return
        mode = "off"
        if settings.get("desktop_blur", True):
            mode = str(settings.get("acrylic_mode", "blur"))
        tint = "#0B0D14" if settings.get("theme", "dark") == "dark" else "#F3F5FB"
        alpha = 170 if settings.get("theme", "dark") == "dark" else 190
        applied = win_effects.prepare_window(window, mode, tint, alpha)
        if applied != self._window_effect:
            self._window_effect = applied
            self.windowEffectChanged.emit()

    @Slot(str)
    def openPath(self, path: str) -> None:
        """Reveal a file in Explorer, or open the folder if it is one."""
        from PySide6.QtGui import QDesktopServices

        target = Path(path)
        if not target.exists():
            self.toast.emit("warn", "That file is no longer there")
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(target if target.is_dir() else target.parent))
        )

    @Slot()
    def openLogFolder(self) -> None:
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(env.log_dir())))

    @Slot()
    def shutdown(self) -> None:
        self._status_timer.stop()
        self.runner.shutdown()
        settings.save()

    # ================================================================ private

    def _on_overall(self, done: int, total: int, eta: float) -> None:
        self._done, self._total, self._eta = done, total, eta
        self.progressChanged.emit()

    def _on_job_finished(self, job_id: str, status: str, error: str) -> None:
        job = self.runner.job(job_id)
        name = job.name if job else "job"
        if status == "done":
            sounds.play("complete")
        elif status == "failed":
            sounds.play("error")
            self.toast.emit("bad", f"{name}: {error}")
        self._history_model.refresh()
        self.statusChanged.emit()

    def _on_batch_finished(self, done: int, failed: int, cancelled: int) -> None:
        self.batchDone.emit(done, failed, cancelled)
        if failed:
            self.toast.emit(
                "warn", f"Batch finished: {done} printed, {failed} failed"
            )
        elif done:
            self.toast.emit("good", f"All done: {done} job{'s' if done != 1 else ''} printed")
