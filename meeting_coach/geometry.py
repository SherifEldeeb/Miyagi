"""Small 2-D geometry helpers.

All internal coordinates are *isotropic*: ``x`` is multiplied by the frame
aspect ratio (width / height) so one unit means "one frame height" on both
axes. That keeps distances and ratios meaningful regardless of camera shape.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        # Coerce numpy scalars so boxes are always JSON-serialisable.
        for name in ("x0", "y0", "x1", "y1"):
            object.__setattr__(self, name, float(getattr(self, name)))

    @classmethod
    def around(cls, pts: np.ndarray) -> Box:
        pts = np.asarray(pts, dtype=np.float32)
        return cls(
            float(pts[:, 0].min()),
            float(pts[:, 1].min()),
            float(pts[:, 0].max()),
            float(pts[:, 1].max()),
        )

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def scale(self, fx: float, fy: float | None = None) -> Box:
        """Scale about the centre."""
        fy = fx if fy is None else fy
        hw, hh = self.w * fx / 2, self.h * fy / 2
        return Box(self.cx - hw, self.cy - hh, self.cx + hw, self.cy + hh)

    def pad(self, dx: float, dy: float | None = None) -> Box:
        dy = dx if dy is None else dy
        return Box(self.x0 - dx, self.y0 - dy, self.x1 + dx, self.y1 + dy)

    def union(self, other: Box) -> Box:
        return Box(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def contains(self, pts: np.ndarray) -> np.ndarray:
        pts = np.atleast_2d(np.asarray(pts))
        return (
            (pts[:, 0] >= self.x0)
            & (pts[:, 0] <= self.x1)
            & (pts[:, 1] >= self.y0)
            & (pts[:, 1] <= self.y1)
        )

    def to_normalized(self, aspect: float) -> dict[str, float]:
        """Convert to the client's normalised ``{x, y, w, h}`` in [0, 1]."""
        x0 = min(max(self.x0 / aspect, 0.0), 1.0)
        x1 = min(max(self.x1 / aspect, 0.0), 1.0)
        y0 = min(max(self.y0, 0.0), 1.0)
        y1 = min(max(self.y1, 0.0), 1.0)
        return {"x": round(x0, 4), "y": round(y0, 4), "w": round(x1 - x0, 4), "h": round(y1 - y0, 4)}


def dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(math.hypot(float(a[0] - b[0]), float(a[1] - b[1])))
