"""Job execution.

One public function, :func:`print_file`, takes a path plus options and drives the
whole thing: capability constraint, page selection, sheet planning, copies,
manual two sided passes, strip rendering and spooling. It reports progress and
honours cancellation through a small hooks object so it stays free of Qt.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import printers
from ..logging_setup import get as get_logger
from ..options import Capabilities, PrintOptions
from ..util import PageRangeError, apply_subset, classify, parse_page_range
from . import nup
from .raster import (
    FILTER_PAD_ROWS,
    Placement,
    Rect,
    available_rect,
    compute_placement,
    finish_band,
    plan_bands,
)
from .sources import PageSource, SourceError, open_source, probe
from .textprint import TextDocument, estimate_pages

log = get_logger("printing.engine")


class Cancelled(Exception):
    """Raised internally when the user stops a job mid flight."""


@dataclass
class Hooks:
    """Callbacks into the caller. Every one is optional."""

    on_progress: Callable[[int, int, str, str], None] | None = None
    on_note: Callable[[str], None] | None = None
    is_cancelled: Callable[[], bool] | None = None
    #: Return True to continue. Used for the manual two sided paper swap.
    ask: Callable[[str, str], bool] | None = None

    def progress(self, done: int, total: int, phase: str, detail: str = "") -> None:
        if self.on_progress:
            self.on_progress(done, total, phase, detail)

    def note(self, text: str) -> None:
        log.info("note: %s", text)
        if self.on_note:
            self.on_note(text)

    def cancelled(self) -> bool:
        return bool(self.is_cancelled and self.is_cancelled())

    def check(self) -> None:
        if self.cancelled():
            raise Cancelled()

    def confirm(self, title: str, message: str) -> bool:
        if self.ask:
            return bool(self.ask(title, message))
        return True


@dataclass
class JobResult:
    ok: bool = False
    status: str = "failed"        # done | failed | cancelled
    error: str = ""
    sheets: int = 0
    pages: int = 0
    dpi: int = 0
    spool_job_id: int = 0
    duration: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class _Pass:
    label: str
    sheets: list[list[int]]
    prompt: str = ""


def estimate(path: str, options: PrintOptions, caps: Capabilities | None = None) -> dict:
    """Page and sheet counts for the queue, without touching the printer."""
    kind = classify(path)
    info = {"kind": kind, "pages": 0, "sheets": 0, "error": ""}
    if kind == "text":
        info["pages"] = estimate_pages(path, options)
    elif kind == "shell":
        info["pages"] = 0
    elif kind == "unsupported":
        info["error"] = "unsupported file type"
        return info
    else:
        meta = probe(path, kind)
        info["pages"] = meta["pages"]
        info["error"] = meta["error"]

    try:
        selected = parse_page_range(options.page_range, info["pages"])
        selected = apply_subset(selected, options.page_subset)
        count = len(selected)
    except PageRangeError as exc:
        info["error"] = str(exc)
        count = info["pages"]

    per_sheet = max(1, int(options.nup))
    sheets = -(-count // per_sheet) if count else 0
    if options.manual_duplex:
        # Same number of sheets, but they go through the printer twice.
        pass
    info["sheets"] = sheets * max(1, int(options.copies))
    info["selected_pages"] = count
    return info


def _select_pages(source_pages: int, options: PrintOptions) -> list[int]:
    pages = parse_page_range(options.page_range, source_pages)
    pages = apply_subset(pages, options.page_subset)
    if options.reverse:
        pages.reverse()
    return pages


def _build_passes(sheets: list[list[int]], options: PrintOptions) -> list[_Pass]:
    """Split into printer passes, which is only interesting for manual duplex."""
    if not options.manual_duplex or len(sheets) < 2:
        return [_Pass("all", sheets)]

    fronts = sheets[0::2]
    backs = sheets[1::2]
    # Printers stack face down, so the second pass runs in reverse to come out
    # in the right order once the stack is flipped and fed back in.
    backs = list(reversed(backs))
    passes = [_Pass("front", fronts)]
    if backs:
        passes.append(
            _Pass(
                "back",
                backs,
                prompt=(
                    f"{len(fronts)} sheet(s) printed on one side.\n\n"
                    "Take the stack out, flip it over, put it back in the tray, "
                    "then continue to print the other side."
                ),
            )
        )
    return passes


def _blit_placement(
    dc,
    source: PageSource,
    page_index: int,
    placement: Placement,
    options: PrintOptions,
    hooks: Hooks,
    dry_run: bool,
) -> None:
    """Render one placed page in strips and copy each onto the sheet."""
    target = placement.target
    if target.w <= 0 or target.h <= 0:
        return
    pad = FILTER_PAD_ROWS if options.sharpen else 0

    for y0, y1 in plan_bands(target.h, target.w):
        hooks.check()
        pad_top = min(pad, y0)
        pad_bottom = min(pad, target.h - y1)
        box = placement.band_source_box(y0 - pad_top, y1 + pad_bottom, 0)
        rows = (y1 - y0) + pad_top + pad_bottom
        band = source.render(page_index, target.w, rows, box, placement.rotate)
        band = finish_band(band, options, pad_top, pad_bottom)
        if band.height != (y1 - y0):
            # Should not happen; better to skip a strip than to smear the page.
            log.warning(
                "strip height %s does not match plan %s, skipping",
                band.height, y1 - y0,
            )
            continue
        if not dry_run:
            dc.blit(band, target.x, target.y + y0)
        del band


def print_file(
    path: str,
    options: PrintOptions,
    hooks: Hooks | None = None,
    caps: Capabilities | None = None,
) -> JobResult:
    hooks = hooks or Hooks()
    started = time.monotonic()
    result = JobResult()
    options = options.copy()
    options.normalise()

    name = Path(path).name
    kind = classify(path)
    if kind == "unsupported":
        result.error = "GlassPrint cannot render this file type"
        return result
    if not Path(path).exists():
        result.error = "file no longer exists"
        return result

    if not options.printer:
        options.printer = printers.pick_printer()
    if not options.printer:
        result.error = "no printer available"
        return result

    caps = caps or printers.capabilities(options.printer)
    result.notes = options.constrain_to(caps)
    for note in result.notes:
        hooks.note(note)

    # Office documents and anything else we do not rasterise ourselves are
    # handed to the shell, which uses the application that owns the format.
    if kind == "shell":
        hooks.progress(0, 1, "spooling", "handing to the associated application")
        ok = printers.shell_print(path, options.printer)
        result.ok = ok
        result.status = "done" if ok else "failed"
        result.error = "" if ok else "the associated application refused to print"
        result.sheets = result.pages = 1 if ok else 0
        result.duration = time.monotonic() - started
        hooks.progress(1, 1, result.status, "")
        return result

    dpi = options.effective_dpi(caps)
    result.dpi = dpi
    devmode = printers.devmode_for(options, caps, dpi)

    source: PageSource | None = None
    text_doc: TextDocument | None = None
    try:
        # ---------------------------------------------------------------- plan
        per_sheet = max(1, int(options.nup))
        with printers.open_page_dc(options.printer, devmode) as probe_dc:
            geometry = probe_dc.geometry
            avail = available_rect(geometry, options)
            cell_rects = nup.cells(
                per_sheet, avail, nup.default_gutter(geometry.dpi_x, per_sheet)
            )
            if kind == "text":
                text_doc = TextDocument(path, options)
                # Lay out for a single cell so N-up text paginates per cell
                # rather than per sheet. Cells differ by at most one dot.
                page_count = text_doc.layout(probe_dc, cell_rects[0])
            else:
                source = open_source(path, kind)
                if hasattr(source, "render_grayscale"):
                    source.render_grayscale = bool(
                        not options.color or options.force_grayscale_render
                    )
                page_count = source.page_count

        log.info(
            "%s: %s pages, %s dpi, sheet %sx%s dots (printable %sx%s, offset %s,%s)",
            name, page_count, dpi, geometry.physical_w, geometry.physical_h,
            geometry.printable_w, geometry.printable_h, geometry.offset_x, geometry.offset_y,
        )
        if geometry.printable_w <= 0 or geometry.printable_h <= 0:
            raise RuntimeError(
                "the driver reported a zero size printable area; "
                "check the paper size in the printer's own properties"
            )

        try:
            pages = _select_pages(page_count, options)
        except PageRangeError as exc:
            raise RuntimeError(f"page range: {exc}") from exc

        sheets = nup.group(pages, per_sheet)
        passes = _build_passes(sheets, options)

        driver_copies = max(1, min(options.copies, max(1, caps.max_copies)))
        loops = int(math.ceil(options.copies / driver_copies))
        if loops > 1:
            hooks.note(
                f"{options.copies} copies split into {loops} passes because the "
                f"driver accepts {driver_copies} at a time"
            )

        total_units = sum(len(p.sheets) for p in passes) * loops
        done_units = 0
        result.pages = len(pages) * options.copies

        # Placements only depend on the source page size, so cache per page to
        # avoid recomputing for every copy and every cell.
        placement_cache: dict = {}

        def placement_for(page_index: int, cell: Rect) -> Placement:
            key = (page_index, cell.as_tuple())
            cached = placement_cache.get(key)
            if cached is not None:
                return cached
            width, height = source.page_size(page_index, 0)
            dpi_x, dpi_y = source.source_dpi(page_index)
            place = compute_placement(width, height, dpi_x, dpi_y, geometry, options, cell)
            placement_cache[key] = place
            if place.clipped and len(placement_cache) == 1:
                hooks.note("content is larger than the page and will be cropped")
            return place

        # --------------------------------------------------------------- print
        for loop_index in range(loops):
            for _pass_index, current in enumerate(passes):
                if not current.sheets:
                    continue
                if current.prompt:
                    hooks.progress(done_units, total_units, "waiting", "waiting for paper")
                    if not hooks.confirm("Flip the paper", current.prompt):
                        raise Cancelled()

                hooks.check()
                title = name if loops == 1 else f"{name} (copy {loop_index + 1})"
                if len(passes) > 1:
                    title = f"{title} [{current.label}]"

                with printers.open_page_dc(options.printer, devmode) as dc:
                    if not options.dry_run:
                        job_id = dc.start_doc(title)
                        if not result.spool_job_id:
                            result.spool_job_id = job_id
                    try:
                        for sheet_index, sheet_pages in enumerate(current.sheets):
                            hooks.check()
                            detail = (
                                f"sheet {sheet_index + 1} of {len(current.sheets)}"
                                + (f", {current.label}" if len(passes) > 1 else "")
                                + (f", copy {loop_index + 1}" if loops > 1 else "")
                            )
                            hooks.progress(done_units, total_units, "printing", detail)

                            if not options.dry_run:
                                dc.start_page()
                            try:
                                if text_doc is not None:
                                    for cell_index, page_index in enumerate(sheet_pages):
                                        cell = cell_rects[cell_index % len(cell_rects)]
                                        if not options.dry_run:
                                            text_doc.draw_page(dc, page_index - 1, cell)
                                else:
                                    for cell_index, page_index in enumerate(sheet_pages):
                                        cell = cell_rects[cell_index % len(cell_rects)]
                                        place = placement_for(page_index - 1, cell)
                                        _blit_placement(
                                            dc, source, page_index - 1, place,
                                            options, hooks, options.dry_run,
                                        )
                            finally:
                                if not options.dry_run:
                                    dc.end_page()

                            done_units += 1
                            result.sheets += 1
                            hooks.progress(done_units, total_units, "printing", detail)

                        if not options.dry_run:
                            dc.end_doc()
                    except Cancelled:
                        dc.abort()
                        raise
                    except Exception:
                        dc.abort()
                        raise

        result.ok = True
        result.status = "done"
        hooks.progress(total_units, total_units, "done", "")

    except Cancelled:
        result.status = "cancelled"
        result.error = "cancelled"
        hooks.progress(0, 1, "cancelled", "")
    except (SourceError, RuntimeError, OSError, ValueError) as exc:
        result.status = "failed"
        result.error = str(exc) or exc.__class__.__name__
        log.exception("job failed for %s", path)
        hooks.progress(0, 1, "failed", result.error)
    except Exception as exc:  # last resort so the worker thread never dies
        result.status = "failed"
        result.error = f"unexpected error: {exc}"
        log.exception("unexpected failure for %s", path)
        hooks.progress(0, 1, "failed", result.error)
    finally:
        if source is not None:
            source.close()
        result.duration = time.monotonic() - started

    return result


def make_thumbnail(path: str, out_path: str, max_px: int = 900) -> bool:
    """Render page one to a PNG for the preview pane."""
    kind = classify(path)
    try:
        if kind in ("pdf", "image"):
            with open_source(path, kind) as source:
                image = source.thumbnail(0, max_px)
                image.convert("RGB").save(out_path, "PNG")
                return True
        if kind == "text":
            return _text_thumbnail(path, out_path, max_px)
    except Exception as exc:
        log.debug("no thumbnail for %s: %s", path, exc)
    return False


def _text_thumbnail(path: str, out_path: str, max_px: int) -> bool:
    """A recognisable page of text, drawn with Pillow rather than the driver."""
    from PIL import Image, ImageDraw, ImageFont

    from .textprint import read_text

    width = int(max_px * 0.72)
    height = max_px
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=11)
    except TypeError:  # older Pillow
        font = ImageFont.load_default()

    text = read_text(path)
    y = 24
    margin = 22
    for line in text.split("\n")[:70]:
        draw.text((margin, y), line.expandtabs(4)[:96], fill=(24, 24, 28), font=font)
        y += 13
        if y > height - 20:
            break
    image.save(out_path, "PNG")
    return True
