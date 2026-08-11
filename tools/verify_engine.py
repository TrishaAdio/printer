"""End to end job checks against the simulation backend.

Exercises the parts of a job that have nothing to do with the operating system:
page selection, sheet planning, N-up cells, copy loops, manual two sided passes,
progress accounting and cancellation. With GLASSPRINT_DUMP=1 each simulated page
is also written out as a PNG so the composition can be eyeballed.

Run: GLASSPRINT_DUMP=1 python tools/verify_engine.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

os.environ.setdefault("GLASSPRINT_SIMULATE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.instance() or QGuiApplication(sys.argv)

    import make_test_pdf
    from PIL import Image

    from app.core import printers
    from app.core.options import PrintOptions
    from app.core.printing import engine, nup
    from app.core.printing.raster import Rect

    tmp = ROOT / ".verify"
    tmp.mkdir(exist_ok=True)
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
        if not ok:
            failures.append(label)

    printer = "HP Smart Tank 529 (Simulated)"
    caps = printers.capabilities(printer)

    pdf8 = str(tmp / "eight.pdf")
    make_test_pdf.build(pdf8, 8)
    photo = Image.new("RGB", (2000, 1400), (250, 240, 200))
    for x in range(0, 2000, 100):
        for y in range(1400):
            photo.putpixel((x, y), (30, 60, 180))
    photo_path = str(tmp / "wide.jpg")
    photo.save(photo_path, dpi=(300, 300))
    text_path = str(tmp / "notes.txt")
    Path(text_path).write_text(
        "\n".join(f"{i:04d}  the quick brown fox jumps over the lazy dog" for i in range(400)),
        encoding="utf-8",
    )

    class Recorder:
        def __init__(self, cancel_after: int = -1) -> None:
            self.events: list[tuple] = []
            self.notes: list[str] = []
            self.prompts: list[str] = []
            self.cancel_after = cancel_after
            self.count = 0

        def hooks(self) -> engine.Hooks:
            return engine.Hooks(
                on_progress=self.progress,
                on_note=self.notes.append,
                is_cancelled=self.cancelled,
                ask=self.ask,
            )

        def progress(self, done, total, phase, detail):
            self.events.append((done, total, phase, detail))
            if phase == "printing":
                self.count += 1

        def cancelled(self):
            return 0 <= self.cancel_after <= self.count

        def ask(self, title, message):
            self.prompts.append(message)
            return True

    def run(path, **kwargs):
        options = PrintOptions(printer=printer, **kwargs)
        rec = Recorder(kwargs.pop("_cancel_after", -1) if "_cancel_after" in kwargs else -1)
        return engine.print_file(path, options, rec.hooks(), caps), rec

    print("\nPDF jobs")
    result, rec = run(pdf8)
    check("8 page pdf prints 8 sheets",
          result.ok and result.sheets == 8 and result.pages == 8,
          f"{result.status} sheets={result.sheets} pages={result.pages} "
          f"{result.dpi}dpi in {result.duration:.2f}s")
    done, total, phase, _ = rec.events[-1]
    check("progress finishes at exactly 100 percent",
          done == total == 8 and phase == "done",
          f"{done}/{total} {phase}")
    monotonic = all(
        rec.events[i][0] <= rec.events[i + 1][0] for i in range(len(rec.events) - 1)
    )
    check("progress never goes backwards", monotonic, f"{len(rec.events)} updates")
    check("a spooler job id came back", result.spool_job_id > 0, str(result.spool_job_id))

    result, _ = run(pdf8, page_range="2-4,7")
    check("page range selects 4 pages", result.sheets == 4, f"sheets={result.sheets}")

    result, _ = run(pdf8, page_range="1-6", page_subset="odd")
    check("odd subset of 1-6 is 3 pages", result.sheets == 3, f"sheets={result.sheets}")

    result, _ = run(pdf8, copies=3)
    check("3 copies of 8 pages is 24 pages",
          result.pages == 24 and result.sheets == 8,
          f"pages={result.pages} sheets={result.sheets} (driver does the copies)")

    result, _ = run(pdf8, nup=4)
    check("4-up puts 8 pages on 2 sheets", result.sheets == 2, f"sheets={result.sheets}")

    result, _ = run(pdf8, nup=9)
    check("9-up puts 8 pages on 1 sheet", result.sheets == 1, f"sheets={result.sheets}")

    result, rec = run(pdf8, manual_duplex=True)
    check("manual duplex prints both passes", result.sheets == 8, f"sheets={result.sheets}")
    check("manual duplex asks the user to flip the stack",
          len(rec.prompts) == 1 and "flip" in rec.prompts[0].lower(),
          f"{len(rec.prompts)} prompt(s)")

    result, _ = run(pdf8, quality="hd")
    check("hd quality resolves to the printer maximum", result.dpi == 1200, f"{result.dpi} dpi")

    result, _ = run(pdf8, page_range="99-200")
    check("a range entirely past the end fails cleanly",
          not result.ok and "page range" in result.error.lower(),
          result.error)

    result, _ = run(pdf8, page_range="7-99")
    check("a range that overruns the end is clipped, not rejected",
          result.ok and result.sheets == 2,
          f"{result.status} sheets={result.sheets}")

    result, _ = run(pdf8, page_range="3,3,3,1")
    check("repeated pages are de-duplicated and ordered as written",
          result.ok and result.sheets == 2,
          f"{result.status} sheets={result.sheets}")

    result, _ = run(pdf8, page_range="not a range")
    check("nonsense page range fails cleanly", not result.ok, result.error)

    print("\nImage jobs")
    result, rec = run(photo_path)
    check("landscape photo prints one sheet", result.ok and result.sheets == 1,
          f"{result.status} sheets={result.sheets}")
    result, _ = run(photo_path, scale_mode="actual")
    check("actual size image job succeeds", result.ok, result.status)
    result, _ = run(photo_path, borderless=True, scale_mode="fill", quality="photo")
    check("borderless photo job succeeds", result.ok, f"{result.status} {result.dpi}dpi")
    result, _ = run(photo_path, copies=2, color=False, sharpen=True)
    check("monochrome sharpened copies succeed", result.ok and result.pages == 2,
          f"{result.status} pages={result.pages}")

    print("\nText jobs")
    result, _ = run(text_path)
    check("text file paginates and prints", result.ok and result.sheets >= 5,
          f"{result.status} sheets={result.sheets}")
    result, _ = run(text_path, nup=2)
    check("2-up text prints half the sheets", result.ok and result.sheets >= 3,
          f"{result.status} sheets={result.sheets}")

    print("\nCancellation and dry run")
    options = PrintOptions(printer=printer)
    rec = Recorder(cancel_after=3)
    result = engine.print_file(pdf8, options, rec.hooks(), caps)
    check("cancelling mid job reports cancelled",
          result.status == "cancelled" and result.sheets < 8,
          f"{result.status} after {result.sheets} sheets")

    result, _ = run(pdf8, dry_run=True)
    check("dry run renders without spooling",
          result.ok and result.sheets == 8 and result.spool_job_id == 0,
          f"{result.status} sheets={result.sheets} job={result.spool_job_id}")

    print("\nMissing and broken input")
    result, _ = run(str(tmp / "nope.pdf"))
    check("missing file fails cleanly", not result.ok and "exists" in result.error, result.error)
    broken = tmp / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 this is not a pdf")
    result, _ = run(str(broken))
    check("corrupt pdf fails cleanly", not result.ok and result.error, result.error)

    print("\nEstimates without printing")
    est = engine.estimate(pdf8, PrintOptions(printer=printer, nup=4, copies=2), caps)
    check("estimate matches what the job does",
          est["pages"] == 8 and est["sheets"] == 4,
          f"pages={est['pages']} sheets={est['sheets']}")

    print("\nN-up cell layout")
    avail = Rect(0, 0, 4811, 6866)
    for count in (1, 2, 4, 6, 9, 16):
        rects = nup.cells(count, avail, 24)
        overlap = False
        for i, a in enumerate(rects):
            for b in rects[i + 1 :]:
                if not (a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y):
                    overlap = True
        inside = all(
            r.x >= avail.x and r.y >= avail.y
            and r.right <= avail.right and r.bottom <= avail.bottom
            for r in rects
        )
        check(f"{count}-up cells: {len(rects)} cells, no overlap, inside page",
              len(rects) == count and not overlap and inside,
              f"first={rects[0].as_tuple()}")

    rects = nup.cells(4, Rect(0, 0, 1000, 1000), 0)
    covered = sum(r.w * r.h for r in rects)
    check("cells with no gutter tile the area exactly", covered == 1000 * 1000,
          f"{covered} of {1000 * 1000}")

    dump = Path(os.environ.get("APPDATA") or Path.home() / ".local/share")
    print(f"\nSimulated pages (if GLASSPRINT_DUMP=1): {dump}/GlassPrint/cache/simprint")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all engine checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
