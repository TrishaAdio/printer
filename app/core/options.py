"""Print option model and the capability descriptions that constrain it.

These are plain dataclasses on purpose: they cross the Python/QML boundary as
dicts, get written to SQLite as JSON, and are handed to a worker thread. Nothing
here may hold a Qt object or an OS handle.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

# Quality presets map to a render resolution. "max" means "ask the driver for the
# highest resolution it advertises", which is what the HD switch does.
QUALITY_DPI = {
    "draft": 150,
    "normal": 300,
    "high": 600,
    "hd": 0,     # 0 -> resolve to the printer's maximum
    "photo": 0,  # same, plus photo media / dithering / ICM tweaks
}

SCALE_MODES = ("fit", "fill", "actual", "custom")
DUPLEX_MODES = ("simplex", "vertical", "horizontal")
ORIENTATIONS = ("auto", "portrait", "landscape")
SUBSETS = ("all", "odd", "even")
NUP_CHOICES = (1, 2, 4, 6, 9, 16)


@dataclass
class Paper:
    id: int
    name: str
    width_mm: float = 0.0
    height_mm: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NamedId:
    id: int
    name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Resolution:
    x: int
    y: int

    @property
    def label(self) -> str:
        return f"{self.x} dpi" if self.x == self.y else f"{self.x} x {self.y} dpi"

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "label": self.label}


@dataclass
class Capabilities:
    """Everything the driver will admit to supporting."""

    printer: str = ""
    driver: str = ""
    port: str = ""
    manufacturer: str = ""
    model: str = ""
    color: bool = True
    max_copies: int = 99
    collate: bool = True
    duplex: bool = False
    staple: bool = False
    landscape: bool = True
    print_rate_ppm: int = 0
    papers: list[Paper] = field(default_factory=list)
    bins: list[NamedId] = field(default_factory=list)
    media_types: list[NamedId] = field(default_factory=list)
    resolutions: list[Resolution] = field(default_factory=list)
    media_ready: list[str] = field(default_factory=list)
    default_paper: int = 0
    default_bin: int = 0
    default_media: int = 0
    default_orientation: int = 1
    default_dpi: int = 300
    max_dpi: int = 600
    is_virtual: bool = False   # PDF writers, XPS, OneNote - no physical sheet
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["papers"] = [p.to_dict() for p in self.papers]
        data["bins"] = [b.to_dict() for b in self.bins]
        data["media_types"] = [m.to_dict() for m in self.media_types]
        data["resolutions"] = [r.to_dict() for r in self.resolutions]
        return data

    def paper_by_id(self, paper_id: int) -> Paper | None:
        for paper in self.papers:
            if paper.id == paper_id:
                return paper
        return None

    def clamp_dpi(self, dpi: int) -> int:
        """Snap a requested DPI to something the driver actually offers."""
        if not self.resolutions:
            return max(72, min(dpi, self.max_dpi or 600))
        exact = [r for r in self.resolutions if r.x == dpi]
        if exact:
            return dpi
        usable = sorted({r.x for r in self.resolutions})
        # Highest advertised resolution that does not exceed the request.
        below = [r for r in usable if r <= dpi]
        return below[-1] if below else usable[0]


@dataclass
class PrinterInfo:
    name: str = ""
    driver: str = ""
    port: str = ""
    comment: str = ""
    location: str = ""
    is_default: bool = False
    status_flags: int = 0
    status: str = "ready"        # ready | busy | warning | error | offline | paused
    status_text: str = "Ready"
    jobs: int = 0
    is_virtual: bool = False
    shared: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PrintOptions:
    """The full option surface, resolved per job."""

    printer: str = ""
    copies: int = 1
    collate: bool = True
    color: bool = True
    duplex: str = "simplex"
    manual_duplex: bool = False       # odd pass, prompt, even pass
    orientation: str = "auto"
    paper_size: int = 0               # DMPAPER_* id, 0 keeps the driver default
    paper_source: int = 0             # bin / tray id
    media_type: int = 0               # plain, photo, ...
    quality: str = "normal"
    render_dpi: int = 0               # 0 derives from quality
    scale_mode: str = "fit"
    scale_percent: int = 100
    borderless: bool = False
    extra_margin_mm: float = 0.0
    nup: int = 1
    page_range: str = ""
    page_subset: str = "all"
    reverse: bool = False
    auto_rotate: bool = True
    sharpen: bool = False
    force_grayscale_render: bool = False
    separate_jobs: bool = True
    dry_run: bool = False
    # Text specific
    text_font: str = "Consolas"
    text_point_size: float = 10.0
    text_header: bool = True
    text_wrap: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PrintOptions:
        data = data or {}
        known = {f.name for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        for key, value in data.items():
            if key in known:
                kwargs[key] = value
        obj = cls(**kwargs)
        obj.normalise()
        return obj

    def copy(self) -> PrintOptions:
        return PrintOptions.from_dict(self.to_dict())

    def normalise(self) -> None:
        """Coerce whatever arrived from QML or an old settings file into range."""
        try:
            self.copies = max(1, min(int(self.copies), 999))
        except (TypeError, ValueError):
            self.copies = 1
        if self.duplex not in DUPLEX_MODES:
            self.duplex = "simplex"
        if self.orientation not in ORIENTATIONS:
            self.orientation = "auto"
        if self.scale_mode not in SCALE_MODES:
            self.scale_mode = "fit"
        if self.page_subset not in SUBSETS:
            self.page_subset = "all"
        if self.quality not in QUALITY_DPI:
            self.quality = "normal"
        try:
            self.nup = int(self.nup)
        except (TypeError, ValueError):
            self.nup = 1
        if self.nup not in NUP_CHOICES:
            self.nup = 1
        try:
            self.scale_percent = max(10, min(int(self.scale_percent), 400))
        except (TypeError, ValueError):
            self.scale_percent = 100
        try:
            self.render_dpi = max(0, min(int(self.render_dpi), 4800))
        except (TypeError, ValueError):
            self.render_dpi = 0
        try:
            self.extra_margin_mm = max(0.0, min(float(self.extra_margin_mm), 50.0))
        except (TypeError, ValueError):
            self.extra_margin_mm = 0.0
        try:
            self.text_point_size = max(5.0, min(float(self.text_point_size), 48.0))
        except (TypeError, ValueError):
            self.text_point_size = 10.0
        for flag in (
            "collate", "color", "manual_duplex", "borderless", "reverse",
            "auto_rotate", "sharpen", "force_grayscale_render", "separate_jobs",
            "dry_run", "text_header", "text_wrap",
        ):
            setattr(self, flag, bool(getattr(self, flag)))

    def effective_dpi(self, caps: Capabilities | None) -> int:
        """Resolve quality + explicit override into a real render resolution."""
        wanted = int(self.render_dpi or 0)
        if wanted <= 0:
            wanted = QUALITY_DPI.get(self.quality, 300)
        if wanted <= 0:  # hd / photo
            wanted = caps.max_dpi if caps else 600
        if caps:
            wanted = caps.clamp_dpi(wanted)
        return max(72, wanted)

    def constrain_to(self, caps: Capabilities) -> list[str]:
        """Drop anything this printer cannot do, and say what was dropped.

        Returned strings are shown to the user, because silently ignoring a
        requested option is how people end up with 200 wrong pages.
        """
        notes: list[str] = []
        if not caps.color and self.color:
            self.color = False
            notes.append("Printer is monochrome, colour disabled")
        if self.duplex != "simplex" and not caps.duplex:
            notes.append(
                "Driver reports no automatic duplex, switched to manual two-sided"
            )
            self.manual_duplex = True
            self.duplex = "simplex"
        if caps.max_copies and self.copies > caps.max_copies:
            notes.append(
                f"Driver caps copies at {caps.max_copies}, extra copies will be looped"
            )
        if self.paper_size and caps.papers and not caps.paper_by_id(self.paper_size):
            notes.append("Selected paper size is not offered, using driver default")
            self.paper_size = 0
        if self.paper_source and caps.bins and all(
            b.id != self.paper_source for b in caps.bins
        ):
            notes.append("Selected tray is not available, using driver default")
            self.paper_source = 0
        if self.media_type and caps.media_types and all(
            m.id != self.media_type for m in caps.media_types
        ):
            notes.append("Selected media type is not available, using driver default")
            self.media_type = 0
        if self.orientation == "landscape" and not caps.landscape:
            notes.append("Driver reports no landscape support")
            self.orientation = "portrait"
        return notes
