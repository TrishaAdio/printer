"""Background job runner: one worker thread, a queue, and full batch control.

The runner owns a plain :class:`threading.Thread` rather than a ``QThread``.
Emitting a Qt signal from any thread is safe and delivers to the receiver's
thread, which is all the interaction we need, and it keeps the printing code
free of Qt object lifetime rules.

Batch behaviour worth knowing:

* Jobs run one at a time per printer, because the spooler serialises them anyway
  and interleaving two documents on one device produces interleaved paper.
* Pausing stops the runner picking up the *next* job; the sheet in progress
  finishes, because aborting mid document wastes a sheet.
* Failures never stop the batch. They are recorded and the run continues, which
  is the only sane behaviour when someone drops four hundred files in.
* The pending queue is persisted after every change, so a crash or a power cut
  during a long run does not lose the list.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from . import env, printers
from .history import history
from .logging_setup import get as get_logger
from .options import PrintOptions
from .printing import engine
from .util import Ticker, classify, human_size, new_id

log = get_logger("jobrunner")

QUEUE_FILE = "queue.json"

#: Statuses that mean "this job will not run again unless the user asks".
TERMINAL = ("done", "failed", "cancelled", "skipped")


@dataclass
class Job:
    id: str = field(default_factory=new_id)
    path: str = ""
    name: str = ""
    kind: str = ""
    size: int = 0
    pages: int = 0
    sheets: int = 0
    status: str = "pending"   # pending|running|done|failed|cancelled|skipped
    phase: str = ""           # rendering|printing|waiting|...
    detail: str = ""
    progress: float = 0.0     # 0..1 within this job
    error: str = ""
    printer: str = ""
    spool_job_id: int = 0
    dpi: int = 0
    duration: float = 0.0
    started: float = 0.0
    options: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, path: str, options: PrintOptions) -> Job:
        resolved = Path(path)
        try:
            size = resolved.stat().st_size
        except OSError:
            size = 0
        job = cls(
            path=str(resolved),
            name=resolved.name,
            kind=classify(path),
            size=size,
            printer=options.printer,
            options=options.to_dict(),
        )
        return job

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["size_text"] = human_size(self.size) if self.size else ""
        return data


class JobRunner(QObject):
    """Owns the queue and the worker thread."""

    jobsChanged = Signal()                       # the list itself changed
    jobUpdated = Signal(str, dict)               # id, job dict
    jobStarted = Signal(str)
    jobFinished = Signal(str, str, str)          # id, status, error
    overallChanged = Signal(int, int, float)     # done, total, eta seconds
    runningChanged = Signal(bool)
    pausedChanged = Signal(bool)
    note = Signal(str, str)                      # job id, text
    askFlip = Signal(str, str, str)              # job id, title, message
    batchFinished = Signal(int, int, int)        # done, failed, cancelled

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._jobs: list[Job] = []
        self._pending: deque[str] = deque()
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._paused = threading.Event()
        #: Cancellation is tracked per job id rather than with a global flag. A
        #: sticky "cancel everything" flag has to be cleared again at exactly the
        #: right moment, and getting that wrong silently cancels work queued
        #: afterwards, so the state simply does not exist.
        self._cancel_ids: set[str] = set()
        self._current: Job | None = None
        self._answer: dict[str, Any] = {}
        self._answer_event = threading.Event()
        self._ticker = Ticker()
        self._tally = {"done": 0, "failed": 0, "cancelled": 0}
        self._thread = threading.Thread(
            target=self._loop, name="GlassPrintWorker", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------ state

    @property
    def queue_path(self) -> Path:
        return env.data_dir() / QUEUE_FILE

    def jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.to_dict() for job in self._jobs]

    def job(self, job_id: str) -> Job | None:
        with self._lock:
            for item in self._jobs:
                if item.id == job_id:
                    return item
        return None

    @property
    def is_paused(self) -> bool:
        return self._paused.is_set()

    @property
    def is_running(self) -> bool:
        return self._current is not None

    def counts(self) -> dict[str, int]:
        with self._lock:
            out = {"total": len(self._jobs), "pending": 0, "running": 0,
                   "done": 0, "failed": 0, "cancelled": 0, "skipped": 0}
            for job in self._jobs:
                out[job.status] = out.get(job.status, 0) + 1
            return out

    # ------------------------------------------------------------------- add

    def add_paths(self, paths: list[str], options: PrintOptions) -> list[str]:
        """Queue files. Returns the ids created, in order."""
        created: list[str] = []
        with self._lock:
            existing = {os.path.normcase(job.path) for job in self._jobs
                        if job.status in ("pending", "running")}
            for path in paths:
                key = os.path.normcase(os.path.abspath(path))
                if key in existing:
                    continue
                job = Job.create(path, options)
                self._jobs.append(job)
                self._pending.append(job.id)
                existing.add(key)
                created.append(job.id)
        if created:
            self._persist()
            self.jobsChanged.emit()
            self._emit_overall()
            self._wake.set()
        return created

    def set_options(self, job_id: str, options: PrintOptions) -> None:
        job = self.job(job_id)
        if job is None or job.status == "running":
            return
        job.options = options.to_dict()
        job.printer = options.printer
        self._persist()
        self.jobUpdated.emit(job.id, job.to_dict())

    def set_options_all(self, options: PrintOptions) -> None:
        """Apply one set of options to every job not already running."""
        with self._lock:
            for job in self._jobs:
                if job.status == "pending":
                    job.options = options.to_dict()
                    job.printer = options.printer
        self._persist()
        self.jobsChanged.emit()

    # ---------------------------------------------------------------- remove

    def remove(self, job_id: str) -> None:
        with self._lock:
            job = next((j for j in self._jobs if j.id == job_id), None)
            if job is None:
                return
            if job.status == "running":
                self.cancel(job_id)
                return
            self._jobs = [j for j in self._jobs if j.id != job_id]
            with contextlib.suppress(ValueError):
                self._pending.remove(job_id)
        self._persist()
        self.jobsChanged.emit()
        self._emit_overall()

    def clear_finished(self) -> None:
        with self._lock:
            self._jobs = [j for j in self._jobs if j.status not in TERMINAL]
        self._persist()
        self.jobsChanged.emit()
        self._emit_overall()

    def clear_all(self) -> None:
        self.cancel_all()
        with self._lock:
            self._jobs = [j for j in self._jobs if j.status == "running"]
            self._pending.clear()
        self._persist()
        self.jobsChanged.emit()
        self._emit_overall()

    def move(self, job_id: str, delta: int) -> None:
        """Reorder a pending job. Only affects the pending order."""
        with self._lock:
            if job_id not in self._pending:
                return
            order = list(self._pending)
            index = order.index(job_id)
            target = max(0, min(len(order) - 1, index + delta))
            if target == index:
                return
            order.insert(target, order.pop(index))
            self._pending = deque(order)
            # Mirror the order into the visible list so the UI matches.
            position = {jid: i for i, jid in enumerate(order)}
            pending_jobs = [j for j in self._jobs if j.id in position]
            others = [j for j in self._jobs if j.id not in position]
            pending_jobs.sort(key=lambda j: position[j.id])
            self._jobs = others + pending_jobs
        self._persist()
        self.jobsChanged.emit()

    # --------------------------------------------------------------- control

    def pause(self) -> None:
        if not self._paused.is_set():
            self._paused.set()
            self.pausedChanged.emit(True)
            log.info("queue paused")

    def resume(self) -> None:
        if self._paused.is_set():
            self._paused.clear()
            self._wake.set()
            self.pausedChanged.emit(False)
            log.info("queue resumed")

    def toggle_pause(self) -> None:
        self.resume() if self._paused.is_set() else self.pause()

    def cancel(self, job_id: str) -> None:
        """Cancel a specific job, whether it is running or still pending."""
        with self._lock:
            self._cancel_ids.add(job_id)
            job = next((j for j in self._jobs if j.id == job_id), None)
            if job is not None and job.status == "pending":
                job.status = "cancelled"
                job.detail = "cancelled before it started"
                with contextlib.suppress(ValueError):
                    self._pending.remove(job_id)
                self._tally["cancelled"] += 1
                self.jobUpdated.emit(job.id, job.to_dict())
        self._persist()
        self._emit_overall()

    def cancel_all(self) -> None:
        with self._lock:
            pending = list(self._pending)
            self._pending.clear()
            for job in self._jobs:
                if job.id in pending:
                    job.status = "cancelled"
                    job.detail = "cancelled"
                    self._tally["cancelled"] += 1
            current = self._current
            if current is not None:
                self._cancel_ids.add(current.id)
        # Also stop the spooler side of whatever is already on the device.
        if current and current.spool_job_id:
            printers.cancel_job(current.printer, current.spool_job_id)
        self._persist()
        self.jobsChanged.emit()
        self._emit_overall()

    def retry(self, job_id: str) -> None:
        job = self.job(job_id)
        if job is None or job.status not in TERMINAL:
            return
        with self._lock:
            self._cancel_ids.discard(job_id)
            job.status = "pending"
            job.error = ""
            job.detail = ""
            job.phase = ""
            job.progress = 0.0
            job.spool_job_id = 0
            self._pending.append(job.id)
        self._persist()
        self.jobUpdated.emit(job.id, job.to_dict())
        self._emit_overall()
        self._wake.set()

    def retry_failed(self) -> None:
        with self._lock:
            failed = [j.id for j in self._jobs if j.status == "failed"]
        for job_id in failed:
            self.retry(job_id)

    def answer_flip(self, job_id: str, proceed: bool) -> None:
        self._answer = {"id": job_id, "proceed": bool(proceed)}
        self._answer_event.set()

    def shutdown(self, timeout: float = 3.0) -> None:
        self._stop.set()
        self._wake.set()
        self._answer_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout)

    # ------------------------------------------------------------ persistence

    def _persist(self) -> None:
        try:
            with self._lock:
                payload = [
                    {
                        "id": job.id, "path": job.path, "options": job.options,
                        "status": job.status,
                    }
                    for job in self._jobs
                    if job.status in ("pending", "running")
                ]
            tmp = self.queue_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
            os.replace(tmp, self.queue_path)
        except OSError as exc:
            log.debug("cannot persist queue: %s", exc)

    def restore(self) -> int:
        """Reload a queue left over from a previous run. Returns the count."""
        try:
            if not self.queue_path.exists():
                return 0
            payload = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("cannot restore queue: %s", exc)
            return 0

        restored = 0
        with self._lock:
            for entry in payload or []:
                path = entry.get("path") or ""
                if not path or not Path(path).exists():
                    continue
                options = PrintOptions.from_dict(entry.get("options"))
                job = Job.create(path, options)
                job.id = entry.get("id") or job.id
                self._jobs.append(job)
                self._pending.append(job.id)
                restored += 1
        if restored:
            log.info("restored %d queued job(s) from the previous session", restored)
            self.jobsChanged.emit()
            self._emit_overall()
        return restored

    # ---------------------------------------------------------------- worker

    def _emit_overall(self) -> None:
        counts = self.counts()
        finished = counts["done"] + counts["failed"] + counts["cancelled"] + counts["skipped"]
        total = counts["total"]
        remaining = max(0, total - finished)
        eta = self._ticker.eta(remaining) or 0.0
        self.overallChanged.emit(finished, total, eta)

    def _next_job(self) -> Job | None:
        with self._lock:
            while self._pending:
                job_id = self._pending.popleft()
                job = next((j for j in self._jobs if j.id == job_id), None)
                if job is None or job.status != "pending":
                    continue
                if job.id in self._cancel_ids:
                    job.status = "cancelled"
                    self.jobUpdated.emit(job.id, job.to_dict())
                    continue
                return job
        return None

    def _loop(self) -> None:
        log.info("worker thread started")
        while not self._stop.is_set():
            if self._paused.is_set():
                self._wake.wait(0.25)
                self._wake.clear()
                continue

            job = self._next_job()
            if job is None:
                if self._tally["done"] or self._tally["failed"] or self._tally["cancelled"]:
                    tally = dict(self._tally)
                    self._tally = {"done": 0, "failed": 0, "cancelled": 0}
                    self.batchFinished.emit(
                        tally["done"], tally["failed"], tally["cancelled"]
                    )
                self._wake.wait(0.3)
                self._wake.clear()
                continue

            self._run_job(job)

        log.info("worker thread stopped")

    def _run_job(self, job: Job) -> None:
        self._current = job
        job.status = "running"
        job.phase = "preparing"
        job.progress = 0.0
        job.started = time.time()
        self.runningChanged.emit(True)
        self.jobStarted.emit(job.id)
        self.jobUpdated.emit(job.id, job.to_dict())
        self._ticker.start_item()

        options = PrintOptions.from_dict(job.options)
        if not options.printer:
            options.printer = printers.pick_printer()
            job.printer = options.printer
        caps = printers.capabilities(options.printer)

        history.record_start(
            {
                "id": job.id, "started": job.started, "path": job.path,
                "name": job.name, "kind": job.kind, "printer": options.printer,
                "bytes": job.size, "copies": options.copies,
                "status": "printing", "options": job.options,
            }
        )

        def on_progress(done: int, total: int, phase: str, detail: str) -> None:
            job.phase = phase
            job.detail = detail
            job.progress = (done / total) if total else 0.0
            if job.sheets < done:
                job.sheets = done
            self.jobUpdated.emit(job.id, job.to_dict())

        def on_note(text: str) -> None:
            job.notes.append(text)
            self.note.emit(job.id, text)

        def is_cancelled() -> bool:
            return job.id in self._cancel_ids or self._stop.is_set()

        def ask(title: str, message: str) -> bool:
            self._answer = {}
            self._answer_event.clear()
            self.askFlip.emit(job.id, title, message)
            # Wait for the UI, but keep noticing cancellation and shutdown.
            while not self._answer_event.wait(0.2):
                if is_cancelled() or self._stop.is_set():
                    return False
            return bool(self._answer.get("proceed"))

        hooks = engine.Hooks(
            on_progress=on_progress, on_note=on_note,
            is_cancelled=is_cancelled, ask=ask,
        )

        result = engine.print_file(job.path, options, hooks, caps)

        job.status = result.status
        job.error = result.error
        job.sheets = result.sheets
        job.pages = result.pages
        job.dpi = result.dpi
        job.duration = result.duration
        job.spool_job_id = result.spool_job_id
        job.progress = 1.0 if result.ok else job.progress
        job.phase = ""
        job.detail = (
            f"{result.sheets} sheet{'s' if result.sheets != 1 else ''} in "
            f"{result.duration:.1f}s" if result.ok else result.error
        )
        for note in result.notes:
            if note not in job.notes:
                job.notes.append(note)

        history.record_finish(
            job.id, result.status, result.error,
            pages=result.pages, sheets=result.sheets, duration=result.duration,
        )

        self._tally[job.status] = self._tally.get(job.status, 0) + 1
        self._ticker.end_item()
        self._current = None
        self._cancel_ids.discard(job.id)

        self.jobUpdated.emit(job.id, job.to_dict())
        self.jobFinished.emit(job.id, job.status, job.error)
        self.runningChanged.emit(False)
        self._emit_overall()
        self._persist()
        log.info(
            "job %s finished: %s (%s sheets, %.1fs)%s",
            job.name, job.status, job.sheets, job.duration,
            f" - {job.error}" if job.error else "",
        )
