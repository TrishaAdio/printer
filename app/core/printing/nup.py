"""Pages per sheet.

Implemented by placing each source page into its own cell on the sheet rather
than compositing a full page bitmap first. That keeps memory flat, avoids a
second resampling step, and works identically at any resolution.
"""

from __future__ import annotations

from .raster import Rect

#: Column x row grid for each supported count, chosen so cells stay as close to
#: the sheet's own aspect ratio as possible. The pair is (across, down) for a
#: portrait sheet and is transposed for a landscape one.
GRIDS = {
    1: (1, 1),
    2: (1, 2),
    4: (2, 2),
    6: (2, 3),
    9: (3, 3),
    16: (4, 4),
}


def grid_for(count: int, landscape_sheet: bool) -> tuple[int, int]:
    across, down = GRIDS.get(int(count), (1, 1))
    if landscape_sheet and across != down:
        across, down = down, across
    return across, down


def cells(count: int, avail: Rect, gutter: int = 0, order: str = "rows") -> list[Rect]:
    """Split ``avail`` into ``count`` equal cells.

    ``gutter`` is the gap between cells in device dots. Remainders from integer
    division are distributed one dot at a time across the leading cells so the
    cells always tile the area exactly, with no drifting seam down the sheet.
    """
    count = max(1, int(count))
    if count == 1:
        return [Rect(avail.x, avail.y, avail.w, avail.h)]

    across, down = grid_for(count, avail.w > avail.h)
    gutter = max(0, int(gutter))

    inner_w = max(1, avail.w - gutter * (across - 1))
    inner_h = max(1, avail.h - gutter * (down - 1))
    base_w, extra_w = divmod(inner_w, across)
    base_h, extra_h = divmod(inner_h, down)

    widths = [base_w + (1 if i < extra_w else 0) for i in range(across)]
    heights = [base_h + (1 if i < extra_h else 0) for i in range(down)]

    xs, x = [], avail.x
    for width in widths:
        xs.append(x)
        x += width + gutter
    ys, y = [], avail.y
    for height in heights:
        ys.append(y)
        y += height + gutter

    out: list[Rect] = []
    if order == "columns":
        for column in range(across):
            for row in range(down):
                out.append(Rect(xs[column], ys[row], widths[column], heights[row]))
    else:
        for row in range(down):
            for column in range(across):
                out.append(Rect(xs[column], ys[row], widths[column], heights[row]))
    return out[:count]


def group(pages: list[int], per_sheet: int) -> list[list[int]]:
    """Chunk a page list into sheets, padding the final sheet with blanks."""
    per_sheet = max(1, int(per_sheet))
    sheets: list[list[int]] = []
    for start in range(0, len(pages), per_sheet):
        sheets.append(pages[start : start + per_sheet])
    return sheets


def default_gutter(dpi: int, count: int) -> int:
    """A small breathing space between cells, scaled to the device."""
    if count <= 1:
        return 0
    return max(1, int(round(dpi * 0.04)))  # roughly 1 mm
