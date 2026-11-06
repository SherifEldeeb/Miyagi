"""Turn raw landmarks into body *zones* and measurements the detectors use.

Zones (all in isotropic coords, see geometry.py):

    hair   - above the forehead / top of head
    face   - eyes, nose, cheeks (upper and middle face)
    mouth  - lips
    beard  - lower face: jaw, chin, lower cheeks
    neck   - below the chin down towards the shoulders
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .geometry import Box, dist
from .observation import HandObs, Observation

# MediaPipe face-mesh indices
FOREHEAD_TOP, CHIN, CHEEK_L, CHEEK_R, NOSE_TIP = 10, 152, 234, 454, 1
UPPER_LIP, LOWER_LIP, MOUTH_L, MOUTH_R = 13, 14, 61, 291
EYE_A_OUTER, EYE_A_INNER, EYE_B_INNER, EYE_B_OUTER = 33, 133, 362, 263
IRIS_CENTERS = (468, 473)
CENTER_POINTS = [NOSE_TIP, EYE_A_OUTER, EYE_B_OUTER, CHIN]

# MediaPipe hand indices: fingertips and the joint just below each tip.
HAND_CONTACT_POINTS = [4, 8, 12, 16, 20, 3, 7, 11, 15, 19]
# Fingertips are what actually touch; distal joints count half.
CONTACT_WEIGHTS = np.array([1.0] * 5 + [0.5] * 5, dtype=np.float32)
WRIST, MIDDLE_MCP = 0, 9

# MediaPipe pose indices
NOSE_P, SHOULDER_L, SHOULDER_R, ELBOW_L, ELBOW_R, WRIST_L, WRIST_R = 0, 11, 12, 13, 14, 15, 16

ZONE_PRIORITY = ["mouth", "beard", "neck", "face", "hair"]

# How long a face may be "remembered" when the mesh drops out (a hand covering
# the face often makes the face detector lose it - exactly when we need it).
FACE_MEMORY_S = 0.8


@dataclass
class FaceFeat:
    box: Box
    fw: float  # face width (cheek to cheek)
    fh: float  # face height (forehead to chin)
    center: np.ndarray
    zones: dict[str, Box]
    yaw: float  # nose offset from the cheek midpoint, in half face widths (~sin(yaw))
    pitch: float  # (nose - eyes) / (chin - eyes) vertical ratio
    roll_deg: float
    gaze: float | None  # horizontal iris position in eye, 0..1 (0.5 = centred)
    fresh: bool = True  # False when this is a remembered face


@dataclass
class HandFeat:
    key: str
    points: np.ndarray
    contact: np.ndarray  # fingertips + distal joints
    scale: float  # wrist -> middle knuckle
    center: np.ndarray


@dataclass
class Features:
    t: float
    aspect: float
    face: FaceFeat | None
    hands: list[HandFeat] = field(default_factory=list)
    pose: np.ndarray | None = None
    blendshapes: dict[str, float] = field(default_factory=dict)

    def shoulders(self, min_vis: float = 0.5) -> tuple[np.ndarray, float] | None:
        """(midpoint, width) of the shoulders, if both are visible."""
        if self.pose is None:
            return None
        l, r = self.pose[SHOULDER_L], self.pose[SHOULDER_R]
        if l[2] < min_vis or r[2] < min_vis:
            return None
        return (l[:2] + r[:2]) / 2, dist(l, r)


def _gaze(face: np.ndarray) -> float | None:
    if face.shape[0] <= max(IRIS_CENTERS):
        return None
    eyes = [(face[EYE_A_OUTER], face[EYE_A_INNER]), (face[EYE_B_INNER], face[EYE_B_OUTER])]
    values = []
    for iris_idx in IRIS_CENTERS:
        iris = face[iris_idx]
        # Assign each iris to its nearest eye (index conventions vary).
        a, b = min(eyes, key=lambda e: dist((e[0] + e[1]) / 2, iris))
        lo, hi = min(a[0], b[0]), max(a[0], b[0])
        if hi - lo < 1e-6:
            continue
        values.append((iris[0] - lo) / (hi - lo))
    return float(np.mean(values)) if values else None


def face_features(face: np.ndarray) -> FaceFeat:
    box = Box.around(face)
    top, chin = face[FOREHEAD_TOP], face[CHIN]
    cl, cr, nose = face[CHEEK_L], face[CHEEK_R], face[NOSE_TIP]
    fw = max(dist(cl, cr), 1e-4)
    fh = max(dist(top, chin), 1e-4)
    lip_lo, lip_hi = face[LOWER_LIP], face[UPPER_LIP]
    ml, mr = face[MOUTH_L], face[MOUTH_R]
    eye_mid = (face[EYE_A_OUTER] + face[EYE_B_OUTER]) / 2
    mid_lower = (nose[1] + lip_lo[1]) / 2

    zones = {
        "mouth": Box(
            min(ml[0], mr[0]) - 0.08 * fw,
            lip_hi[1] - 0.07 * fh,
            max(ml[0], mr[0]) + 0.08 * fw,
            lip_lo[1] + 0.05 * fh,
        ),
        # Generous below the chin: beards extend past the jaw the mesh tracks.
        "beard": Box(box.x0 - 0.05 * fw, mid_lower, box.x1 + 0.05 * fw, chin[1] + 0.2 * fh),
        "neck": Box(nose[0] - 0.55 * fw, chin[1] + 0.2 * fh, nose[0] + 0.55 * fw, chin[1] + 0.95 * fh),
        "face": Box(box.x0 - 0.05 * fw, top[1] + 0.12 * fh, box.x1 + 0.05 * fw, mid_lower),
        "hair": Box(box.x0 - 0.18 * fw, top[1] - 0.5 * fh, box.x1 + 0.18 * fw, top[1] + 0.12 * fh),
    }

    cheek_mid = (cl + cr) / 2
    denom = chin[1] - eye_mid[1]
    eye_vec = face[EYE_B_OUTER] - face[EYE_A_OUTER]
    return FaceFeat(
        box=box,
        fw=fw,
        fh=fh,
        center=face[CENTER_POINTS].mean(axis=0),
        zones=zones,
        yaw=float((nose[0] - cheek_mid[0]) / (fw / 2)),
        pitch=float((nose[1] - eye_mid[1]) / denom) if abs(denom) > 1e-6 else 0.0,
        roll_deg=math.degrees(math.atan2(float(eye_vec[1]), float(eye_vec[0]))),
        gaze=_gaze(face),
    )


def hand_features(hand: HandObs, key: str) -> HandFeat:
    pts = hand.points
    return HandFeat(
        key=key,
        points=pts,
        contact=pts[HAND_CONTACT_POINTS],
        scale=dist(pts[WRIST], pts[MIDDLE_MCP]),
        center=pts.mean(axis=0),
    )


class FeatureExtractor:
    """Stateful: remembers the last face for a moment when the mesh drops out."""

    def __init__(self) -> None:
        self._last_face: FaceFeat | None = None
        self._last_face_t: float = -1e9

    def __call__(self, obs: Observation) -> Features:
        face = None
        if obs.face is not None and len(obs.face) >= 468:
            face = face_features(obs.face)
            self._last_face, self._last_face_t = face, obs.t
        elif self._last_face is not None and obs.t - self._last_face_t <= FACE_MEMORY_S:
            last = self._last_face
            face = FaceFeat(**{**last.__dict__, "fresh": False})

        hands = []
        seen: dict[str, int] = {}
        for h in obs.hands:
            n = seen.get(h.label, 0)
            seen[h.label] = n + 1
            hands.append(hand_features(h, h.label if n == 0 else f"{h.label}{n}"))

        return Features(t=obs.t, aspect=obs.aspect, face=face, hands=hands, pose=obs.pose, blendshapes=obs.blendshapes)
