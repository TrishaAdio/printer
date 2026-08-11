"""The real Windows printing backend: spooler, DEVMODE and device contexts.

Everything the driver exposes is reachable from here:

* ``capabilities()`` interrogates ``DeviceCapabilities`` for papers, trays,
  media types, resolutions, duplex, collate, colour and staple.
* ``build_devmode()`` translates our :class:`PrintOptions` into DEVMODE fields,
  including the explicit DPI pair that drives HD output.
* ``show_driver_dialog()`` opens the vendor's own property sheet, so any feature
  we did not model (HP photo modes, borderless, custom colour profiles) is still
  one click away and is honoured for the job.
* ``open_page_dc()`` hands back a device context plus real physical geometry,
  which is what keeps placement aligned instead of approximately aligned.

Import guarded: on a non-Windows machine this module is never loaded.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from typing import Any

import win32api  # noqa: F401  (kept for ShellExecute based fallback printing)
import win32con
import win32gui
import win32print
import win32ui

from .geometry import PageGeometry
from .logging_setup import get as get_logger
from .options import Capabilities, NamedId, Paper, PrinterInfo, PrintOptions, Resolution
from .util import as_point

log = get_logger("printers.win")

# --------------------------------------------------------------------------- #
# Constants. Declared locally rather than trusting win32con to expose every one
# of them across pywin32 versions.
# --------------------------------------------------------------------------- #

DC_FIELDS = 1
DC_PAPERS = 2
DC_PAPERSIZE = 3
DC_MINEXTENT = 4
DC_MAXEXTENT = 5
DC_BINS = 6
DC_DUPLEX = 7
DC_BINNAMES = 12
DC_ENUMRESOLUTIONS = 13
DC_PAPERNAMES = 16
DC_ORIENTATION = 17
DC_COPIES = 18
DC_COLLATE = 22
DC_MANUFACTURER = 23
DC_MODEL = 24
DC_PRINTRATE = 26
DC_PRINTRATEUNIT = 27
DC_MEDIAREADY = 29
DC_STAPLE = 30
DC_PRINTRATEPPM = 31
DC_COLORDEVICE = 32
DC_NUP = 33
DC_MEDIATYPENAMES = 34
DC_MEDIATYPES = 35

DM_ORIENTATION = 0x00000001
DM_PAPERSIZE = 0x00000002
DM_PAPERLENGTH = 0x00000004
DM_PAPERWIDTH = 0x00000008
DM_SCALE = 0x00000010
DM_COPIES = 0x00000100
DM_DEFAULTSOURCE = 0x00000200
DM_PRINTQUALITY = 0x00000400
DM_COLOR = 0x00000800
DM_DUPLEX = 0x00001000
DM_YRESOLUTION = 0x00002000
DM_TTOPTION = 0x00004000
DM_COLLATE = 0x00008000
DM_ICMMETHOD = 0x00800000
DM_ICMINTENT = 0x01000000
DM_MEDIATYPE = 0x02000000
DM_DITHERTYPE = 0x04000000

DM_UPDATE = 1
DM_COPY = 2
DM_PROMPT = 4
DM_MODIFY = 8
DM_IN_BUFFER = DM_MODIFY
DM_IN_PROMPT = DM_PROMPT
DM_OUT_BUFFER = DM_COPY

DMORIENT_PORTRAIT = 1
DMORIENT_LANDSCAPE = 2
DMCOLOR_MONOCHROME = 1
DMCOLOR_COLOR = 2
DMDUP_SIMPLEX = 1
DMDUP_VERTICAL = 2
DMDUP_HORIZONTAL = 3
DMCOLLATE_FALSE = 0
DMCOLLATE_TRUE = 1
DMDITHER_NONE = 1
DMDITHER_ERRORDIFFUSION = 5
DMDITHER_GRAYSCALE = 10
DMTT_DOWNLOAD_OUTLINE = 4
DMICMMETHOD_SYSTEM = 2
DMICM_CONTRAST = 2
DMICM_COLORIMETRIC = 3

# GetDeviceCaps indices
HORZRES = 8
VERTRES = 10
LOGPIXELSX = 88
LOGPIXELSY = 90
PHYSICALWIDTH = 110
PHYSICALHEIGHT = 111
PHYSICALOFFSETX = 112
PHYSICALOFFSETY = 113
BITSPIXEL = 12
NUMCOLORS = 24

PRINTER_STATUS = [
    (0x00000001, "Paused", "paused"),
    (0x00000002, "Error", "error"),
    (0x00000004, "Being deleted", "warning"),
    (0x00000008, "Paper jam", "error"),
    (0x00000010, "Out of paper", "error"),
    (0x00000020, "Manual feed required", "warning"),
    (0x00000040, "Paper problem", "error"),
    (0x00000080, "Offline", "offline"),
    (0x00000100, "Transferring data", "busy"),
    (0x00000200, "Busy", "busy"),
    (0x00000400, "Printing", "busy"),
    (0x00000800, "Output bin full", "error"),
    (0x00001000, "Not available", "offline"),
    (0x00002000, "Waiting", "busy"),
    (0x00004000, "Processing", "busy"),
    (0x00008000, "Initialising", "busy"),
    (0x00010000, "Warming up", "busy"),
    (0x00020000, "Ink or toner low", "warning"),
    (0x00040000, "Out of ink or toner", "error"),
    (0x00080000, "Page could not print", "error"),
    (0x00100000, "Needs attention", "error"),
    (0x00200000, "Out of memory", "error"),
    (0x00400000, "Door open", "error"),
    (0x00800000, "Server unknown", "warning"),
    (0x01000000, "Power save", "ready"),
]

JOB_STATUS = [
    (0x00000001, "paused"),
    (0x00000002, "error"),
    (0x00000004, "deleting"),
    (0x00000008, "spooling"),
    (0x00000010, "printing"),
    (0x00000020, "offline"),
    (0x00000040, "out of paper"),
    (0x00000080, "printed"),
    (0x00000100, "deleted"),
    (0x00000200, "blocked"),
    (0x00000400, "needs attention"),
    (0x00000800, "restarting"),
    (0x00001000, "complete"),
    (0x00002000, "retained"),
    (0x00004000, "rendering"),
]

PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x00000400
PRINTER_ATTRIBUTE_SHARED = 0x00000008

VIRTUAL_HINTS = (
    "pdf", "xps", "onenote", "fax", "microsoft print to", "document writer",
    "snagit", "adobe", "cutepdf", "nitro", "foxit", "send to onenote",
)

_ENUM_FLAGS = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS


# --------------------------------------------------------------------------- #
# Enumeration and status
# --------------------------------------------------------------------------- #


def default_printer() -> str:
    try:
        return win32print.GetDefaultPrinter() or ""
    except Exception:  # pragma: no cover - no printers installed at all
        return ""


def set_default_printer(name: str) -> bool:
    try:
        win32print.SetDefaultPrinter(name)
        return True
    except Exception as exc:
        log.warning("SetDefaultPrinter(%s) failed: %s", name, exc)
        return False


def _decode_status(flags: int, attributes: int, jobs: int) -> tuple[str, str]:
    if attributes & PRINTER_ATTRIBUTE_WORK_OFFLINE:
        return "offline", "Offline"
    hits = [(text, kind) for bit, text, kind in PRINTER_STATUS if flags & bit]
    if not hits:
        return ("busy", f"Printing {jobs} job{'s' if jobs != 1 else ''}") if jobs else (
            "ready",
            "Ready",
        )
    order = {"error": 0, "offline": 1, "paused": 2, "warning": 3, "busy": 4, "ready": 5}
    hits.sort(key=lambda item: order.get(item[1], 9))
    return hits[0][1], ", ".join(text for text, _ in hits[:2])


def list_printers() -> list[PrinterInfo]:
    out: list[PrinterInfo] = []
    default = default_printer()
    try:
        raw = win32print.EnumPrinters(_ENUM_FLAGS, None, 2)
    except Exception as exc:
        log.error("EnumPrinters failed: %s", exc)
        return out

    for entry in raw:
        try:
            name = entry.get("pPrinterName") or ""
            if not name:
                continue
            flags = int(entry.get("Status") or 0)
            attributes = int(entry.get("Attributes") or 0)
            jobs = int(entry.get("cJobs") or 0)
            kind, text = _decode_status(flags, attributes, jobs)
            driver = entry.get("pDriverName") or ""
            port = entry.get("pPortName") or ""
            lowered = f"{name} {driver} {port}".lower()
            out.append(
                PrinterInfo(
                    name=name,
                    driver=entry.get("pDriverName") or "",
                    port=entry.get("pPortName") or "",
                    comment=entry.get("pComment") or "",
                    location=entry.get("pLocation") or "",
                    is_default=(name == default),
                    status_flags=flags,
                    status=kind,
                    status_text=text,
                    jobs=jobs,
                    is_virtual=any(hint in lowered for hint in VIRTUAL_HINTS),
                    shared=bool(attributes & PRINTER_ATTRIBUTE_SHARED),
                )
            )
        except Exception as exc:  # keep one bad driver from hiding the rest
            log.warning("skipping malformed printer entry: %s", exc)
    out.sort(key=lambda p: (not p.is_default, p.is_virtual, p.name.lower()))
    return out


def printer_status(name: str) -> dict[str, Any]:
    try:
        handle = win32print.OpenPrinter(name)
    except Exception as exc:
        return {"status": "offline", "status_text": f"Unavailable ({exc})", "jobs": 0}
    try:
        info = win32print.GetPrinter(handle, 2)
        flags = int(info.get("Status") or 0)
        attributes = int(info.get("Attributes") or 0)
        jobs = int(info.get("cJobs") or 0)
        kind, text = _decode_status(flags, attributes, jobs)
        return {"status": kind, "status_text": text, "jobs": jobs, "status_flags": flags}
    except Exception as exc:
        return {"status": "warning", "status_text": str(exc), "jobs": 0}
    finally:
        with contextlib.suppress(Exception):
            win32print.ClosePrinter(handle)


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #


def _pick_name(names, index: int, fallback: str) -> str:
    """Driver name lists arrive null padded and occasionally short or blank."""
    if index < len(names):
        cleaned = str(names[index]).rstrip("\x00").strip()
        if cleaned:
            return cleaned
    return fallback


def _dev_caps(name: str, port: str, index: int, default=None):
    try:
        return win32print.DeviceCapabilities(name, port, index)
    except Exception:
        return default


def capabilities(name: str) -> Capabilities:
    """Ask the driver what it can do. Every probe is individually guarded."""
    caps = Capabilities(printer=name)
    printers = {p.name: p for p in list_printers()}
    info = printers.get(name)
    port = info.port if info else ""
    if info:
        caps.driver = info.driver
        caps.port = info.port
        caps.is_virtual = info.is_virtual

    caps.manufacturer = str(_dev_caps(name, port, DC_MANUFACTURER, "") or "")
    caps.model = str(_dev_caps(name, port, DC_MODEL, "") or "")

    # Papers -------------------------------------------------------------
    ids = _dev_caps(name, port, DC_PAPERS, []) or []
    names = _dev_caps(name, port, DC_PAPERNAMES, []) or []
    sizes = _dev_caps(name, port, DC_PAPERSIZE, []) or []
    papers: list[Paper] = []
    for index, paper_id in enumerate(ids):
        label = ""
        if index < len(names):
            label = str(names[index]).rstrip("\x00").strip()
        if not label:
            label = f"Paper {paper_id}"
        width_mm = height_mm = 0.0
        if index < len(sizes):
            # DC_PAPERSIZE is reported in tenths of a millimetre, in a pair whose
            # concrete type varies by driver and pywin32 build.
            pair = as_point(sizes[index])
            if pair is not None:
                width_mm, height_mm = pair[0] / 10.0, pair[1] / 10.0
        papers.append(Paper(id=int(paper_id), name=label, width_mm=width_mm, height_mm=height_mm))
    caps.papers = papers

    # Trays --------------------------------------------------------------
    bin_ids = _dev_caps(name, port, DC_BINS, []) or []
    bin_names = _dev_caps(name, port, DC_BINNAMES, []) or []
    caps.bins = [
        NamedId(
            id=int(bin_id),
            name=_pick_name(
                bin_names, i, f"Tray {bin_id}"
            ),
        )
        for i, bin_id in enumerate(bin_ids)
    ]

    # Media types --------------------------------------------------------
    media_ids = _dev_caps(name, port, DC_MEDIATYPES, []) or []
    media_names = _dev_caps(name, port, DC_MEDIATYPENAMES, []) or []
    caps.media_types = [
        NamedId(
            id=int(media_id),
            name=_pick_name(
                media_names, i, f"Media {media_id}"
            ),
        )
        for i, media_id in enumerate(media_ids)
    ]

    ready = _dev_caps(name, port, DC_MEDIAREADY, []) or []
    caps.media_ready = [str(r).rstrip("\x00").strip() for r in ready if str(r).strip()]

    # Resolutions --------------------------------------------------------
    resolutions: list[Resolution] = []
    raw_res = _dev_caps(name, port, DC_ENUMRESOLUTIONS, []) or []
    for item in raw_res:
        pair = as_point(item)
        if pair is None:
            continue
        x_dpi, y_dpi = int(pair[0]), int(pair[1])
        if x_dpi > 0 and y_dpi > 0:
            resolutions.append(Resolution(x=x_dpi, y=y_dpi))
    resolutions.sort(key=lambda r: (r.x, r.y))
    caps.resolutions = resolutions
    if resolutions:
        caps.max_dpi = max(r.x for r in resolutions)
    else:
        caps.max_dpi = 600
        caps.notes.append("Driver did not enumerate resolutions, assuming up to 600 dpi")

    # Flags --------------------------------------------------------------
    copies = _dev_caps(name, port, DC_COPIES, 1)
    try:
        caps.max_copies = max(1, int(copies))
    except (TypeError, ValueError):
        caps.max_copies = 1
    caps.duplex = bool(_dev_caps(name, port, DC_DUPLEX, 0))
    caps.collate = bool(_dev_caps(name, port, DC_COLLATE, 0))
    caps.staple = bool(_dev_caps(name, port, DC_STAPLE, 0))
    colour = _dev_caps(name, port, DC_COLORDEVICE, None)
    caps.color = True if colour is None else bool(colour)
    rotation = _dev_caps(name, port, DC_ORIENTATION, 90)
    caps.landscape = rotation in (90, 270)
    ppm = _dev_caps(name, port, DC_PRINTRATEPPM, 0)
    try:
        caps.print_rate_ppm = int(ppm or 0)
    except (TypeError, ValueError):
        caps.print_rate_ppm = 0

    # Driver defaults ----------------------------------------------------
    devmode = base_devmode(name)
    if devmode is not None:
        for attr, target in (
            ("PaperSize", "default_paper"),
            ("DefaultSource", "default_bin"),
            ("MediaType", "default_media"),
            ("Orientation", "default_orientation"),
        ):
            try:
                value = getattr(devmode, attr, 0) or 0
                setattr(caps, target, int(value))
            except Exception:
                pass
        try:
            quality = int(getattr(devmode, "PrintQuality", 0) or 0)
            caps.default_dpi = quality if quality > 0 else 300
        except Exception:
            caps.default_dpi = 300
    else:
        caps.notes.append("Driver did not return a DEVMODE, using generic defaults")

    return caps


# --------------------------------------------------------------------------- #
# DEVMODE
# --------------------------------------------------------------------------- #


def base_devmode(name: str):
    """Fetch a writable DEVMODE for a printer, trying every level that has one."""
    try:
        handle = win32print.OpenPrinter(name)
    except Exception as exc:
        log.warning("OpenPrinter(%s) failed: %s", name, exc)
        return None
    try:
        for level in (2, 8, 9):
            try:
                info = win32print.GetPrinter(handle, level)
            except Exception:
                continue
            devmode = info.get("pDevMode") if isinstance(info, dict) else None
            if devmode is not None:
                return devmode
    finally:
        with contextlib.suppress(Exception):
            win32print.ClosePrinter(handle)
    return None


def _set(devmode, attr: str, value, field_bit: int) -> bool:
    """Assign one DEVMODE member and flag it, tolerating drivers that refuse."""
    try:
        setattr(devmode, attr, value)
        devmode.Fields = int(getattr(devmode, "Fields", 0)) | field_bit
        return True
    except Exception as exc:
        log.debug("DEVMODE.%s = %r rejected: %s", attr, value, exc)
        return False


def build_devmode(
    name: str,
    options: PrintOptions,
    caps: Capabilities | None = None,
    dpi: int | None = None,
    override=None,
):
    """Translate PrintOptions into a DEVMODE.

    ``override`` is a DEVMODE previously returned by the driver's own property
    sheet. When present it becomes the base, so vendor-only features survive,
    and we then re-apply the handful of fields the user set in our UI.
    """
    devmode = override if override is not None else base_devmode(name)
    if devmode is None:
        return None

    caps = caps or Capabilities(printer=name)
    resolved_dpi = int(dpi or options.effective_dpi(caps))

    # Copies are handled by the driver when it can, otherwise the queue loops.
    driver_copies = min(max(1, options.copies), max(1, caps.max_copies))
    _set(devmode, "Copies", driver_copies, DM_COPIES)
    if caps.collate:
        _set(devmode, "Collate", DMCOLLATE_TRUE if options.collate else DMCOLLATE_FALSE, DM_COLLATE)

    _set(
        devmode,
        "Color",
        DMCOLOR_COLOR if (options.color and caps.color) else DMCOLOR_MONOCHROME,
        DM_COLOR,
    )

    duplex_map = {
        "simplex": DMDUP_SIMPLEX,
        "vertical": DMDUP_VERTICAL,
        "horizontal": DMDUP_HORIZONTAL,
    }
    if caps.duplex:
        _set(devmode, "Duplex", duplex_map.get(options.duplex, DMDUP_SIMPLEX), DM_DUPLEX)

    if options.orientation in ("portrait", "landscape"):
        _set(
            devmode,
            "Orientation",
            DMORIENT_LANDSCAPE if options.orientation == "landscape" else DMORIENT_PORTRAIT,
            DM_ORIENTATION,
        )

    if options.paper_size:
        _set(devmode, "PaperSize", int(options.paper_size), DM_PAPERSIZE)
    if options.paper_source:
        _set(devmode, "DefaultSource", int(options.paper_source), DM_DEFAULTSOURCE)
    if options.media_type:
        _set(devmode, "MediaType", int(options.media_type), DM_MEDIATYPE)

    # Explicit resolution pair. This is the HD path: PrintQuality carries the
    # x resolution in dpi and YResolution the y resolution.
    _set(devmode, "PrintQuality", resolved_dpi, DM_PRINTQUALITY)
    y_dpi = resolved_dpi
    if caps.resolutions:
        for res in caps.resolutions:
            if res.x == resolved_dpi:
                y_dpi = res.y
                break
    _set(devmode, "YResolution", y_dpi, DM_YRESOLUTION)

    # Photo mode leans on the driver's colour management and fine dithering.
    if options.quality in ("photo", "hd"):
        _set(devmode, "DitherType", DMDITHER_ERRORDIFFUSION, DM_DITHERTYPE)
        _set(devmode, "ICMMethod", DMICMMETHOD_SYSTEM, DM_ICMMETHOD)
        _set(devmode, "ICMIntent", DMICM_CONTRAST, DM_ICMINTENT)
    elif not options.color:
        _set(devmode, "DitherType", DMDITHER_GRAYSCALE, DM_DITHERTYPE)

    _set(devmode, "TTOption", DMTT_DOWNLOAD_OUTLINE, DM_TTOPTION)
    return devmode


def show_driver_dialog(name: str, hwnd: int = 0, current=None):
    """Open the vendor property sheet and return the DEVMODE the user approved.

    Returns ``None`` when cancelled or unsupported. This is the escape hatch that
    makes genuinely every driver feature reachable.
    """
    try:
        handle = win32print.OpenPrinter(name)
    except Exception as exc:
        log.warning("cannot open %s for properties: %s", name, exc)
        return None
    try:
        devmode_in = current if current is not None else base_devmode(name)
        devmode_out = base_devmode(name)
        if devmode_out is None:
            return None
        mode = DM_IN_BUFFER | DM_IN_PROMPT | DM_OUT_BUFFER
        if devmode_in is None:
            mode = DM_IN_PROMPT | DM_OUT_BUFFER
        result = win32print.DocumentProperties(
            int(hwnd or 0), handle, name, devmode_out, devmode_in, mode
        )
        if result == win32con.IDOK:
            return devmode_out
        return None
    except Exception as exc:
        log.warning("DocumentProperties failed for %s: %s", name, exc)
        return None
    finally:
        with contextlib.suppress(Exception):
            win32print.ClosePrinter(handle)


def devmode_summary(devmode) -> dict[str, Any]:
    """Read back the fields we understand so the UI reflects driver changes."""
    if devmode is None:
        return {}
    out: dict[str, Any] = {}
    mapping = {
        "Copies": "copies",
        "Collate": "collate",
        "Color": "color",
        "Duplex": "duplex",
        "Orientation": "orientation",
        "PaperSize": "paper_size",
        "DefaultSource": "paper_source",
        "MediaType": "media_type",
        "PrintQuality": "render_dpi",
    }
    for attr, key in mapping.items():
        try:
            out[key] = int(getattr(devmode, attr))
        except Exception:
            continue
    if "color" in out:
        out["color"] = out["color"] == DMCOLOR_COLOR
    if "collate" in out:
        out["collate"] = out["collate"] == DMCOLLATE_TRUE
    if "duplex" in out:
        out["duplex"] = {
            DMDUP_SIMPLEX: "simplex",
            DMDUP_VERTICAL: "vertical",
            DMDUP_HORIZONTAL: "horizontal",
        }.get(out["duplex"], "simplex")
    if "orientation" in out:
        out["orientation"] = (
            "landscape" if out["orientation"] == DMORIENT_LANDSCAPE else "portrait"
        )
    if out.get("render_dpi", 0) <= 0:
        out.pop("render_dpi", None)
    return out


# --------------------------------------------------------------------------- #
# Device context and page geometry
# --------------------------------------------------------------------------- #


def _read_geometry(dc) -> PageGeometry:
    def cap(index: int, fallback: int = 0) -> int:
        try:
            return int(dc.GetDeviceCaps(index))
        except Exception:
            return fallback

    geo = PageGeometry()
    geo.dpi_x = cap(LOGPIXELSX, 300) or 300
    geo.dpi_y = cap(LOGPIXELSY, geo.dpi_x) or geo.dpi_x
    geo.printable_w = cap(HORZRES)
    geo.printable_h = cap(VERTRES)
    geo.physical_w = cap(PHYSICALWIDTH) or geo.printable_w
    geo.physical_h = cap(PHYSICALHEIGHT) or geo.printable_h
    geo.offset_x = cap(PHYSICALOFFSETX)
    geo.offset_y = cap(PHYSICALOFFSETY)
    geo.bpp = cap(BITSPIXEL, 24)
    return geo


class PrinterDC:
    """Owns an HDC for the life of one document."""

    def __init__(self, printer: str, devmode=None) -> None:
        self.printer = printer
        self.dc = None
        self.geometry = PageGeometry()
        self.job_id: int = 0
        self._doc_open = False
        self._page_open = False
        self._font = None
        self._font_old = None
        self._create(devmode)

    def _create(self, devmode) -> None:
        handle = None
        if devmode is not None:
            try:
                handle = win32gui.CreateDC("WINSPOOL", self.printer, devmode)
            except Exception as exc:
                log.warning("CreateDC with DEVMODE failed (%s), using driver default", exc)
                handle = None
        if handle:
            self.dc = win32ui.CreateDCFromHandle(handle)
        else:
            self.dc = win32ui.CreateDC()
            self.dc.CreatePrinterDC(self.printer)
        with contextlib.suppress(Exception):
            self.dc.SetMapMode(win32con.MM_TEXT)
        self.geometry = _read_geometry(self.dc)

    @property
    def hdc(self) -> int:
        return int(self.dc.GetHandleOutput())

    def start_doc(self, title: str) -> int:
        self.job_id = int(self.dc.StartDoc(title[:250] or "GlassPrint document") or 0)
        self._doc_open = True
        return self.job_id

    def start_page(self) -> None:
        self.dc.StartPage()
        self._page_open = True

    def end_page(self) -> None:
        if self._page_open:
            self.dc.EndPage()
            self._page_open = False

    def end_doc(self) -> None:
        if self._doc_open:
            self.dc.EndDoc()
            self._doc_open = False

    def abort(self) -> None:
        try:
            if self._doc_open:
                self.dc.AbortDoc()
        except Exception:
            pass
        self._doc_open = False
        self._page_open = False

    def close(self) -> None:
        try:
            if self._font_old is not None:
                with contextlib.suppress(Exception):
                    self.dc.SelectObject(self._font_old)
            if self.dc is not None:
                self.dc.DeleteDC()
        except Exception:
            pass
        self.dc = None

    # -- drawing ---------------------------------------------------------

    def blit(self, image, x: int, y: int) -> None:
        """Copy a PIL image onto the page at device pixel (x, y), 1:1.

        The image is expected to be pre-sized to its exact device footprint, so
        GDI performs no resampling. That is deliberate: Pillow's Lanczos filter
        is far better than the driver's stretch blit, and 1:1 placement is what
        keeps banded output seam free.
        """
        from PIL import ImageWin  # local import keeps module import cheap

        if image.mode not in ("RGB", "L", "1"):
            image = image.convert("RGB")
        width, height = image.size
        dib = ImageWin.Dib(image)
        dib.draw(self.hdc, (int(x), int(y), int(x) + width, int(y) + height))

    # -- text ------------------------------------------------------------

    def select_font(self, family: str, point_size: float, bold: bool = False) -> None:
        height = -int(round(point_size * self.geometry.dpi_y / 72.0))
        spec = {
            "name": family or "Consolas",
            "height": height,
            "weight": 700 if bold else 400,
            "quality": 4,  # CLEARTYPE-ish; printers ignore it harmlessly
        }
        try:
            font = win32ui.CreateFont(spec)
        except Exception:
            spec["name"] = "Courier New"
            try:
                font = win32ui.CreateFont(spec)
            except Exception as exc:
                log.warning("no printer font available: %s", exc)
                return
        old = self.dc.SelectObject(font)
        if self._font_old is None:
            self._font_old = old
        self._font = font

    def text_extent(self, text: str):
        try:
            return self.dc.GetTextExtent(text or " ")
        except Exception:
            approx = int(self.geometry.dpi_x * 0.1)
            return (max(1, len(text)) * approx // 2, approx)

    def draw_text(self, text: str, x: int, y: int) -> None:
        try:
            self.dc.TextOut(int(x), int(y), text)
        except Exception as exc:
            log.debug("TextOut failed: %s", exc)


@contextlib.contextmanager
def open_page_dc(printer: str, devmode=None) -> Iterator[PrinterDC]:
    handle = PrinterDC(printer, devmode)
    try:
        yield handle
    finally:
        handle.close()


def measure_page(printer: str, devmode=None) -> PageGeometry:
    """Geometry probe without starting a document. Used for preview and layout."""
    try:
        with open_page_dc(printer, devmode) as handle:
            return handle.geometry
    except Exception as exc:
        log.warning("cannot measure %s: %s", printer, exc)
        return PageGeometry()


# --------------------------------------------------------------------------- #
# Spooler queue control
# --------------------------------------------------------------------------- #


def _decode_job_status(flags: int) -> str:
    hits = [text for bit, text in JOB_STATUS if flags & bit]
    return ", ".join(hits[:2]) if hits else "queued"


def list_jobs(printer: str, limit: int = 64) -> list[dict[str, Any]]:
    try:
        handle = win32print.OpenPrinter(printer)
    except Exception:
        return []
    try:
        raw = win32print.EnumJobs(handle, 0, limit, 1)
    except Exception:
        return []
    finally:
        with contextlib.suppress(Exception):
            win32print.ClosePrinter(handle)
    out = []
    for job in raw or []:
        out.append(
            {
                "id": int(job.get("JobId", 0)),
                "document": job.get("pDocument") or "",
                "user": job.get("pUserName") or "",
                "status_flags": int(job.get("Status", 0)),
                "status": job.get("pStatus") or _decode_job_status(int(job.get("Status", 0))),
                "pages": int(job.get("TotalPages", 0)),
                "printed": int(job.get("PagesPrinted", 0)),
            }
        )
    return out


def find_job(printer: str, job_id: int) -> dict[str, Any] | None:
    if job_id <= 0:
        return None
    for job in list_jobs(printer):
        if job["id"] == job_id:
            return job
    return None


def wait_for_spool(printer: str, job_id: int, timeout: float = 1.0) -> dict[str, Any]:
    """Give the spooler a moment to register the job we just submitted."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = find_job(printer, job_id)
        if job:
            return job
        time.sleep(0.05)
    return {}


def _job_command(printer: str, job_id: int, command: int) -> bool:
    try:
        handle = win32print.OpenPrinter(printer, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
    except Exception:
        try:
            handle = win32print.OpenPrinter(printer)
        except Exception as exc:
            log.warning("cannot open %s for job control: %s", printer, exc)
            return False
    try:
        win32print.SetJob(handle, int(job_id), 0, None, command)
        return True
    except Exception as exc:
        log.warning("SetJob(%s, %s) failed: %s", job_id, command, exc)
        return False
    finally:
        with contextlib.suppress(Exception):
            win32print.ClosePrinter(handle)


def cancel_job(printer: str, job_id: int) -> bool:
    return _job_command(printer, job_id, win32print.JOB_CONTROL_DELETE)


def pause_job(printer: str, job_id: int) -> bool:
    return _job_command(printer, job_id, win32print.JOB_CONTROL_PAUSE)


def resume_job(printer: str, job_id: int) -> bool:
    return _job_command(printer, job_id, win32print.JOB_CONTROL_RESUME)


def _printer_command(printer: str, command: int) -> bool:
    try:
        handle = win32print.OpenPrinter(printer, {"DesiredAccess": win32print.PRINTER_ALL_ACCESS})
    except Exception as exc:
        log.warning("cannot open %s for control: %s", printer, exc)
        return False
    try:
        win32print.SetPrinter(handle, 0, None, command)
        return True
    except Exception as exc:
        log.warning("SetPrinter(%s) failed: %s", command, exc)
        return False
    finally:
        with contextlib.suppress(Exception):
            win32print.ClosePrinter(handle)


def pause_printer(printer: str) -> bool:
    return _printer_command(printer, win32print.PRINTER_CONTROL_PAUSE)


def resume_printer(printer: str) -> bool:
    return _printer_command(printer, win32print.PRINTER_CONTROL_RESUME)


def purge_printer(printer: str) -> bool:
    return _printer_command(printer, win32print.PRINTER_CONTROL_PURGE)


def open_printer_folder(printer: str) -> bool:
    """Open the Windows queue window, for anything we deliberately do not clone."""
    try:
        win32api.ShellExecute(0, "open", "rundll32.exe",
                              f'printui.dll,PrintUIEntry /o /n "{printer}"', None, 1)
        return True
    except Exception as exc:
        log.warning("cannot open queue window: %s", exc)
        return False


def shell_print(path: str, printer: str = "") -> bool:
    """Last resort for formats we do not render ourselves (Office documents)."""
    try:
        if printer:
            win32api.ShellExecute(0, "printto", path, f'"{printer}"', None, 0)
        else:
            win32api.ShellExecute(0, "print", path, None, None, 0)
        return True
    except Exception as exc:
        log.warning("shell print failed for %s: %s", path, exc)
        return False
