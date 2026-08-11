"""Emit a small multi page vector PDF used by the rendering checks.

Hand written so the checks do not need a PDF library. Vector content matters
here: it is what proves strips are rasterised at final resolution rather than
cut out of an upscaled bitmap.
"""

from __future__ import annotations

import sys
from pathlib import Path

PAGE_W, PAGE_H = 595, 842  # A4 in points


#: The blocks page is deliberately 8 x 11 inches on a 1 inch grid. Every edge
#: then falls on a whole device pixel at 150, 300, 600 and 1200 dpi, so there is
#: no antialiasing anywhere and a strip must match a whole page render byte for
#: byte. On a page whose edges land on fractional pixels, that is impossible and
#: the test would only be measuring the rasteriser's edge blending.
BLOCK_PAGE_W, BLOCK_PAGE_H = 576, 792
BLOCK_STEP = 72


def _blocks_content(index: int) -> str:
    lines = ["q"]
    palette = [
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.6, 0.0), (0.0, 0.0, 1.0),
        (1.0, 1.0, 0.0), (0.0, 0.8, 0.8), (0.6, 0.0, 0.6), (0.4, 0.4, 0.4),
    ]
    for row in range(BLOCK_PAGE_H // BLOCK_STEP):
        for column in range(BLOCK_PAGE_W // BLOCK_STEP):
            colour = palette[(row * 3 + column + index) % len(palette)]
            lines.append("{:.3f} {:.3f} {:.3f} rg".format(*colour))
            lines.append(
                f"{column * BLOCK_STEP} {row * BLOCK_STEP} {BLOCK_STEP} {BLOCK_STEP} re f"
            )
    lines.append("Q")
    return "\n".join(lines)


def _page_content(index: int) -> str:
    lines = [
        "q",
        "0.15 0.35 0.85 rg",
        f"40 {PAGE_H - 120} 515 60 re f",   # header bar
        "1 1 1 rg",
        f"BT /F1 28 Tf 60 {PAGE_H - 100} Td (GlassPrint page {index + 1}) Tj ET",
        "Q",
        "q 0 0 0 rg",
    ]
    # Dense horizontal rules: any band seam or vertical drift shows up here.
    y = PAGE_H - 160
    row = 0
    while y > 80:
        lines.append(f"BT /F1 9 Tf 45 {y} Td (row {row:03d} " + "-" * 60 + ") Tj ET")
        y -= 11
        row += 1
    lines.append("Q")
    # Thin diagonals catch resampling artefacts.
    lines.append("q 0.9 0.2 0.2 RG 0.6 w")
    for step in range(0, 12):
        x = 45 + step * 45
        lines.append(f"{x} 60 m {x + 40} 780 l S")
    lines.append("Q")
    return "\n".join(lines)


def build(path: str, pages: int = 2, style: str = "dense") -> str:
    objects: list[bytes] = []

    def add(body: str) -> int:
        objects.append(body.encode("latin-1"))
        return len(objects)  # 1 based object number

    font_num = None
    content_nums = []
    page_nums = []

    # Reserve: 1 = catalog, 2 = pages tree. Build the rest first, then patch.
    objects.append(b"")  # placeholder for catalog
    objects.append(b"")  # placeholder for pages tree
    font_num = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    blocks = style == "blocks"
    painter = _blocks_content if blocks else _page_content
    width = BLOCK_PAGE_W if blocks else PAGE_W
    height = BLOCK_PAGE_H if blocks else PAGE_H
    for index in range(pages):
        stream = painter(index)
        content_nums.append(
            add(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        )

    for index in range(pages):
        page_nums.append(
            add(
                "<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {width} {height}] "
                f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
                f"/Contents {content_nums[index]} 0 R >>"
            )
        )

    kids = " ".join(f"{num} 0 R" for num in page_nums)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode("latin-1")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode("latin-1")

    Path(path).write_bytes(bytes(out))
    return path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "test.pdf"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    kind = sys.argv[3] if len(sys.argv) > 3 else "dense"
    print("wrote", build(target, count, kind))
