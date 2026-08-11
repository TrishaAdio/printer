"""Job runner checks: batching, ordering, pause, cancel, retry, persistence.

Runs the real runner against the simulation backend with a live Qt event loop so
the cross thread signal delivery is exercised the same way it will be in the app.

Run: python tools/verify_queue.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

os.environ.setdefault("GLASSPRINT_SIMULATE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

    QCoreApplication.instance() or QCoreApplication(sys.argv)

    import make_test_pdf

    from app.core import env
    from app.core.jobrunner import JobRunner
    from app.core.options import PrintOptions

    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
        if not ok:
            failures.append(label)

    tmp = ROOT / ".verify"
    tmp.mkdir(exist_ok=True)
    files = []
    for index in range(6):
        path = str(tmp / f"batch_{index + 1}.pdf")
        make_test_pdf.build(path, 2)
        files.append(path)

    printer = "HP Smart Tank 529 (Simulated)"
    options = PrintOptions(printer=printer)

    def wait_for(predicate, timeout=30.0, label=""):
        """Spin the event loop until predicate holds or we give up."""
        loop = QEventLoop()
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        poll = QTimer()
        poll.setInterval(20)
        poll.timeout.connect(lambda: loop.quit() if predicate() else None)
        deadline.start(int(timeout * 1000))
        poll.start()
        loop.exec()
        poll.stop()
        deadline.stop()
        return predicate()

    print("\nBatch run")
    # Start from a clean slate so a queue file from an earlier run cannot leak in.
    queue_file = env.data_dir() / "queue.json"
    if queue_file.exists():
        queue_file.unlink()

    runner = JobRunner()
    events: list[tuple] = []
    runner.jobFinished.connect(lambda i, s, e: events.append((i, s, e)))
    overall: list[tuple] = []
    runner.overallChanged.connect(lambda d, t, eta: overall.append((d, t, eta)))
    batch: list[tuple] = []
    runner.batchFinished.connect(lambda d, f, c: batch.append((d, f, c)))

    ids = runner.add_paths(files, options)
    check("six files queued", len(ids) == 6, f"{len(ids)} ids")
    check("duplicates are not queued twice",
          runner.add_paths([files[0]], options) == [],
          "re-adding the first file was ignored")

    ok = wait_for(lambda: len(events) == 6, 60)
    check("every job finished", ok and all(s == "done" for _, s, _ in events),
          f"{len(events)} finished: {[s for _, s, _ in events]}")
    counts = runner.counts()
    check("counts add up", counts["done"] == 6 and counts["pending"] == 0, str(counts))
    check("overall progress reached the end",
          bool(overall) and overall[-1][0] == overall[-1][1] == 6,
          str(overall[-1]) if overall else "no updates")
    check("an eta was produced during the run",
          any(eta > 0 for _, _, eta in overall), f"{len(overall)} updates")
    ok = wait_for(lambda: len(batch) == 1, 5)
    check("batch summary emitted once", ok and batch[0] == (6, 0, 0),
          str(batch[0]) if batch else "none")

    print("\nOrdering")
    runner.clear_all()
    ids = runner.add_paths(files, options)
    runner.pause()
    # Reorder while paused so nothing is running.
    last = ids[-1]
    for _ in range(5):
        runner.move(last, -1)
    order = [j["id"] for j in runner.jobs() if j["status"] == "pending"]
    check("a pending job can be moved to the front", order[0] == last,
          f"front is {order[0][:6]}, expected {last[:6]}")

    print("\nPause, cancel and retry")
    check("pausing is reported", runner.is_paused)
    before = runner.counts()["done"]
    ok = wait_for(lambda: runner.counts()["done"] > before, 2.0)
    check("nothing runs while paused", not ok, f"done stayed at {runner.counts()['done']}")

    runner.cancel(order[1])
    check("a pending job can be cancelled",
          any(j["id"] == order[1] and j["status"] == "cancelled" for j in runner.jobs()),
          "status is cancelled")

    runner.resume()
    check("resuming is reported", not runner.is_paused)
    ok = wait_for(lambda: runner.counts()["pending"] == 0 and not runner.is_running, 60)
    counts = runner.counts()
    check("the rest of the batch completed after resume",
          ok and counts["done"] == 5 and counts["cancelled"] == 1, str(counts))

    runner.retry(order[1])
    ok = wait_for(lambda: runner.counts()["done"] == 6, 30)
    check("a cancelled job can be retried", ok, str(runner.counts()))

    print("\nCancel everything mid batch")
    runner.clear_all()
    big = []
    for index in range(8):
        path = str(tmp / f"long_{index}.pdf")
        make_test_pdf.build(path, 6)
        big.append(path)
    runner.add_paths(big, options)
    wait_for(lambda: runner.is_running, 10)
    runner.cancel_all()
    ok = wait_for(lambda: not runner.is_running and runner.counts()["pending"] == 0, 30)
    counts = runner.counts()
    check("cancel all empties the queue",
          ok and counts["pending"] == 0 and counts["cancelled"] >= 7, str(counts))

    print("\nFailures do not stop the batch")
    runner.clear_all()
    broken = tmp / "not_really.pdf"
    broken.write_bytes(b"nonsense")
    mixed = [files[0], str(broken), files[1], str(tmp / "gone.pdf"), files[2]]
    runner.add_paths(mixed, options)
    ok = wait_for(lambda: runner.counts()["pending"] == 0 and not runner.is_running, 60)
    counts = runner.counts()
    check("good files still printed around the bad ones",
          ok and counts["done"] == 3 and counts["failed"] == 2, str(counts))
    failed_jobs = [j for j in runner.jobs() if j["status"] == "failed"]
    check("failures carry a readable reason",
          all(j["error"] for j in failed_jobs),
          "; ".join(j["error"] for j in failed_jobs))

    runner.retry_failed()
    ok = wait_for(lambda: runner.counts()["pending"] == 0 and not runner.is_running, 30)
    check("retrying failures re-runs only those", runner.counts()["failed"] == 2,
          str(runner.counts()))

    print("\nManual duplex prompt")
    runner.clear_all()
    prompts: list[tuple] = []

    def on_ask(job_id, title, message):
        prompts.append((job_id, title))
        runner.answer_flip(job_id, True)

    runner.askFlip.connect(on_ask)
    runner.add_paths([files[0]], PrintOptions(printer=printer, manual_duplex=True))
    ok = wait_for(lambda: runner.counts()["done"] == 1, 30)
    check("the flip prompt is raised and answered", ok and len(prompts) == 1,
          f"{len(prompts)} prompt(s), counts={runner.counts()}")

    print("\nPersistence")
    runner.clear_all()
    runner.pause()
    runner.add_paths(files[:4], options)
    saved = json.loads(queue_file.read_text(encoding="utf-8")) if queue_file.exists() else []
    check("pending jobs are written to disk", len(saved) == 4, f"{len(saved)} entries")
    runner.shutdown()

    fresh = JobRunner()
    fresh.pause()
    restored = fresh.restore()
    check("a queue survives a restart", restored == 4, f"{restored} restored")
    fresh.clear_all()
    fresh.shutdown()
    if queue_file.exists():
        queue_file.unlink()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all queue checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
