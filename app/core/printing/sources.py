"""Page sources: anything that can hand back a resampled strip of a page.

Both implementations resample directly from their original data for every strip
rather than scaling once into an intermediate bitmap. That is what allows a
1200 dpi A4 page to be produced in 48 MB chunks with no visible seams.
"""

from __future__ import annotations

import contextlib
import math

from ..logging_setup import get as get_logger

log = get_logger("printing.sources")

#: Fallback pixel density for images that carry no DPI metadata. 96 matches what
#: Windows assumes for screen bitmaps, so "actual size" behaves predictably.
DEFAULT_IMAGE_DPI = 96.0


class SourceError(RuntimeError):
    """The file cannot be rendered, with a message worth showing the user."""


class PageSource:
    kind = "none"
    page_count = 0

    def page_size(self, index: int, rotate: int = 0) -> tuple[float, float]:
        raise NotImplementedError

    def source_dpi(self, index: int) -> tuple[float, float]:
        return (DEFAULT_IMAGE_DPI, DEFAULT_IMAGE_DPI)

    def render(
        self,
        index: int,
        out_w: int,
        out_h: int,
        source_box: tuple[float, float, float, float],
        rotate: int = 0,
    ):
        raise NotImplementedError

    def thumbnail(self, index: int = 0, max_px: int = 900):
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self) -> PageSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# --------------------------------------------------------------------------- #
# Raster images
# --------------------------------------------------------------------------- #


class ImageSource(PageSource):
    """Pillow backed. Multi frame TIFF and GIF are treated as multi page."""

    kind = "image"

    def __init__(self, path: str) -> None:
        from PIL import Image, ImageFile

        # Large scans are legitimate; refuse only the genuinely absurd.
        Image.MAX_IMAGE_PIXELS = 512_000_000
        ImageFile.LOAD_TRUNCATED_IMAGES = True

        self.path = path
        try:
            self._image = Image.open(path)
        except Exception as exc:
            raise SourceError(f"cannot open image: {exc}") from exc

        self.page_count = max(1, int(getattr(self._image, "n_frames", 1) or 1))
        self._frame_cache: dict[tuple[int, int], object] = {}
        self._current_frame = -1

    # -- frames ----------------------------------------------------------

    def _frame(self, index: int, rotate: int = 0):
        key = (index, rotate % 360)
        cached = self._frame_cache.get(key)
        if cached is not None:
            return cached

        from PIL import Image, ImageOps

        if self.page_count > 1 and self._current_frame != index:
            try:
                self._image.seek(index)
                self._current_frame = index
            except (EOFError, ValueError) as exc:
                raise SourceError(f"cannot read frame {index + 1}: {exc}") from exc

        frame = self._image
        with contextlib.suppress(Exception):
            frame = ImageOps.exif_transpose(frame) or frame

        if frame.mode in ("P", "PA"):
            frame = frame.convert("RGBA" if "transparency" in frame.info else "RGB")
        elif frame.mode == "CMYK":
            frame = frame.convert("RGB")
        elif frame.mode in ("I;16", "I", "F") or frame.mode == "1":
            frame = frame.convert("L")

        if rotate % 360:
            frame = frame.rotate(-(rotate % 360), expand=True, resample=Image.NEAREST)

        # Only the rotated variant is worth keeping; the raw frame is cheap to
        # re-fetch and holding both doubles peak memory on huge scans.
        self._frame_cache.clear()
        self._frame_cache[key] = frame
        return frame

    # -- geometry --------------------------------------------------------

    def page_size(self, index: int, rotate: int = 0) -> tuple[float, float]:
        frame = self._frame(index, 0)
        width, height = float(frame.width), float(frame.height)
        if rotate % 180:
            width, height = height, width
        return (width, height)

    def source_dpi(self, index: int) -> tuple[float, float]:
        info = getattr(self._image, "info", {}) or {}
        raw = info.get("dpi") or info.get("resolution")
        dpi_x = dpi_y = DEFAULT_IMAGE_DPI
        if isinstance(raw, (tuple, list)) and len(raw) >= 2:
            try:
                dpi_x, dpi_y = float(raw[0]), float(raw[1])
            except (TypeError, ValueError):
                dpi_x = dpi_y = DEFAULT_IMAGE_DPI
        elif isinstance(raw, (int, float)):
            dpi_x = dpi_y = float(raw)

        def sanitise(value: float) -> float:
            # Some cameras and scanners write nonsense here.
            if math.isnan(value) or not (1.0 <= value <= 6000.0):
                return DEFAULT_IMAGE_DPI
            # PNG stores density in pixels per metre, so 300 dpi comes back as
            # 299.9994. Snap to the integer the file clearly meant.
            if abs(value - round(value)) < 0.02:
                return float(round(value))
            return round(value, 2)

        return (sanitise(dpi_x), sanitise(dpi_y))

    # -- rendering -------------------------------------------------------

    def render(
        self,
        index: int,
        out_w: int,
        out_h: int,
        source_box: tuple[float, float, float, float],
        rotate: int = 0,
    ):
        from PIL import Image

        frame = self._frame(index, rotate)
        x0, y0, x1, y1 = source_box
        x0 = max(0.0, min(float(x0), frame.width - 1.0))
        y0 = max(0.0, min(float(y0), frame.height - 1.0))
        x1 = max(x0 + 1e-3, min(float(x1), float(frame.width)))
        y1 = max(y0 + 1e-3, min(float(y1), float(frame.height)))
        out_w = max(1, int(out_w))
        out_h = max(1, int(out_h))

        # Pillow resamples straight out of a floating point source box, so the
        # strip boundaries line up exactly with no accumulated rounding error.
        resample = Image.LANCZOS
        if out_w > (x1 - x0) * 3 or out_h > (y1 - y0) * 3:
            # Heavy upscale: bicubic avoids the ringing Lanczos produces.
            resample = Image.BICUBIC
        return frame.resize((out_w, out_h), resample=resample, box=(x0, y0, x1, y1))

    def thumbnail(self, index: int = 0, max_px: int = 900):
        frame = self._frame(min(index, self.page_count - 1), 0)
        scale = min(1.0, max_px / max(frame.width, frame.height))
        size = (max(1, int(frame.width * scale)), max(1, int(frame.height * scale)))
        from PIL import Image

        return frame.convert("RGB").resize(size, Image.LANCZOS)

    def close(self) -> None:
        self._frame_cache.clear()
        with contextlib.suppress(Exception):
            self._image.close()


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #


def _qimage_to_pil(image):
    """QImage to PIL, flattened onto white, without assuming a packed stride.

    QtPdf hands back ARGB32 in which everything the page did not paint is fully
    transparent. Dropping that alpha would turn the background of any PDF that
    relies on the paper being white into solid black, so it is composited over
    white first. Getting this wrong means a page of solid ink, so it is checked
    by the render suite.
    """
    from PIL import Image
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    if image.isNull():
        raise SourceError("PDF page rendered empty")

    if image.hasAlphaChannel():
        flat = QImage(image.size(), QImage.Format.Format_RGB888)
        flat.fill(Qt.GlobalColor.white)
        painter = QPainter(flat)
        painter.drawImage(0, 0, image)
        painter.end()
        image = flat
    elif image.format() != QImage.Format.Format_RGB888:
        image = image.convertToFormat(QImage.Format.Format_RGB888)

    width, height = image.width(), image.height()
    stride = image.bytesPerLine()
    raw = bytes(image.constBits())
    if stride == width * 3:
        return Image.frombuffer("RGB", (width, height), raw, "raw", "RGB", 0, 1)
    # Padded rows: copy line by line.
    packed = bytearray(width * height * 3)
    for row in range(height):
        start = row * stride
        packed[row * width * 3 : (row + 1) * width * 3] = raw[start : start + width * 3]
    return Image.frombuffer("RGB", (width, height), bytes(packed), "raw", "RGB", 0, 1)


#: Ceiling for one cached page bitmap, as RGB bytes. A4 renders exactly up to
#: about 740 dpi within this; beyond that the page is rasterised at the largest
#: size that fits and strips are enlarged from it.
PAGE_CACHE_BUDGET_BYTES = 160 * 1024 * 1024


def _resample_for(out_w: int, out_h: int, box_w: float, box_h: float):
    """Lanczos for reduction, bicubic for large enlargement (less ringing)."""
    from PIL import Image

    if out_w > box_w * 3 or out_h > box_h * 3:
        return Image.BICUBIC
    return Image.LANCZOS


class PdfSource(PageSource):
    """QtPdf (PDFium) backed.

    Each page is rasterised in a single call and strips are cut from that bitmap.
    The obvious alternative, asking QtPdf for each strip directly through
    ``scaledClipRect``, was measured and rejected: its rendering scale drifts
    with the clip offset by around 0.2 percent, which walks content several
    pixels down the page and puts a small step at every strip boundary. Cutting
    strips from one render is geometrically exact instead, and it also means a
    page used many times on one sheet, as N-up does, is rasterised once.

    When a page at full device resolution would exceed the cache budget it is
    rendered at the largest size that fits and strips are enlarged from there.
    The softening is far below what an inkjet can resolve, and the driver still
    receives data at its native resolution so its own halftoning is unaffected.
    """

    kind = "pdf"

    def __init__(self, path: str, password: str = "") -> None:
        from PySide6.QtPdf import QPdfDocument

        self.path = path
        self._doc = QPdfDocument()
        if password:
            self._doc.setPassword(password)
        status = self._doc.load(path)
        # PySide renames the "None" enumerator to "None_" because None is a
        # reserved word, so both spellings mean success.
        error_name = getattr(status, "name", str(status))
        if error_name not in ("None", "None_", "NoError"):
            mapping = {
                "IncorrectPassword": "the PDF is password protected",
                "FileNotFound": "the file is missing",
                "InvalidFileFormat": "the file is not a readable PDF",
                "UnsupportedSecurityScheme": "the PDF uses unsupported encryption",
            }
            raise SourceError(f"cannot open PDF: {mapping.get(error_name, error_name)}")
        self.page_count = max(0, int(self._doc.pageCount()))
        if self.page_count == 0:
            raise SourceError("the PDF contains no pages")
        self._cache = None
        self._cache_key: tuple | None = None
        #: Effective rasterisation resolution of the last page rendered, so the
        #: caller can report what actually happened rather than what was asked.
        self.last_render_scale = 1.0

    def page_size(self, index: int, rotate: int = 0) -> tuple[float, float]:
        size = self._doc.pagePointSize(int(index))
        width, height = float(size.width()), float(size.height())
        if width <= 0 or height <= 0:  # malformed page box
            width, height = 595.0, 842.0
        if rotate % 180:
            width, height = height, width
        return (width, height)

    def source_dpi(self, index: int) -> tuple[float, float]:
        # PDF user space is 1/72 inch, so the "pixels" we report are points.
        return (72.0, 72.0)

    #: Annotations and form field appearances are part of the document as far as
    #: a user is concerned, so they are rendered by default. A filled in form
    #: that prints blank is a bug, not a feature.
    render_annotations = True
    #: Let PDFium do the grey conversion when the job is monochrome. It is both
    #: faster than converting afterwards and better at preserving text contrast.
    render_grayscale = False

    def _rotation(self, rotate: int):
        from PySide6.QtPdf import QPdfDocumentRenderOptions

        rotation = QPdfDocumentRenderOptions.Rotation
        return {
            90: rotation.Clockwise90,
            180: rotation.Clockwise180,
            270: rotation.Clockwise270,
        }.get(rotate % 360, rotation.None_)

    def _flags(self):
        from PySide6.QtPdf import QPdfDocumentRenderOptions

        flag = QPdfDocumentRenderOptions.RenderFlag
        flags = flag(0)
        if self.render_annotations:
            flags |= flag.Annotations
        if self.render_grayscale:
            flags |= flag.Grayscale
        return flags

    def _page_bitmap(self, index: int, rotate: int, want_w: int, want_h: int):
        """Rasterise a whole page once, capped to the cache budget."""
        from PySide6.QtCore import QSize
        from PySide6.QtPdf import QPdfDocumentRenderOptions

        want_w = max(1, int(want_w))
        want_h = max(1, int(want_h))
        budget_px = max(1, PAGE_CACHE_BUDGET_BYTES // 3)
        scale = 1.0
        if want_w * want_h > budget_px:
            scale = math.sqrt(budget_px / float(want_w * want_h))
        cache_w = max(1, int(want_w * scale))
        cache_h = max(1, int(want_h * scale))

        key = (
            int(index), rotate % 360, cache_w, cache_h,
            bool(self.render_grayscale), bool(self.render_annotations),
        )
        if self._cache_key == key and self._cache is not None:
            return self._cache

        options = QPdfDocumentRenderOptions()
        options.setScaledSize(QSize(cache_w, cache_h))
        options.setRotation(self._rotation(rotate))
        options.setRenderFlags(self._flags())
        image = self._doc.render(int(index), QSize(cache_w, cache_h), options)

        # Drop the previous page before holding two large bitmaps at once.
        self._cache = None
        self._cache_key = None
        pil = _qimage_to_pil(image)
        del image
        if pil.size != (cache_w, cache_h):
            log.debug("pdf page came back %s, wanted %s", pil.size, (cache_w, cache_h))
        self._cache = pil
        self._cache_key = key
        self.last_render_scale = scale
        if scale < 1.0:
            log.info(
                "page %s rasterised at %.0f%% of requested resolution "
                "(%sx%s) to stay inside the %d MiB page budget",
                index + 1, scale * 100, cache_w, cache_h,
                PAGE_CACHE_BUDGET_BYTES // 1024 // 1024,
            )
        return pil

    def render(
        self,
        index: int,
        out_w: int,
        out_h: int,
        source_box: tuple[float, float, float, float],
        rotate: int = 0,
    ):
        out_w = max(1, int(out_w))
        out_h = max(1, int(out_h))
        page_w, page_h = self.page_size(index, rotate)
        x0, y0, x1, y1 = (float(v) for v in source_box)
        box_w = max(1e-6, x1 - x0)
        box_h = max(1e-6, y1 - y0)

        # Device size the whole page would occupy at this strip's scale. Every
        # strip of a placement yields the same value, so the cache is built once.
        full_w = int(round(out_w * page_w / box_w))
        full_h = int(round(out_h * page_h / box_h))
        page = self._page_bitmap(index, rotate, full_w, full_h)

        # Map the requested box from points into cache pixels.
        map_x = page.width / page_w
        map_y = page.height / page_h
        box = (
            max(0.0, x0 * map_x),
            max(0.0, y0 * map_y),
            min(float(page.width), x1 * map_x),
            min(float(page.height), y1 * map_y),
        )
        resample = _resample_for(out_w, out_h, box[2] - box[0], box[3] - box[1])
        return page.resize((out_w, out_h), resample=resample, box=box)

    def thumbnail(self, index: int = 0, max_px: int = 900):
        page_w, page_h = self.page_size(index, 0)
        scale = min(max_px / page_w, max_px / page_h)
        out_w = max(1, int(page_w * scale))
        out_h = max(1, int(page_h * scale))
        return self.render(index, out_w, out_h, (0.0, 0.0, page_w, page_h), 0)

    def release_cache(self) -> None:
        self._cache = None
        self._cache_key = None

    def close(self) -> None:
        self.release_cache()
        with contextlib.suppress(Exception):
            self._doc.close()


# --------------------------------------------------------------------------- #


def open_source(path: str, kind: str = "") -> PageSource:
    from ..util import classify

    kind = kind or classify(path)
    if kind == "pdf":
        return PdfSource(path)
    if kind == "image":
        return ImageSource(path)
    raise SourceError(f"no renderer for this file type ({kind})")


def probe(path: str, kind: str = "") -> dict:
    """Cheap metadata read for the queue list: page count and natural size."""
    from ..util import classify

    kind = kind or classify(path)
    info = {"kind": kind, "pages": 1, "width": 0.0, "height": 0.0, "error": ""}
    if kind == "text":
        return info
    if kind == "shell":
        info["pages"] = 0
        return info
    try:
        with open_source(path, kind) as source:
            info["pages"] = source.page_count
            width, height = source.page_size(0, 0)
            dpi_x, dpi_y = source.source_dpi(0)
            info["width"] = round(width / dpi_x * 25.4, 1)
            info["height"] = round(height / dpi_y * 25.4, 1)
    except Exception as exc:
        info["error"] = str(exc)
        info["pages"] = 0
    return info
