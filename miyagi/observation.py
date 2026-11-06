"""Raw perception output: what the vision models saw in one frame."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class HandObs:
    points: np.ndarray  # (21, 2) isotropic coords, MediaPipe hand landmark order
    label: str = "hand"  # "Left" / "Right" (only used as a tracking key)
    score: float = 1.0


@dataclass
class Observation:
    t: float  # seconds (monotonic, client clock)
    aspect: float  # frame width / height
    face: np.ndarray | None = None  # (478, 2) MediaPipe face mesh incl. irises
    blendshapes: dict[str, float] = field(default_factory=dict)
    hands: list[HandObs] = field(default_factory=list)
    pose: np.ndarray | None = None  # (33, 3) x, y, visibility
