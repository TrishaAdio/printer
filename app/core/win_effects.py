"""Windows window effects: blur behind, dark title bar, rounded corners.

Windows 10 is the target, which shapes the choices here.

* Windows 10 has no public API for Mica and its acrylic blur behind, while it
  does exist, drags badly when a window is moved. So the default is the older
  Aero style blur behind, which is smooth, plus our own gradient and grain
  inside the window doing the visual work. Acrylic remains selectable.
* Rounded corners are not a system feature on Windows 10, so the shape is drawn
  in QML on a translucent surface instead.

Every call is a no-op off Windows and every failure is swallowed: a missing
effect must never stop the app from opening.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from . import env
from .logging_setup import get as get_logger

log = get_logger("win_effects")

# DWM window attributes
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35

DWMWCP_ROUND = 2
DWMSBT_TRANSIENTWINDOW = 3   # acrylic, Windows 11 only
DWMSBT_MAINWINDOW = 2        # mica, Windows 11 only

# SetWindowCompositionAttribute
WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_GRADIENT = 1
ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(ctypes.c_int)),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _build_number() -> int:
    if not env.IS_WINDOWS:
        return 0
    try:
        import sys

        version = getattr(sys, "getwindowsversion", None)
        if version:
            return int(version().build)
    except Exception:
        pass
    return 0


def is_windows_11() -> bool:
    return _build_number() >= 22000


def describe() -> str:
    if not env.IS_WINDOWS:
        return "not Windows, effects disabled"
    build = _build_number()
    return f"Windows build {build} ({'11' if build >= 22000 else '10'})"


def _dwm_set(hwnd: int, attribute: int, value: int) -> bool:
    try:
        dwm = ctypes.windll.dwmapi
        data = ctypes.c_int(int(value))
        result = dwm.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_uint(attribute),
            ctypes.byref(data), ctypes.sizeof(data),
        )
        return result == 0
    except Exception as exc:
        log.debug("DwmSetWindowAttribute(%s) failed: %s", attribute, exc)
        return False


def set_dark_titlebar(hwnd: int, dark: bool = True) -> None:
    """Applies to the system frame; harmless while we draw our own."""
    if not env.IS_WINDOWS or not hwnd:
        return
    if not _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0):
        _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, 1 if dark else 0)


def set_rounded_corners(hwnd: int) -> bool:
    """Windows 11 only. On 10 the QML surface draws the radius itself."""
    if not env.IS_WINDOWS or not hwnd or not is_windows_11():
        return False
    return _dwm_set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)


def _set_accent(hwnd: int, state: int, tint: int) -> bool:
    try:
        user32 = ctypes.windll.user32
        set_attribute = getattr(user32, "SetWindowCompositionAttribute", None)
        if set_attribute is None:
            return False
        policy = ACCENT_POLICY(state, 2, ctypes.c_uint(tint).value, 0)
        data = WINDOWCOMPOSITIONATTRIBDATA(
            WCA_ACCENT_POLICY,
            ctypes.cast(ctypes.pointer(policy), ctypes.POINTER(ctypes.c_int)),
            ctypes.sizeof(policy),
        )
        return bool(set_attribute(wintypes.HWND(hwnd), ctypes.byref(data)))
    except Exception as exc:
        log.debug("SetWindowCompositionAttribute failed: %s", exc)
        return False


def _abgr(hex_colour: str, alpha: int) -> int:
    """Pack #rrggbb plus alpha into the ABGR word the accent policy expects."""
    value = hex_colour.lstrip("#")
    if len(value) != 6:
        value = "101018"
    red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return (int(alpha) << 24) | (blue << 16) | (green << 8) | red


def apply_backdrop(
    hwnd: int,
    mode: str = "blur",
    tint: str = "#0E1018",
    tint_alpha: int = 168,
) -> str:
    """Ask Windows to blur whatever sits behind the window.

    Returns the mode that was actually applied, which the caller shows in
    settings so the user is not told they have acrylic when they do not.
    """
    if not env.IS_WINDOWS or not hwnd:
        return "off"
    if mode == "off":
        _set_accent(hwnd, ACCENT_DISABLED, 0)
        return "off"

    colour = _abgr(tint, tint_alpha)

    if mode == "acrylic":
        if is_windows_11() and _dwm_set(
            hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW
        ):
            return "acrylic"
        if _set_accent(hwnd, ACCENT_ENABLE_ACRYLICBLURBEHIND, colour):
            return "acrylic"

    if _set_accent(hwnd, ACCENT_ENABLE_BLURBEHIND, colour):
        return "blur"
    if _set_accent(hwnd, ACCENT_ENABLE_TRANSPARENTGRADIENT, colour):
        return "tint"
    return "off"


def hwnd_of(window) -> int:
    """Extract the native handle from a QWindow or QQuickWindow."""
    try:
        return int(window.winId())
    except Exception as exc:
        log.debug("cannot read winId: %s", exc)
        return 0


def prepare_window(window, mode: str = "blur", tint: str = "#0E1018",
                   tint_alpha: int = 168) -> str:
    """Apply every effect we want on a freshly shown window."""
    handle = hwnd_of(window)
    if not handle:
        return "off"
    set_dark_titlebar(handle, True)
    set_rounded_corners(handle)
    applied = apply_backdrop(handle, mode, tint, tint_alpha)
    log.info("window effects: %s on %s", applied, describe())
    return applied
