"""Plain text and source code printing, drawn with real printer fonts.

Text is the one format not rendered as a bitmap. Asking the driver to draw glyphs
gives genuinely sharper output than any bitmap we could send, and the spool file
ends up kilobytes rather than megabytes, which matters a great deal when a batch
contains hundreds of logs.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..logging_setup import get as get_logger
from ..options import PrintOptions
from .raster import Rect

log = get_logger("printing.text")

#: Files above this are truncated rather than paginated forever.
MAX_LINES = 200_000
TAB_WIDTH = 4

ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def read_text(path: str) -> str:
    """Read a text file, trying the encodings Windows actually produces."""
    raw = Path(path).read_bytes()
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


class TextDocument:
    """Lays a text file out into pages for a specific device and area."""

    def __init__(self, path: str, options: PrintOptions) -> None:
        self.path = path
        self.options = options
        self.name = Path(path).name
        self.pages: list[list[str]] = []
        self._char_widths: dict = {}
        self._truncated = False

        text = read_text(path)
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES]
            lines.append(f"... truncated at {MAX_LINES} lines ...")
            self._truncated = True
        self.raw_lines = [line.expandtabs(TAB_WIDTH) for line in lines]

    # -- measurement -----------------------------------------------------

    def _width_of(self, dc, text: str) -> int:
        """Sum cached per character widths.

        Measuring every candidate line through the device context is far too slow
        for a large file, and a per character table is exact for the monospace
        fonts this is used with and close enough for proportional ones.
        """
        total = 0
        cache = self._char_widths
        for char in text:
            width = cache.get(char)
            if width is None:
                try:
                    width = int(dc.text_extent(char)[0])
                except Exception:
                    width = 0
                if width <= 0:
                    width = cache.get("n", 1) or 1
                cache[char] = width
            total += width
        return total

    def _wrap(self, dc, line: str, max_width: int) -> list[str]:
        if not line:
            return [""]
        if self._width_of(dc, line) <= max_width:
            return [line]
        if not self.options.text_wrap:
            # Hard clip instead of wrapping: trim until it fits.
            out = line
            while out and self._width_of(dc, out) > max_width:
                out = out[:-1]
            return [out]

        rows: list[str] = []
        current = ""
        for word in _split_keeping_spaces(line):
            candidate = current + word
            if current and self._width_of(dc, candidate) > max_width:
                rows.append(current.rstrip())
                current = word.lstrip() if word.strip() else ""
                # A single word longer than the line still has to be broken.
                while self._width_of(dc, current) > max_width and len(current) > 1:
                    cut = len(current) - 1
                    while cut > 1 and self._width_of(dc, current[:cut]) > max_width:
                        cut -= 1
                    rows.append(current[:cut])
                    current = current[cut:]
            else:
                current = candidate
        rows.append(current.rstrip())
        return rows or [""]

    def line_height(self, dc) -> int:
        try:
            height = int(dc.text_extent("Mg")[1])
        except Exception:
            height = 0
        if height <= 0:
            height = int(self.options.text_point_size * 96 / 72)
        return max(1, int(round(height * 1.18)))

    # -- layout ----------------------------------------------------------

    def layout(self, dc, avail: Rect) -> int:
        """Paginate for this device. Returns the page count."""
        dc.select_font(self.options.text_font, self.options.text_point_size)
        line_h = self.line_height(dc)
        header_h = (line_h * 2) if self.options.text_header else 0
        footer_h = line_h * 2 if self.options.text_header else 0
        body_h = max(line_h, avail.h - header_h - footer_h)
        per_page = max(1, body_h // line_h)

        wrapped: list[str] = []
        for line in self.raw_lines:
            wrapped.extend(self._wrap(dc, line, avail.w))

        self.pages = [
            wrapped[start : start + per_page] for start in range(0, len(wrapped), per_page)
        ] or [[""]]
        self._line_h = line_h
        self._header_h = header_h
        log.info(
            "%s laid out as %d page(s), %d lines per page",
            self.name, len(self.pages), per_page,
        )
        return len(self.pages)

    # -- drawing ---------------------------------------------------------

    def draw_page(self, dc, index: int, avail: Rect) -> None:
        if not self.pages:
            return
        index = max(0, min(index, len(self.pages) - 1))
        line_h = getattr(self, "_line_h", self.line_height(dc))
        header_h = getattr(self, "_header_h", 0)

        dc.select_font(self.options.text_font, self.options.text_point_size)

        if self.options.text_header:
            dc.select_font(self.options.text_font, self.options.text_point_size, bold=True)
            dc.draw_text(self.name, avail.x, avail.y)
            stamp = f"Page {index + 1} of {len(self.pages)}"
            width = 0
            try:
                width = int(dc.text_extent(stamp)[0])
            except Exception:
                width = 0
            dc.draw_text(stamp, avail.x + max(0, avail.w - width), avail.y)
            dc.select_font(self.options.text_font, self.options.text_point_size)

        y = avail.y + header_h
        for line in self.pages[index]:
            if line:
                dc.draw_text(line, avail.x, y)
            y += line_h


def _split_keeping_spaces(line: str) -> Sequence[str]:
    """Split into word chunks that keep their trailing whitespace attached."""
    out: list[str] = []
    token = ""
    for char in line:
        token += char
        if char in " \t":
            out.append(token)
            token = ""
    if token:
        out.append(token)
    return out


def estimate_pages(path: str, options: PrintOptions, lines_per_page: int = 62) -> int:
    """Cheap page estimate for the queue list, without a device context."""
    try:
        text = read_text(path)
    except OSError:
        return 1
    count = text.count("\n") + 1
    if options.text_header:
        lines_per_page = max(10, lines_per_page - 4)
    return max(1, -(-count // max(1, lines_per_page)))
