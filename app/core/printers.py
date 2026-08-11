"""Backend facade.

Chooses the real Windows stack when it is available and the simulation otherwise,
then re-exports one stable API. Every other module imports from here and never
from the backends directly.
"""

from __future__ import annotations

import threading
from typing import Any

from . import env
from .geometry import PageGeometry
from .logging_setup import get as get_logger
from .options import Capabilities, PrinterInfo, PrintOptions

log = get_logger("printers")

if env.SIMULATED:
    from . import printers_sim as backend  # type: ignore
else:  # pragma: no cover - only on a real Windows box
    from . import printers_win as backend  # type: ignore

IS_SIMULATED = env.SIMULATED

# Re-exported backend functions -------------------------------------------------
default_printer = backend.default_printer
set_default_printer = backend.set_default_printer
printer_status = backend.printer_status
base_devmode = backend.base_devmode
build_devmode = backend.build_devmode
show_driver_dialog = backend.show_driver_dialog
devmode_summary = backend.devmode_summary
open_page_dc = backend.open_page_dc
measure_page = backend.measure_page
list_jobs = backend.list_jobs
find_job = backend.find_job
wait_for_spool = backend.wait_for_spool
cancel_job = backend.cancel_job
pause_job = backend.pause_job
resume_job = backend.resume_job
pause_printer = backend.pause_printer
resume_printer = backend.resume_printer
purge_printer = backend.purge_printer
open_printer_folder = backend.open_printer_folder
shell_print = backend.shell_print
PrinterDC = backend.PrinterDC


# Capability cache --------------------------------------------------------------
# DeviceCapabilities does a round trip per probe and we ask for a dozen of them,
# so a slow USB driver can take a noticeable moment. Cache per printer name and
# let the UI invalidate when the user hits refresh.

_caps_lock = threading.RLock()
_caps_cache: dict[str, Capabilities] = {}

#: DEVMODE objects returned by the vendor property sheet, kept for the session.
_devmode_overrides: dict[str, Any] = {}


def list_printers() -> list[PrinterInfo]:
    return backend.list_printers()


def printer_names() -> list[str]:
    return [p.name for p in list_printers()]


def capabilities(name: str, refresh: bool = False) -> Capabilities:
    if not name:
        return Capabilities()
    with _caps_lock:
        if not refresh and name in _caps_cache:
            return _caps_cache[name]
    try:
        caps = backend.capabilities(name)
    except Exception as exc:
        # Never fatal. This runs at startup for whatever printer is default, and
        # one driver reporting something unexpected must not stop the application
        # from opening. Generic defaults still allow printing.
        log.exception("could not read the capabilities of %s", name)
        caps = Capabilities(
            printer=name,
            notes=[f"Could not read this printer's capabilities ({exc}); using defaults"],
        )
    with _caps_lock:
        _caps_cache[name] = caps
    return caps


def invalidate(name: str = "") -> None:
    with _caps_lock:
        if name:
            _caps_cache.pop(name, None)
        else:
            _caps_cache.clear()


def has_printer(name: str) -> bool:
    return any(p.name == name for p in list_printers())


def pick_printer(preferred: str = "") -> str:
    """Resolve a usable printer: the requested one, the system default, or any."""
    printers = list_printers()
    if not printers:
        return ""
    names = {p.name for p in printers}
    if preferred and preferred in names:
        return preferred
    system_default = default_printer()
    if system_default in names:
        return system_default
    return printers[0].name


# Driver override plumbing ------------------------------------------------------


def set_override(printer: str, devmode) -> None:
    if devmode is None:
        _devmode_overrides.pop(printer, None)
    else:
        _devmode_overrides[printer] = devmode


def get_override(printer: str):
    return _devmode_overrides.get(printer)


def clear_override(printer: str = "") -> None:
    if printer:
        _devmode_overrides.pop(printer, None)
    else:
        _devmode_overrides.clear()


def devmode_for(options: PrintOptions, caps: Capabilities | None = None, dpi: int = 0):
    """Build the DEVMODE for a job, layering our options over any driver override."""
    caps = caps or capabilities(options.printer)
    override = get_override(options.printer)
    return build_devmode(options.printer, options, caps, dpi or None, override)


def geometry_for(options: PrintOptions, caps: Capabilities | None = None,
                 dpi: int = 0) -> PageGeometry:
    caps = caps or capabilities(options.printer)
    devmode = devmode_for(options, caps, dpi)
    return measure_page(options.printer, devmode)


def snapshot() -> dict[str, Any]:
    """Everything the UI needs about the current printer landscape, in one call."""
    printers = list_printers()
    return {
        "simulated": IS_SIMULATED,
        "default": default_printer(),
        "printers": [p.to_dict() for p in printers],
    }
