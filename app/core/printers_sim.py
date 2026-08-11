"""Simulation backend.

Purpose is twofold. It lets the whole interface be developed and exercised on a
machine with no printers at all, and it gives users a safe way to try a large
batch without burning paper. Set ``GLASSPRINT_DUMP=1`` and every simulated page
is written to the cache directory as a PNG, which doubles as a rendering test.

The API mirrors :mod:`printers_win` exactly, member for member.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterator
from typing import Any

from . import env
from .geometry import PageGeometry
from .logging_setup import get as get_logger
from .options import Capabilities, NamedId, Paper, PrinterInfo, PrintOptions, Resolution

log = get_logger("printers.sim")

DUMP_PAGES = os.environ.get("GLASSPRINT_DUMP", "") not in ("", "0", "false", "False")

A4 = Paper(id=9, name="A4", width_mm=210.0, height_mm=297.0)
LETTER = Paper(id=1, name="Letter", width_mm=215.9, height_mm=279.4)
LEGAL = Paper(id=5, name="Legal", width_mm=215.9, height_mm=355.6)
A5 = Paper(id=11, name="A5", width_mm=148.0, height_mm=210.0)
A6 = Paper(id=70, name="A6", width_mm=105.0, height_mm=148.0)
PHOTO_4X6 = Paper(id=259, name="4 x 6 in", width_mm=101.6, height_mm=152.4)
ENVELOPE = Paper(id=20, name="Envelope #10", width_mm=104.8, height_mm=241.3)

_SIM_PRINTERS: dict[str, dict[str, Any]] = {
    "HP Smart Tank 529 (Simulated)": {
        "driver": "HP Smart Tank 520 series",
        "port": "USB001",
        "color": True,
        "duplex": False,
        "resolutions": [(300, 300), (600, 600), (1200, 1200)],
        "papers": [A4, LETTER, LEGAL, A5, A6, PHOTO_4X6, ENVELOPE],
        "bins": [
            NamedId(1, "Automatically Select"),
            NamedId(7, "Main Tray"),
            NamedId(4, "Manual Feed"),
        ],
        "media": [
            NamedId(1, "Plain Paper"),
            NamedId(258, "HP Advanced Photo Paper"),
            NamedId(259, "HP Brochure Glossy"),
            NamedId(260, "Matte Presentation"),
        ],
        "max_copies": 99,
        "ppm": 12,
        "virtual": False,
        "default_paper": 9,
    },
    "Office Laser Duplex (Simulated)": {
        "driver": "Generic PCL6",
        "port": "192.168.1.40",
        "color": False,
        "duplex": True,
        "resolutions": [(300, 300), (600, 600), (1200, 1200)],
        "papers": [A4, LETTER, LEGAL, A5],
        "bins": [NamedId(1, "Auto Select"), NamedId(7, "Tray 1"), NamedId(8, "Tray 2")],
        "media": [NamedId(1, "Plain"), NamedId(3, "Transparency"), NamedId(261, "Heavy")],
        "max_copies": 999,
        "ppm": 38,
        "virtual": False,
        "default_paper": 9,
    },
    "Print to PNG (Simulated)": {
        "driver": "GlassPrint Virtual",
        "port": "FILE:",
        "color": True,
        "duplex": False,
        "resolutions": [(300, 300), (600, 600)],
        "papers": [A4, LETTER],
        "bins": [NamedId(1, "Auto Select")],
        "media": [NamedId(1, "Plain")],
        "max_copies": 1,
        "ppm": 0,
        "virtual": True,
        "default_paper": 9,
    },
}

_default = "HP Smart Tank 529 (Simulated)"
_job_counter = [1000]
_queues: dict[str, list[dict[str, Any]]] = {}


def default_printer() -> str:
    return _default


def set_default_printer(name: str) -> bool:
    global _default
    if name in _SIM_PRINTERS:
        _default = name
        return True
    return False


def list_printers() -> list[PrinterInfo]:
    out = []
    for name, spec in _SIM_PRINTERS.items():
        jobs = len(_queues.get(name, []))
        out.append(
            PrinterInfo(
                name=name,
                driver=spec["driver"],
                port=spec["port"],
                comment="Simulation backend - no paper will move",
                is_default=(name == _default),
                status="busy" if jobs else "ready",
                status_text=f"Printing {jobs} job{'s' if jobs != 1 else ''}" if jobs else "Ready",
                jobs=jobs,
                is_virtual=spec["virtual"],
            )
        )
    out.sort(key=lambda p: (not p.is_default, p.is_virtual, p.name.lower()))
    return out


def printer_status(name: str) -> dict[str, Any]:
    jobs = len(_queues.get(name, []))
    if name not in _SIM_PRINTERS:
        return {"status": "offline", "status_text": "Not installed", "jobs": 0}
    return {
        "status": "busy" if jobs else "ready",
        "status_text": f"Printing {jobs} job{'s' if jobs != 1 else ''}" if jobs else "Ready",
        "jobs": jobs,
        "status_flags": 0,
    }


def capabilities(name: str) -> Capabilities:
    spec = _SIM_PRINTERS.get(name)
    if spec is None:
        return Capabilities(printer=name, notes=["Printer not found in simulation"])
    caps = Capabilities(
        printer=name,
        driver=spec["driver"],
        port=spec["port"],
        manufacturer="Simulated",
        model=spec["driver"],
        color=spec["color"],
        max_copies=spec["max_copies"],
        collate=True,
        duplex=spec["duplex"],
        staple=False,
        landscape=True,
        print_rate_ppm=spec["ppm"],
        papers=list(spec["papers"]),
        bins=list(spec["bins"]),
        media_types=list(spec["media"]),
        resolutions=[Resolution(x, y) for x, y in spec["resolutions"]],
        media_ready=[spec["papers"][0].name],
        default_paper=spec["default_paper"],
        default_bin=spec["bins"][0].id,
        default_media=spec["media"][0].id,
        default_dpi=300,
        max_dpi=max(x for x, _ in spec["resolutions"]),
        is_virtual=spec["virtual"],
        notes=["Simulation backend: output is discarded"
               + (", pages dumped to cache" if DUMP_PAGES else "")],
    )
    return caps


def base_devmode(name: str):
    return {"printer": name}


def build_devmode(name, options: PrintOptions, caps=None, dpi=None, override=None):
    caps = caps or capabilities(name)
    return {
        "printer": name,
        "dpi": int(dpi or options.effective_dpi(caps)),
        "paper_size": options.paper_size or caps.default_paper,
        "color": options.color and caps.color,
        "duplex": options.duplex if caps.duplex else "simplex",
        "orientation": options.orientation,
        "copies": min(options.copies, caps.max_copies),
    }


def show_driver_dialog(name: str, hwnd: int = 0, current=None):
    log.info("driver dialog requested for %s (unavailable in simulation)", name)
    return None


def devmode_summary(devmode) -> dict[str, Any]:
    if not isinstance(devmode, dict):
        return {}
    return {k: v for k, v in devmode.items() if k not in ("printer", "dpi")}


class PrinterDC:
    """Discards ink, keeps the geometry honest."""

    def __init__(self, printer: str, devmode=None) -> None:
        self.printer = printer
        self.job_id = 0
        self.geometry = PageGeometry()
        self._page_index = 0
        self._dump_dir = None
        self._font_size = 10.0
        self._font_family = "Consolas"
        self._page = None

        caps = capabilities(printer)
        dpi = 300
        paper_id = caps.default_paper
        if isinstance(devmode, dict):
            dpi = int(devmode.get("dpi") or 300)
            paper_id = int(devmode.get("paper_size") or paper_id)
        paper = caps.paper_by_id(paper_id) or A4

        landscape = isinstance(devmode, dict) and devmode.get("orientation") == "landscape"
        width_mm, height_mm = paper.width_mm, paper.height_mm
        if landscape:
            width_mm, height_mm = height_mm, width_mm

        geo = self.geometry
        geo.dpi_x = geo.dpi_y = dpi
        geo.physical_w = int(round(width_mm / 25.4 * dpi))
        geo.physical_h = int(round(height_mm / 25.4 * dpi))
        # 3.2 mm unprintable border, which is close to a real ink tank printer.
        margin = int(round(3.2 / 25.4 * dpi))
        geo.offset_x = geo.offset_y = margin
        geo.printable_w = geo.physical_w - 2 * margin
        geo.printable_h = geo.physical_h - 2 * margin
        geo.bpp = 24

    @property
    def hdc(self) -> int:
        return 0

    def start_doc(self, title: str) -> int:
        _job_counter[0] += 1
        self.job_id = _job_counter[0]
        _queues.setdefault(self.printer, []).append(
            {
                "id": self.job_id,
                "document": title,
                "user": "simulation",
                "status_flags": 0x10,
                "status": "printing",
                "pages": 0,
                "printed": 0,
            }
        )
        if DUMP_PAGES:
            self._dump_dir = env.cache_dir() / "simprint" / f"job{self.job_id}"
            self._dump_dir.mkdir(parents=True, exist_ok=True)
        log.info("simulated job %s started on %s (%s)", self.job_id, self.printer, title)
        return self.job_id

    def start_page(self) -> None:
        self._page_index += 1
        if DUMP_PAGES:
            from PIL import Image

            self._page = Image.new(
                "RGB", (self.geometry.physical_w, self.geometry.physical_h), "white"
            )
        # Simulated printers still take time, which keeps the progress UI honest.
        time.sleep(0.02)

    def end_page(self) -> None:
        if DUMP_PAGES and self._page is not None and self._dump_dir is not None:
            out = self._dump_dir / f"page_{self._page_index:04d}.png"
            try:
                preview = self._page
                if preview.width > 1400:
                    ratio = 1400 / preview.width
                    preview = preview.resize(
                        (1400, max(1, int(preview.height * ratio)))
                    )
                preview.save(out)
            except Exception as exc:
                log.warning("cannot dump page: %s", exc)
        self._page = None
        for job in _queues.get(self.printer, []):
            if job["id"] == self.job_id:
                job["printed"] = self._page_index
                job["pages"] = max(job["pages"], self._page_index)

    def end_doc(self) -> None:
        queue = _queues.get(self.printer, [])
        _queues[self.printer] = [job for job in queue if job["id"] != self.job_id]
        log.info("simulated job %s finished (%s pages)", self.job_id, self._page_index)

    def abort(self) -> None:
        self.end_doc()

    def close(self) -> None:
        self._page = None

    # -- drawing ---------------------------------------------------------

    def blit(self, image, x: int, y: int) -> None:
        if self._page is not None:
            try:
                self._page.paste(image.convert("RGB"), (int(x), int(y)))
            except Exception as exc:
                log.debug("simulated blit failed: %s", exc)

    # -- text ------------------------------------------------------------

    def select_font(self, family: str, point_size: float, bold: bool = False) -> None:
        self._font_family = family or "Consolas"
        self._font_size = float(point_size)

    def _char_box(self):
        # Monospace approximation: 0.6 em wide, 1.2 em line box.
        em = self._font_size * self.geometry.dpi_y / 72.0
        return em * 0.6, em * 1.2

    def text_extent(self, text: str):
        char_w, line_h = self._char_box()
        return (int(round(len(text or " ") * char_w)), int(round(line_h)))

    def draw_text(self, text: str, x: int, y: int) -> None:
        if self._page is None:
            return
        try:
            from PIL import ImageDraw

            draw = ImageDraw.Draw(self._page)
            draw.text((int(x), int(y)), text, fill="black")
        except Exception:
            pass


@contextlib.contextmanager
def open_page_dc(printer: str, devmode=None) -> Iterator[PrinterDC]:
    handle = PrinterDC(printer, devmode)
    try:
        yield handle
    finally:
        handle.close()


def measure_page(printer: str, devmode=None) -> PageGeometry:
    with open_page_dc(printer, devmode) as handle:
        return handle.geometry


# -- queue -----------------------------------------------------------------


def list_jobs(printer: str, limit: int = 64) -> list[dict[str, Any]]:
    return list(_queues.get(printer, []))[:limit]


def find_job(printer: str, job_id: int) -> dict[str, Any] | None:
    for job in _queues.get(printer, []):
        if job["id"] == job_id:
            return job
    return None


def wait_for_spool(printer: str, job_id: int, timeout: float = 1.0) -> dict[str, Any]:
    return find_job(printer, job_id) or {}


def cancel_job(printer: str, job_id: int) -> bool:
    queue = _queues.get(printer, [])
    _queues[printer] = [job for job in queue if job["id"] != job_id]
    return True


def pause_job(printer: str, job_id: int) -> bool:
    return True


def resume_job(printer: str, job_id: int) -> bool:
    return True


def pause_printer(printer: str) -> bool:
    return True


def resume_printer(printer: str) -> bool:
    return True


def purge_printer(printer: str) -> bool:
    _queues[printer] = []
    return True


def open_printer_folder(printer: str) -> bool:
    return False


def shell_print(path: str, printer: str = "") -> bool:
    log.info("simulated shell print of %s to %s", path, printer or "default")
    time.sleep(0.2)
    return True
