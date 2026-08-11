"""Builds a printer test page.

Useful for two things: confirming the printable area really is where the driver
says it is, and judging colour and grey reproduction on whatever paper is loaded.
The page is generated at the requested paper size so the marks land at known
distances from the edges.
"""

from __future__ import annotations

from pathlib import Path

from . import env
from .logging_setup import get as get_logger

log = get_logger("testpage")

DPI = 150


def build(width_mm: float = 210.0, height_mm: float = 297.0,
          printer: str = "", note: str = "") -> str:
    """Render the test page to a PNG and return its path."""
    from PIL import Image, ImageDraw, ImageFont

    width = int(round(width_mm / 25.4 * DPI))
    height = int(round(height_mm / 25.4 * DPI))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    accent = (91, 140, 255)
    violet = (176, 107, 255)
    ink = (26, 28, 36)

    def font(size: int):
        for name in ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    def mm(value: float) -> int:
        return int(round(value / 25.4 * DPI))

    # Full bleed border, 1 mm in. If the printer cannot reach it, the missing
    # edges tell you exactly how much of the sheet is unprintable.
    draw.rectangle([mm(1), mm(1), width - mm(1) - 1, height - mm(1) - 1],
                   outline=(190, 195, 210), width=max(1, mm(0.2)))
    draw.rectangle([mm(5), mm(5), width - mm(5) - 1, height - mm(5) - 1],
                   outline=ink, width=max(1, mm(0.3)))

    # Corner registration marks with their distance from the corner.
    for corner_x, corner_y, label_dx, label_dy in (
        (mm(5), mm(5), 6, 4), (width - mm(5), mm(5), -60, 4),
        (mm(5), height - mm(5), 6, -18), (width - mm(5), height - mm(5), -60, -18),
    ):
        arm = mm(8)
        draw.line([corner_x - arm, corner_y, corner_x + arm, corner_y], fill=accent, width=2)
        draw.line([corner_x, corner_y - arm, corner_x, corner_y + arm], fill=accent, width=2)
        draw.text((corner_x + label_dx, corner_y + label_dy), "5 mm",
                  fill=accent, font=font(13))

    # Centre cross and a diagonal pair, for skew.
    cx, cy = width // 2, height // 2
    draw.line([cx - mm(15), cy, cx + mm(15), cy], fill=violet, width=2)
    draw.line([cx, cy - mm(15), cx, cy + mm(15)], fill=violet, width=2)
    draw.ellipse([cx - mm(10), cy - mm(10), cx + mm(10), cy + mm(10)],
                 outline=violet, width=2)
    draw.line([mm(5), mm(5), width - mm(5), height - mm(5)], fill=(226, 230, 240), width=1)
    draw.line([width - mm(5), mm(5), mm(5), height - mm(5)], fill=(226, 230, 240), width=1)

    # Header
    draw.text((mm(10), mm(9)), "GlassPrint test page", fill=ink, font=font(30))
    subtitle = f"{width_mm:.0f} x {height_mm:.0f} mm at {DPI} dpi"
    if printer:
        subtitle += f"   |   {printer}"
    draw.text((mm(10), mm(17)), subtitle, fill=(96, 102, 120), font=font(15))
    if note:
        draw.text((mm(10), mm(22)), note, fill=(96, 102, 120), font=font(13))

    # Millimetre ruler along the top edge, so you can measure any scaling error.
    ruler_y = mm(30)
    draw.text((mm(10), ruler_y - mm(5)), "ruler, ticks every 10 mm",
              fill=(96, 102, 120), font=font(12))
    for millimetre in range(0, int(width_mm) - 8, 1):
        x = mm(10 + millimetre)
        if x > width - mm(10):
            break
        if millimetre % 10 == 0:
            draw.line([x, ruler_y, x, ruler_y + mm(5)], fill=ink, width=2)
            draw.text((x + 2, ruler_y + mm(5)), str(millimetre), fill=ink, font=font(11))
        elif millimetre % 5 == 0:
            draw.line([x, ruler_y, x, ruler_y + mm(3)], fill=ink, width=1)
        else:
            draw.line([x, ruler_y, x, ruler_y + mm(1.6)], fill=(120, 126, 145), width=1)

    # Grey ramp, in steps and as a smooth sweep.
    top = mm(48)
    band = mm(11)
    steps = 16
    step_w = (width - mm(20)) / steps
    draw.text((mm(10), top - mm(5)), "grey steps", fill=(96, 102, 120), font=font(12))
    for index in range(steps):
        shade = int(round(255 * (1 - index / (steps - 1))))
        x0 = mm(10) + int(index * step_w)
        draw.rectangle([x0, top, x0 + int(step_w) + 1, top + band], fill=(shade,) * 3)

    top += band + mm(4)
    draw.text((mm(10), top - mm(4)), "grey sweep", fill=(96, 102, 120), font=font(12))
    usable = width - mm(20)
    for offset in range(usable):
        shade = int(round(255 * (1 - offset / max(1, usable - 1))))
        draw.line([mm(10) + offset, top, mm(10) + offset, top + band], fill=(shade,) * 3)

    # Colour bars, then the same colours as light tints where ink starvation shows.
    top += band + mm(6)
    colours = [
        ("C", (0, 174, 239)), ("M", (236, 0, 140)), ("Y", (255, 241, 0)),
        ("K", (35, 31, 32)), ("R", (237, 28, 36)), ("G", (0, 166, 81)),
        ("B", (46, 49, 146)), ("A", accent), ("V", violet),
    ]
    draw.text((mm(10), top - mm(4)), "colour bars", fill=(96, 102, 120), font=font(12))
    bar_w = (width - mm(20)) / len(colours)
    for index, (label, colour) in enumerate(colours):
        x0 = mm(10) + int(index * bar_w)
        draw.rectangle([x0, top, x0 + int(bar_w) + 1, top + band], fill=colour)
        draw.text((x0 + 4, top + band + 2), label, fill=ink, font=font(12))
    top += band + mm(7)
    for index, (_, colour) in enumerate(colours):
        x0 = mm(10) + int(index * bar_w)
        for level, height_frac in ((0.25, 0.5), (0.1, 0.5)):
            tint = tuple(int(round(255 - (255 - channel) * level)) for channel in colour)
            y0 = top + int(band * (0 if height_frac == 0.5 and level == 0.25 else 0.5))
            draw.rectangle([x0, y0, x0 + int(bar_w) + 1, y0 + int(band * 0.5)], fill=tint)

    # Fine line and text resolution targets.
    top += band + mm(8)
    draw.text((mm(10), top - mm(4)), "line widths in dots at 150 dpi",
              fill=(96, 102, 120), font=font(12))
    x = mm(10)
    for thickness in (1, 1, 2, 2, 3, 4, 6, 8):
        draw.rectangle([x, top, x + thickness - 1, top + mm(10)], fill=ink)
        x += thickness + mm(2.2)
    for gap in (1, 2, 3, 4):
        for _repeat in range(6):
            draw.rectangle([x, top, x + gap - 1, top + mm(10)], fill=ink)
            x += gap * 2
        x += mm(2)

    top += mm(14)
    draw.text((mm(10), top), "Text size ladder", fill=(96, 102, 120), font=font(12))
    top += mm(5)
    for size in (22, 18, 15, 13, 11, 9, 8, 7, 6):
        draw.text((mm(10), top), f"{size}px  The quick brown fox jumps over the lazy dog "
                                 f"0123456789", fill=ink, font=font(size))
        top += size + mm(1.4)

    out = env.cache_dir() / "testpage.png"
    image.save(out, "PNG", dpi=(DPI, DPI))
    log.info("test page written to %s (%sx%s)", out, width, height)
    return str(out)


def write_probe_pdf(path: str) -> str:
    """Write a tiny one page PDF, used by the packaged build's self test.

    Kept here rather than in tools/ because it has to exist inside the frozen
    bundle: proving that QtPdf can rasterise a real document after packaging is
    the only way to catch a missing Qt Pdf plugin before a user does.
    """
    content = (
        "q 0.15 0.35 0.85 rg 72 400 200 120 re f Q\n"
        "q 0 0 0 rg BT /F1 24 Tf 72 300 Td (GlassPrint probe) Tj ET Q\n"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode("latin-1")

    target = Path(path)
    target.write_bytes(bytes(out))
    return str(target)


def build_for(printer: str, paper: tuple[float, float] | None = None) -> str:
    """Build a test page matching the printer's current paper size."""
    from . import printers as printer_api

    width_mm, height_mm = paper or (210.0, 297.0)
    if paper is None:
        try:
            caps = printer_api.capabilities(printer)
            sheet = caps.paper_by_id(caps.default_paper)
            if sheet and sheet.width_mm > 10 and sheet.height_mm > 10:
                width_mm, height_mm = sheet.width_mm, sheet.height_mm
        except Exception as exc:
            log.debug("cannot read paper size for the test page: %s", exc)
    return build(width_mm, height_mm, printer)
