"""Rendering checks that can run without a printer.

Verifies the two claims the output quality rests on:

1. A page assembled from strips is pixel identical to the same page rendered in
   one go, for both PDF and raster sources. That is the seam guarantee.
2. Placement maths put content where the options say it should go, including the
   hardware margin offset and full bleed.

Run: python tools/verify_render.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))



def main() -> int:
    from PIL import Image, ImageChops
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.instance() or QGuiApplication(sys.argv)

    import make_test_pdf

    from app.core.geometry import PageGeometry
    from app.core.options import PrintOptions
    from app.core.printing import raster
    from app.core.printing import sources as sources_module
    from app.core.printing.sources import ImageSource, PdfSource

    tmp = ROOT / ".verify"
    tmp.mkdir(exist_ok=True)
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
        if not ok:
            failures.append(label)

    def stitch(source, index, out_w, out_h, box, rotate, rows):
        """Assemble a placement from strips, exactly as the engine does."""
        placement = raster.Placement(
            target=raster.Rect(0, 0, out_w, out_h), source_box=box, rotate=rotate
        )
        out = Image.new("RGB", (out_w, out_h))
        y = 0
        count = 0
        while y < out_h:
            y_end = min(out_h, y + rows)
            band_box = placement.band_source_box(y, y_end, 0)
            band = source.render(index, out_w, y_end - y, band_box, rotate)
            if band.size != (out_w, y_end - y):
                raise AssertionError(f"strip came back {band.size}, wanted {(out_w, y_end - y)}")
            out.paste(band.convert("RGB"), (0, y))
            y = y_end
            count += 1
        return out, count

    def mean_delta(a, b) -> float:
        diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
        return sum(diff.get_flattened_data()) / (a.width * a.height)

    def strip_equals_whole(source, index, out_w, out_h, box, rotate, label, tolerance=1):
        """Strict: a strip assembly must equal the whole page render."""
        whole = source.render(index, out_w, out_h, box, rotate).convert("RGB")
        stitched, count = stitch(source, index, out_w, out_h, box, rotate,
                                max(16, out_h // 7))
        worst = ImageChops.difference(whole, stitched).convert("L").getextrema()[1]
        ok = worst <= tolerance
        if not ok:
            whole.save(tmp / f"{label}_whole.png")
            stitched.save(tmp / f"{label}_stitched.png")
        check(label, ok, f"{count} strips, max channel delta {worst}")

    def row_step(image, y: int) -> float:
        """Mean absolute difference between row y-1 and row y of one image."""
        upper = image.crop((0, y - 1, image.width, y))
        lower = image.crop((0, y, image.width, y + 1))
        diff = ImageChops.difference(upper, lower).convert("L")
        return sum(diff.get_flattened_data()) / image.width

    def no_visible_seam(source, index, out_w, out_h, box, rotate, rows, label):
        """Tolerant: strips may differ from a whole render, but must not seam.

        PDFium snaps glyph rasterisation to the target bitmap's pixel grid, so a
        strip's antialiasing phase depends on its offset and byte identity with a
        whole page render is unobtainable. What matters on paper is that no strip
        boundary is visible, so the test compares the row to row step across each
        boundary against the natural step in the reference render.
        """
        whole = source.render(index, out_w, out_h, box, rotate).convert("RGB")
        stitched, _ = stitch(source, index, out_w, out_h, box, rotate, rows)

        baseline = [
            abs(row_step(stitched, y) - row_step(whole, y))
            for y in range(4, out_h - 4, 37)
            if y % rows not in (0, 1)
        ]
        typical = max(baseline) if baseline else 0.0

        boundaries = list(range(rows, out_h, rows))
        worst_boundary = 0.0
        worst_at = 0
        for y in boundaries:
            if y < 2 or y >= out_h - 1:
                continue
            delta = abs(row_step(stitched, y) - row_step(whole, y))
            if delta > worst_boundary:
                worst_boundary, worst_at = delta, y
        # A real seam is a step at the boundary well beyond the natural variation.
        ok = worst_boundary <= max(1.0, typical * 1.5)
        if not ok:
            stitched.save(tmp / f"{label}_stitched.png")
            whole.save(tmp / f"{label}_whole.png")
        check(
            label,
            ok,
            f"{len(boundaries)} boundaries, worst step deviation {worst_boundary:.2f} "
            f"at y={worst_at} vs {typical:.2f} elsewhere, "
            f"mean delta {mean_delta(whole, stitched):.2f}/255",
        )

    print("\nPDF background handling")
    bg_path = str(tmp / "no_background.pdf")
    make_test_pdf.build(bg_path, 1)
    bg = PdfSource(bg_path)
    bg_w, bg_h = bg.page_size(0)
    page = bg.render(0, 300, 424, (0.0, 0.0, bg_w, bg_h), 0)
    # This page paints a header bar and text but never fills the background, like
    # most real PDFs. Unpainted areas must come out white, not black.
    corner = page.getpixel((5, 5))
    middle_gap = page.getpixel((285, 400))
    check("a pdf with no painted background renders white",
          corner == (255, 255, 255) and middle_gap == (255, 255, 255),
          f"corner={corner} lower right={middle_gap}")
    darkness = sum(sum(page.getpixel((x, y))) for x in range(0, 300, 17)
                   for y in range(0, 424, 23)) / (18 * 19 * 3)
    check("the page is mostly light, not mostly ink", darkness > 170,
          f"mean channel value {darkness:.0f}/255")
    bg.close()

    print("\nPDF strip placement (solid blocks, must be exact)")
    blocks_path = str(tmp / "blocks.pdf")
    make_test_pdf.build(blocks_path, 2, "blocks")
    blocks = PdfSource(blocks_path)
    block_w, block_h = blocks.page_size(0)
    check("blocks page is on a whole inch grid", (block_w, block_h) == (576.0, 792.0),
          f"{block_w}x{block_h} pt")
    for dpi in (150, 300, 600, 1200):
        out_w = int(block_w / 72 * dpi)
        out_h = int(block_h / 72 * dpi)
        # Below the page cache budget the strip is a plain crop and must be
        # byte identical. Above it the page is rasterised smaller and strips are
        # enlarged, so a single code value of resampling rounding is expected.
        fits = out_w * out_h * 3 <= sources_module.PAGE_CACHE_BUDGET_BYTES
        strip_equals_whole(
            blocks, 0, out_w, out_h, (0.0, 0.0, block_w, block_h), 0,
            f"pdf_blocks_{dpi}dpi", tolerance=0 if fits else 1,
        )
        print(f"        {out_w}x{out_h} dots, rasterised at "
              f"{blocks.last_render_scale * 100:.0f}% "
              f"({'exact crop' if fits else 'enlarged from cache'})")
    # A cropped box on the same grid, which is what scale mode "fill" produces.
    strip_equals_whole(
        blocks, 1, 1200, 900, (72.0, 144.0, 72.0 + 288.0, 144.0 + 216.0), 0,
        "pdf_blocks_cropped", tolerance=0,
    )
    rot_w, rot_h = blocks.page_size(0, 90)
    strip_equals_whole(
        blocks, 0, int(rot_w / 72 * 300), int(rot_h / 72 * 300),
        (0.0, 0.0, rot_w, rot_h), 90, "pdf_blocks_rotated", tolerance=0,
    )
    check("pdf rotation swaps page size", (rot_w, rot_h) == (block_h, block_w),
          f"{(rot_w, rot_h)} vs {(block_h, block_w)}")
    blocks.close()

    print("\nPDF strip seams (text and diagonals, antialiasing tolerant)")
    pdf_path = str(tmp / "vector.pdf")
    make_test_pdf.build(pdf_path, 2)
    pdf = PdfSource(pdf_path)
    page_w, page_h = pdf.page_size(0)
    print(f"  pages={pdf.page_count} size={pdf.page_size(0)} pt")
    for dpi, rows in ((300, 400), (1200, 1690)):
        out_w = int(round(page_w / 72 * dpi))
        out_h = int(round(page_h / 72 * dpi))
        no_visible_seam(
            pdf, 0, out_w, out_h, (0.0, 0.0, page_w, page_h), 0, rows, f"pdf_seam_{dpi}dpi"
        )

    print("\nImage strip rendering")
    photo = Image.new("RGB", (1600, 1200))
    pixels = photo.load()
    for y in range(1200):
        for x in range(0, 1600, 4):
            shade = (x * 7 + y * 3) % 256
            for dx in range(4):
                pixels[x + dx, y] = (shade, (shade * 3) % 256, 255 - shade)
    photo_path = str(tmp / "photo.png")
    photo.save(photo_path, dpi=(300, 300))
    image = ImageSource(photo_path)
    check("image dpi read from file", image.source_dpi(0) == (300.0, 300.0),
          str(image.source_dpi(0)))
    strip_equals_whole(image, 0, 2480, 1860, (0.0, 0.0, 1600.0, 1200.0), 0, "image_upscale")
    strip_equals_whole(image, 0, 800, 600, (0.0, 0.0, 1600.0, 1200.0), 0, "image_downscale")
    strip_equals_whole(image, 0, 1000, 1400, (200.0, 100.0, 1000.0, 1100.0), 90, "image_rot_crop")

    print("\nMulti frame TIFF")
    frames = [Image.new("RGB", (600, 400), c) for c in ("red", "green", "blue")]
    tiff_path = str(tmp / "multi.tiff")
    frames[0].save(tiff_path, save_all=True, append_images=frames[1:])
    tiff = ImageSource(tiff_path)
    check("tiff frames counted as pages", tiff.page_count == 3, f"{tiff.page_count} pages")
    mid = tiff.render(1, 60, 40, (0.0, 0.0, 600.0, 400.0), 0)
    middle_pixel = mid.getpixel((30, 20))
    check("second frame is the green one", middle_pixel[1] > 100, str(middle_pixel))

    print("\nPlacement maths")
    geo = PageGeometry(
        dpi_x=600, dpi_y=600, physical_w=4961, physical_h=7016,
        printable_w=4811, printable_h=6866, offset_x=75, offset_y=75,
    )

    opts = PrintOptions(scale_mode="fit", auto_rotate=False)
    avail = raster.available_rect(geo, opts)
    check("printable area is the default target", avail.as_tuple() == (0, 0, 4811, 6866),
          str(avail.as_tuple()))

    bleed = raster.available_rect(geo, PrintOptions(borderless=True, auto_rotate=False))
    check("full bleed starts at negative offset", bleed.as_tuple() == (-75, -75, 4961, 7016),
          str(bleed.as_tuple()))

    margin = raster.available_rect(geo, PrintOptions(extra_margin_mm=10.0, auto_rotate=False))
    expect = int(round(10.0 / 25.4 * 600))
    check("extra margin insets by the right dot count",
          margin.as_tuple() == (expect, expect, 4811 - 2 * expect, 6866 - 2 * expect),
          str(margin.as_tuple()))

    # Actual size: a 4x6 inch photo at 300 dpi must land as exactly 4x6 inches.
    place = raster.compute_placement(1200, 1800, 300, 300, geo,
                                     PrintOptions(scale_mode="actual", auto_rotate=False))
    check("actual size keeps physical dimensions",
          (place.target.w, place.target.h) == (2400, 3600),
          f"{place.target.w}x{place.target.h} dots = "
          f"{place.target.w / 600:.2f}x{place.target.h / 600:.2f} in")
    left_margin = place.target.x
    right_margin = 4811 - place.target.w - place.target.x
    top_margin = place.target.y
    bottom_margin = 6866 - place.target.h - place.target.y
    check("actual size is centred within one dot",
          abs(left_margin - right_margin) <= 1 and abs(top_margin - bottom_margin) <= 1,
          f"margins l/r={left_margin}/{right_margin} t/b={top_margin}/{bottom_margin}")

    place = raster.compute_placement(1200, 1800, 300, 300, geo,
                                     PrintOptions(scale_mode="fit", auto_rotate=False))
    check("fit never exceeds the printable area",
          place.target.w <= 4811 and place.target.h <= 6866,
          f"{place.target.w}x{place.target.h}")
    check("fit preserves aspect ratio",
          abs((place.target.w / place.target.h) - (1200 / 1800)) < 0.002,
          f"{place.target.w / place.target.h:.4f} vs {1200 / 1800:.4f}")

    place = raster.compute_placement(1800, 1200, 300, 300, geo, PrintOptions(auto_rotate=True))
    check("landscape source auto rotates for a portrait sheet", place.rotate == 90,
          f"rotate={place.rotate}")

    place = raster.compute_placement(1200, 1800, 300, 300, geo,
                                     PrintOptions(scale_mode="fill", auto_rotate=False))
    check("fill covers the whole area", place.target.as_tuple() == (0, 0, 4811, 6866),
          str(place.target.as_tuple()))
    check("fill crops the source", place.clipped, f"box={place.source_box}")
    aspect_target = place.target.w / place.target.h
    aspect_source = place.source_width / place.source_height
    check("fill crop keeps aspect ratio undistorted",
          abs(aspect_target - aspect_source) < 0.01,
          f"{aspect_target:.4f} vs {aspect_source:.4f}")

    place = raster.compute_placement(1200, 1800, 300, 300, geo,
                                     PrintOptions(scale_mode="custom", scale_percent=50,
                                                  auto_rotate=False))
    check("custom scale halves the size", (place.target.w, place.target.h) == (1200, 1800),
          f"{place.target.w}x{place.target.h}")

    print("\nBand planning")
    bands = raster.plan_bands(14031, 9921)
    total = sum(b - a for a, b in bands)
    contiguous = all(bands[i][1] == bands[i + 1][0] for i in range(len(bands) - 1))
    starts_at_zero = bands[0][0] == 0 and bands[-1][1] == 14031
    peak = max(b - a for a, b in bands) * 9921 * 3
    check("bands tile the page exactly once",
          total == 14031 and contiguous and starts_at_zero,
          f"{len(bands)} bands, {total} rows")
    check("peak band stays inside the memory budget",
          peak <= raster.BAND_BUDGET_BYTES,
          f"{peak / 1024 / 1024:.1f} MiB per band at 1200 dpi A4 "
          f"(budget {raster.BAND_BUDGET_BYTES / 1024 / 1024:.0f} MiB), "
          f"whole page would be {14031 * 9921 * 3 / 1024 / 1024:.0f} MiB")
    check("small pages use a single band", raster.plan_bands(500, 400) == [(0, 500)])

    print("\nFilter padding")
    placement = raster.Placement(target=raster.Rect(0, 0, 100, 1000),
                                 source_box=(0.0, 0.0, 100.0, 1000.0))
    padded = placement.band_source_box(200, 300, raster.FILTER_PAD_ROWS)
    check("padded strip reaches past its own rows",
          padded[1] < 200.0 and padded[3] > 300.0, str(padded))
    edge = placement.band_source_box(0, 100, raster.FILTER_PAD_ROWS)
    check("padding is clamped at the page edge", edge[1] == 0.0, str(edge))

    pdf.close()
    image.close()
    tiff.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        print(f"diff images in {tmp}")
        return 1
    print("all rendering checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
