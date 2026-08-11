"""Placement maths and band planning.

Two ideas carry all of the output quality in this app.

**Placement.** A printer device context puts its origin at the top left of the
*printable* area, not the physical sheet. Content is therefore positioned in that
space, and full bleed output deliberately uses negative coordinates. Every rect
here is in device dots of the target printer.

**Banding.** A4 at 1200 dpi is 9921 x 14031 dots, which is 418 MB as RGB. Whole
page bitmaps are not an option, so a placement is rendered as horizontal strips.
Each strip is resampled straight from the source with a floating point source
box, which means no seams and no cumulative rounding drift.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import PageGeometry
from ..options import PrintOptions

#: Peak bytes allowed for one band. Keeps a 1200 dpi job inside a sane working
#: set even on a 4 GB machine while staying large enough to be efficient.
BAND_BUDGET_BYTES = 48 * 1024 * 1024
MIN_BAND_ROWS = 32

#: Extra source rows resampled either side of a band when a neighbourhood filter
#: (sharpening) is active, then trimmed off. Without this the filter would see a
#: hard edge at every band boundary and leave visible lines.
FILTER_PAD_ROWS = 4


@dataclass
class Rect:
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def inset(self, dx: int, dy: int) -> Rect:
        return Rect(self.x + dx, self.y + dy, max(1, self.w - 2 * dx), max(1, self.h - 2 * dy))

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


@dataclass
class Placement:
    """Where one source page lands on one sheet, and which part of it is used."""

    target: Rect
    #: (x0, y0, x1, y1) in source units, already in post-rotation space.
    source_box: tuple[float, float, float, float]
    rotate: int = 0
    clipped: bool = False

    @property
    def source_width(self) -> float:
        return self.source_box[2] - self.source_box[0]

    @property
    def source_height(self) -> float:
        return self.source_box[3] - self.source_box[1]

    def band_source_box(self, y0: int, y1: int, pad: int = 0) -> tuple[float, float, float, float]:
        """Source box for target rows ``[y0, y1)``, optionally padded for filters."""
        height = max(1, self.target.h)
        sx0, sy0, sx1, sy1 = self.source_box
        span = sy1 - sy0
        top = sy0 + span * (max(0, y0 - pad) / height)
        bottom = sy0 + span * (min(height, y1 + pad) / height)
        return (sx0, top, sx1, bottom)


def available_rect(geometry: PageGeometry, options: PrintOptions) -> Rect:
    """The rect content may occupy, in device coordinates.

    Normal output is the printable area. Full bleed extends into the hardware
    margin using negative coordinates, which only survives if the driver really
    is in a borderless mode; otherwise the driver clips it, which is the correct
    and safe outcome.
    """
    if options.borderless:
        rect = Rect(
            x=-geometry.offset_x,
            y=-geometry.offset_y,
            w=geometry.physical_w or geometry.printable_w,
            h=geometry.physical_h or geometry.printable_h,
        )
    else:
        rect = Rect(0, 0, geometry.printable_w, geometry.printable_h)

    if options.extra_margin_mm > 0:
        dx = int(round(options.extra_margin_mm / 25.4 * geometry.dpi_x))
        dy = int(round(options.extra_margin_mm / 25.4 * geometry.dpi_y))
        rect = rect.inset(dx, dy)
    return rect


def compute_placement(
    source_w: float,
    source_h: float,
    source_dpi_x: float,
    source_dpi_y: float,
    geometry: PageGeometry,
    options: PrintOptions,
    avail: Rect | None = None,
) -> Placement:
    """Fit one source page into ``avail`` according to the scaling options.

    ``source_w/h`` are in the source's own units (pixels for images, points for
    PDF) and ``source_dpi_*`` converts them to inches, which is what makes
    "actual size" mean actual size.
    """
    avail = avail or available_rect(geometry, options)
    source_w = max(1.0, float(source_w))
    source_h = max(1.0, float(source_h))
    source_dpi_x = float(source_dpi_x) or 96.0
    source_dpi_y = float(source_dpi_y) or 96.0

    inches_w = source_w / source_dpi_x
    inches_h = source_h / source_dpi_y

    rotate = 0
    if options.auto_rotate:
        source_landscape = inches_w > inches_h
        target_landscape = avail.w > avail.h
        if source_landscape != target_landscape:
            rotate = 90
            inches_w, inches_h = inches_h, inches_w
            source_w, source_h = source_h, source_w

    # Natural footprint on this device, in dots.
    natural_w = inches_w * geometry.dpi_x
    natural_h = inches_h * geometry.dpi_y

    mode = options.scale_mode
    if mode == "actual":
        scale = 1.0
    elif mode == "custom":
        scale = max(0.1, options.scale_percent / 100.0)
    elif mode == "fill":
        scale = max(avail.w / natural_w, avail.h / natural_h)
    else:  # fit
        scale = min(avail.w / natural_w, avail.h / natural_h)

    draw_w = natural_w * scale
    draw_h = natural_h * scale

    source_box = (0.0, 0.0, source_w, source_h)
    clipped = False

    if mode == "fill":
        # Cover the sheet and crop the overflow symmetrically.
        target = Rect(avail.x, avail.y, avail.w, avail.h)
        visible_frac_x = min(1.0, avail.w / draw_w) if draw_w else 1.0
        visible_frac_y = min(1.0, avail.h / draw_h) if draw_h else 1.0
        crop_w = source_w * visible_frac_x
        crop_h = source_h * visible_frac_y
        x0 = (source_w - crop_w) / 2.0
        y0 = (source_h - crop_h) / 2.0
        source_box = (x0, y0, x0 + crop_w, y0 + crop_h)
        clipped = visible_frac_x < 0.999 or visible_frac_y < 0.999
    else:
        width = max(1, int(round(draw_w)))
        height = max(1, int(round(draw_h)))
        # Centre inside the available area. Floor division rather than round so
        # centring is deterministic instead of depending on banker's rounding.
        # Oversized content stays centred and the driver clips the excess, which
        # at least keeps the middle of the page aligned.
        x = avail.x + (avail.w - width) // 2
        y = avail.y + (avail.h - height) // 2
        target = Rect(x, y, width, height)
        clipped = width > avail.w + 1 or height > avail.h + 1

    return Placement(target=target, source_box=source_box, rotate=rotate, clipped=clipped)


def plan_bands(height: int, width: int, channels: int = 3) -> list[tuple[int, int]]:
    """Split a placement height into ``(y0, y1)`` strips within the memory budget."""
    height = max(1, int(height))
    width = max(1, int(width))
    row_bytes = max(1, width * channels)
    rows = max(MIN_BAND_ROWS, int(BAND_BUDGET_BYTES // row_bytes))
    if rows >= height:
        return [(0, height)]
    bands: list[tuple[int, int]] = []
    y = 0
    while y < height:
        bands.append((y, min(height, y + rows)))
        y += rows
    return bands


def finish_band(image, options: PrintOptions, pad_top: int, pad_bottom: int):
    """Apply post-processing to a rendered band and trim the filter padding."""
    from PIL import Image, ImageOps

    if image.mode in ("RGBA", "LA", "PA"):
        # Printers have no alpha channel; flatten onto white so transparency
        # prints as paper rather than as black.
        background = Image.new("RGB", image.size, (255, 255, 255))
        alpha = image.getchannel("A") if "A" in image.getbands() else None
        background.paste(image.convert("RGB"), (0, 0), alpha)
        image = background
    elif image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    if options.sharpen:
        from PIL import ImageFilter

        image = image.filter(ImageFilter.UnsharpMask(radius=1.6, percent=95, threshold=3))

    if options.force_grayscale_render and image.mode != "L":
        image = ImageOps.grayscale(image)

    if pad_top or pad_bottom:
        top = pad_top
        bottom = image.height - pad_bottom
        if bottom > top:
            image = image.crop((0, top, image.width, bottom))
    return image
