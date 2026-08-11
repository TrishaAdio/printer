"""Small pure helpers shared across the app. No Qt, no win32, easy to reason about."""

from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Iterable, Sequence
from pathlib import Path

MM_PER_INCH = 25.4

IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".jpe", ".bmp", ".gif", ".webp", ".tif", ".tiff",
    ".ico", ".ppm", ".pgm", ".tga", ".jfif", ".avif",
}
PDF_EXTS = {".pdf"}
TEXT_EXTS = {
    ".txt", ".log", ".md", ".csv", ".json", ".xml", ".yml", ".yaml", ".ini",
    ".cfg", ".py", ".js", ".ts", ".c", ".h", ".cpp", ".cs", ".java", ".sql",
    ".sh", ".bat", ".ps1", ".html", ".css", ".rs", ".go",
}
#: Handed to the shell "print" verb as a last resort (Word, Excel, ...).
SHELL_EXTS = {
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf", ".odt", ".ods",
}

SUPPORTED_EXTS = IMAGE_EXTS | PDF_EXTS | TEXT_EXTS | SHELL_EXTS


def classify(path: str | os.PathLike[str]) -> str:
    """Return one of ``pdf`` / ``image`` / ``text`` / ``shell`` / ``unsupported``."""
    ext = Path(path).suffix.lower()
    if ext in PDF_EXTS:
        return "pdf"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in TEXT_EXTS:
        return "text"
    if ext in SHELL_EXTS:
        return "shell"
    return "unsupported"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def natural_key(text: str) -> list[object]:
    """Sort key so ``page2`` lands before ``page10``."""
    parts = re.split(r"(\d+)", str(text).lower())
    return [int(p) if p.isdigit() else p for p in parts]


def human_size(num: float) -> str:
    if num < 1024:
        return f"{int(num)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        num /= 1024.0
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}".replace(".0 ", " ")
    return f"{num:.1f} TB"


def human_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 1:
        return "<1s"
    if seconds < 60:
        return f"{int(round(seconds))}s"
    minutes, secs = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def mm_to_inch(mm: float) -> float:
    return mm / MM_PER_INCH


def inch_to_mm(inch: float) -> float:
    return inch * MM_PER_INCH


def clamp(value, low, high):
    return low if value < low else high if value > high else value


def as_point(value) -> tuple[float, float] | None:
    """Coerce whatever a driver returned for a coordinate pair into ``(x, y)``.

    ``win32print.DeviceCapabilities`` reports paper dimensions and resolutions as
    pairs, but the shape of each pair is not consistent: depending on the pywin32
    build and the capability being queried it can be a tuple, a list, a mapping
    keyed ``x``/``y``, or an object with ``x``/``y`` attributes. Indexing blindly
    with ``[0]`` works against some drivers and raises ``KeyError`` against others,
    which is a crash on startup for anyone with the wrong printer installed.

    Returns ``None`` when the value cannot be read as a pair, so callers can skip
    the entry instead of failing.
    """
    if value is None:
        return None
    # Mapping, with either casing.
    if isinstance(value, dict):
        for keys in (("x", "y"), ("X", "Y"), ("cx", "cy"), (0, 1)):
            if keys[0] in value and keys[1] in value:
                try:
                    return (float(value[keys[0]]), float(value[keys[1]]))
                except (TypeError, ValueError):
                    return None
        return None
    # Object with attributes, such as a PyPOINT or a QSize-alike.
    for names in (("x", "y"), ("cx", "cy"), ("width", "height")):
        if hasattr(value, names[0]) and hasattr(value, names[1]):
            try:
                first = getattr(value, names[0])
                second = getattr(value, names[1])
                # Guard against methods rather than plain attributes.
                first = first() if callable(first) else first
                second = second() if callable(second) else second
                return (float(first), float(second))
            except (TypeError, ValueError):
                return None
    # Sequence.
    try:
        if len(value) >= 2:
            return (float(value[0]), float(value[1]))
    except (TypeError, ValueError, KeyError, IndexError):
        return None
    return None


class PageRangeError(ValueError):
    """Raised for a page range the user can fix by editing the text."""


def parse_page_range(spec: str, page_count: int) -> list[int]:
    """Turn ``"1-3, 7, 12-"`` into a de-duplicated, ordered 1-based page list.

    An empty or whitespace-only spec means "every page". Open ended ranges
    (``12-``) run to the last page. Out-of-range values are clipped rather than
    rejected so a range copied from another document still prints something
    sensible, but a range entirely past the end is an error worth surfacing.
    """
    if page_count <= 0:
        return []
    spec = (spec or "").strip()
    if not spec:
        return list(range(1, page_count + 1))

    pages: list[int] = []
    seen = set()
    for raw_token in spec.replace(";", ",").split(","):
        token = raw_token.strip()
        if not token:
            continue
        if not re.fullmatch(r"\d*\s*-?\s*\d*", token):
            raise PageRangeError(f"'{token}' is not a page or range")
        if "-" in token:
            left, _, right = token.partition("-")
            left, right = left.strip(), right.strip()
            start = int(left) if left else 1
            end = int(right) if right else page_count
        else:
            start = end = int(token)
        if start == 0 or end == 0:
            raise PageRangeError("pages start at 1")
        if start > end:
            start, end = end, start
        if start > page_count:
            # Entirely past the end. Skip it rather than silently collapsing it
            # onto the last page, which would print something nobody asked for.
            continue
        start = clamp(start, 1, page_count)
        end = clamp(end, 1, page_count)
        for page in range(start, end + 1):
            if page not in seen:
                seen.add(page)
                pages.append(page)

    if not pages:
        raise PageRangeError(f"no pages in range for a {page_count} page document")
    return pages


def apply_subset(pages: Sequence[int], subset: str) -> list[int]:
    """Filter to ``odd`` / ``even`` sheet positions, or pass everything through.

    Odd and even refer to the document page numbers, which is what users mean
    when they hand-feed paper for two sided printing.
    """
    if subset == "odd":
        return [p for p in pages if p % 2 == 1]
    if subset == "even":
        return [p for p in pages if p % 2 == 0]
    return list(pages)


def iter_files(paths: Iterable[str], recursive: bool = True) -> list[str]:
    """Expand a drop of mixed files and folders into a sorted file list.

    Directories are walked (optionally recursively), unsupported extensions are
    dropped, and the result is natural-sorted so ``scan_2`` precedes ``scan_10``.
    """
    found: list[str] = []
    for raw in paths:
        if not raw:
            continue
        path = Path(raw)
        try:
            if path.is_dir():
                walker = path.rglob("*") if recursive else path.glob("*")
                for child in walker:
                    try:
                        if child.is_file() and child.suffix.lower() in SUPPORTED_EXTS:
                            found.append(str(child))
                    except OSError:
                        continue
            elif path.is_file():
                found.append(str(path))
        except OSError:
            continue
    found.sort(key=lambda p: (str(Path(p).parent).lower(), natural_key(Path(p).name)))
    # Preserve first occurrence only.
    out: list[str] = []
    seen = set()
    for item in found:
        key = os.path.normcase(os.path.abspath(item))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


class Ticker:
    """Tracks throughput so the UI can show a believable ETA.

    A plain "pages remaining x average" estimate swings wildly on the first
    couple of pages, so this keeps an exponentially weighted average instead.
    """

    def __init__(self, smoothing: float = 0.3) -> None:
        self.smoothing = smoothing
        self.avg_seconds: float | None = None
        self._mark: float | None = None

    def start_item(self) -> None:
        self._mark = time.monotonic()

    def end_item(self) -> None:
        if self._mark is None:
            return
        elapsed = time.monotonic() - self._mark
        self._mark = None
        if self.avg_seconds is None:
            self.avg_seconds = elapsed
        else:
            self.avg_seconds = (
                self.smoothing * elapsed + (1.0 - self.smoothing) * self.avg_seconds
            )

    def eta(self, remaining: int) -> float | None:
        if self.avg_seconds is None or remaining <= 0:
            return None
        return self.avg_seconds * remaining
