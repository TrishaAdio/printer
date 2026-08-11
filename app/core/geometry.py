"""Page geometry, shared by both printer backends.

Lives in its own module so the simulation backend never has to touch anything
that imports pywin32.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PageGeometry:
    """Real measurements of the sheet, in printer dots.

    ``printable_*`` is the area the driver will actually mark. ``offset_*`` is the
    unprintable margin at the top left of the physical sheet. Placing content
    without subtracting that offset is the single most common cause of output
    drifting down and to the right.
    """

    dpi_x: int = 300
    dpi_y: int = 300
    physical_w: int = 0
    physical_h: int = 0
    printable_w: int = 0
    printable_h: int = 0
    offset_x: int = 0
    offset_y: int = 0
    bpp: int = 24

    @property
    def physical_w_mm(self) -> float:
        return self.physical_w / self.dpi_x * 25.4 if self.dpi_x else 0.0

    @property
    def physical_h_mm(self) -> float:
        return self.physical_h / self.dpi_y * 25.4 if self.dpi_y else 0.0

    @property
    def landscape(self) -> bool:
        return self.physical_w > self.physical_h

    def to_dict(self) -> dict[str, Any]:
        return {
            "dpi_x": self.dpi_x,
            "dpi_y": self.dpi_y,
            "physical_w": self.physical_w,
            "physical_h": self.physical_h,
            "printable_w": self.printable_w,
            "printable_h": self.printable_h,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "width_mm": round(self.physical_w_mm, 1),
            "height_mm": round(self.physical_h_mm, 1),
        }
