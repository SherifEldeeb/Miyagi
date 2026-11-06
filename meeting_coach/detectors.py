"""Rule-based (zero-shot) detectors: geometry + short-term history.

Each detector maps (features, config, context) -> Signal. Detectors are
stateless; temporal state lives in :class:`Context` (motion history and the
calibrated baseline posture), and debouncing lives in engine.py.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import median

import numpy as np

from .conditions import ConditionConfig
from .features import (
    CONTACT_WEIGHTS,
    ELBOW_L,
    ELBOW_R,
    SHOULDER_L,
    SHOULDER_R,
    WRIST_L,
    WRIST_R,
    ZONE_PRIORITY,
    Features,
    HandFeat,
)
from .geometry import Box, dist

# A hand much bigger than "same depth as the face" is in front of the face, not
# touching it. Typical hand-scale / face-width at equal depth is ~0.6-0.8.
MAX_HAND_FACE_RATIO = 1.2
ZONE_WEIGHT = {"mouth": 1.6}
CALIBRATION_S = 3.0
WRIST_POINT = 0


@dataclass
class Signal:
    active: bool
    strength: float = 0.0
    box: Box | None = None


INACTIVE = Signal(False)


@dataclass
class Baseline:
    fw: float
    yaw: float
    pitch: float
    gaze: float | None
    neck_ratio: float | None


@dataclass
class Context:
    face_hist: deque = field(default_factory=lambda: deque(maxlen=120))  # (t, center, fw)
    hand_hist: dict[str, deque] = field(default_factory=dict)  # key -> (t, centroid)
    baseline: Baseline | None = None
    calib_until: float | None = None
    calib_samples: list[tuple] = field(default_factory=list)
    configs: dict = field(default_factory=dict)  # all condition configs (for cross-habit rules)

    # -- history ---------------------------------------------------------
    def update(self, f: Features) -> None:
        if f.face is not None and f.face.fresh:
            self.face_hist.append((f.t, f.face.center.copy(), f.face.fw))
        live = set()
        for h in f.hands:
            live.add(h.key)
            self.hand_hist.setdefault(h.key, deque(maxlen=90)).append((f.t, h.contact.mean(axis=0)))
        for key in list(self.hand_hist):
            if key not in live and self.hand_hist[key] and f.t - self.hand_hist[key][-1][0] > 0.5:
                del self.hand_hist[key]
        self._calibration_step(f)

    # -- calibration -----------------------------------------------------
    def start_calibration(self, t: float) -> None:
        self.calib_until = t + CALIBRATION_S
        self.calib_samples = []

    @property
    def calibrating(self) -> bool:
        return self.calib_until is not None

    def _calibration_step(self, f: Features) -> None:
        if self.baseline is None and self.calib_until is None and f.face is not None:
            self.start_calibration(f.t)  # auto-calibrate on the first face we see
        if self.calib_until is None:
            return
        if f.face is not None and f.face.fresh:
            sh = f.shoulders()
            neck = (sh[0][1] - f.face.center[1]) / sh[1] if sh and sh[1] > 1e-4 else None
            self.calib_samples.append((f.face.fw, f.face.yaw, f.face.pitch, f.face.gaze, neck))
        if f.t >= self.calib_until and len(self.calib_samples) >= 5:
            cols = list(zip(*self.calib_samples))

            def med(values):
                vals = [v for v in values if v is not None]
                return float(median(vals)) if vals else None

            self.baseline = Baseline(*(med(c) for c in cols))
            self.calib_until = None
        elif f.t >= self.calib_until + 5:  # never saw a face; try again later
            self.calib_until = None

    # -- motion helpers ---------------------------------------------------
    def face_speed(self, now: float, window: float = 3.0, step: float = 0.2) -> float | None:
        """Head movement in face-widths per second (resampled to damp jitter)."""
        pts = [p for p in self.face_hist if now - p[0] <= window]
        if len(pts) < 4 or pts[-1][0] - pts[0][0] < window * 0.5:
            return None
        sampled = [pts[0]]
        for p in pts[1:]:
            if p[0] - sampled[-1][0] >= step:
                sampled.append(p)
        if len(sampled) < 3:
            return None
        fw = float(np.mean([p[2] for p in sampled]))
        path = sum(dist(a[1], b[1]) + 0.5 * abs(a[2] - b[2]) for a, b in zip(sampled, sampled[1:]))
        return path / fw / (sampled[-1][0] - sampled[0][0])

    def hand_speed(self, key: str, now: float, fw: float, window: float = 1.2) -> float | None:
        hist = [p for p in self.hand_hist.get(key, ()) if now - p[0] <= window]
        if len(hist) < 3 or hist[-1][0] - hist[0][0] < window * 0.4:
            return None
        path = sum(dist(a[1], b[1]) for a, b in zip(hist, hist[1:]))
        return path / fw / (hist[-1][0] - hist[0][0])


# --------------------------------------------------------------------------
# Hand-to-body contact
# --------------------------------------------------------------------------


def hand_zone(f: Features, hand: HandFeat, zone_scale: float = 1.0) -> tuple[str, np.ndarray] | None:
    """Which zone (if any) is this hand touching, and which contact points are in it."""
    face = f.face
    if face is None or hand.scale / face.fw > MAX_HAND_FACE_RATIO:
        return None
    best, best_score, best_pts = None, 0.0, None
    for zone in ZONE_PRIORITY:
        box = face.zones[zone].scale(zone_scale)
        inside = box.contains(hand.contact)
        score = float(CONTACT_WEIGHTS[inside].sum()) * ZONE_WEIGHT.get(zone, 1.0)
        if score > best_score:
            best, best_score, best_pts = zone, score, hand.contact[inside]
    return (best, best_pts) if best else None


def _contact(zone_name: str):
    def detect(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
        for hand in f.hands:
            hit = hand_zone(f, hand, cfg.param)
            if hit and hit[0] == zone_name:
                pts = hit[1]
                box = Box.around(pts).pad(0.15 * f.face.fw).union(f.face.zones[zone_name])
                return Signal(True, min(1.0, len(pts) / 6), box)
        return INACTIVE

    return detect


def detect_beard_stroke(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    for hand in f.hands:
        hit = hand_zone(f, hand)
        if hit and hit[0] == "beard":
            speed = ctx.hand_speed(hand.key, f.t, f.face.fw)
            if speed is not None and speed >= cfg.param:
                return Signal(True, min(1.0, speed / (2 * cfg.param)), f.face.zones["beard"].pad(0.05 * f.face.fw))
    return INACTIVE


def detect_chin_touch(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    """Hand on the chin / jaw / beard, or propping up the head - but *not* stroking.

    When the hand is moving fast enough to count as beard stroking, the more
    specific ``beard_stroke`` habit claims it instead, so one gesture is never
    counted twice.
    """
    stroke = ctx.configs.get("beard_stroke")
    stroke_speed = stroke.param if stroke is not None and stroke.enabled else None
    for hand in f.hands:
        hit = hand_zone(f, hand, cfg.param)
        if not hit:
            continue
        zone, pts = hit
        # Propping the head: fingers up the cheek *and* the heel of the palm on
        # the jaw/chin. (In a plain cheek touch the wrist is well below the chin.)
        propping = zone == "face" and bool(f.face.zones["beard"].contains(hand.points[WRIST_POINT]).any())
        if zone != "beard" and not propping:
            continue
        if stroke_speed is not None:
            speed = ctx.hand_speed(hand.key, f.t, f.face.fw)
            if speed is not None and speed >= stroke_speed:
                continue
        box = f.face.zones["beard"].union(Box.around(pts).pad(0.1 * f.face.fw))
        return Signal(True, min(1.0, len(pts) / 6), box)
    return INACTIVE


# --------------------------------------------------------------------------
# Head, posture, expression
# --------------------------------------------------------------------------


def detect_movement(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    speed = ctx.face_speed(f.t)
    if f.face is None or speed is None or speed < cfg.param:
        return INACTIVE
    return Signal(True, min(1.0, speed / (2 * cfg.param)), f.face.box.pad(0.1 * f.face.fw))


def detect_looking_away(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    if f.face is None or not f.face.fresh:
        return INACTIVE
    b = ctx.baseline
    yaw0, pitch0, gaze0 = (b.yaw, b.pitch, b.gaze) if b else (0.0, f.face.pitch, 0.5)
    yaw_off = abs(f.face.yaw - yaw0) > cfg.param
    pitch_off = abs(f.face.pitch - pitch0) > cfg.param * 0.35
    gaze_off = f.face.gaze is not None and gaze0 is not None and abs(f.face.gaze - gaze0) > cfg.param * 0.4
    if yaw_off or pitch_off or gaze_off:
        return Signal(True, 0.7, f.face.box)
    return INACTIVE


def detect_slouching(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    b = ctx.baseline
    sh = f.shoulders()
    if f.face is None or not f.face.fresh or b is None or b.neck_ratio is None or sh is None or sh[1] < 1e-4:
        return INACTIVE
    neck = (sh[0][1] - f.face.center[1]) / sh[1]
    if neck < b.neck_ratio * (1 - cfg.param):
        return Signal(
            True,
            0.6,
            f.face.box.union(Box(sh[0][0] - sh[1] / 2, sh[0][1] - 0.02, sh[0][0] + sh[1] / 2, sh[0][1] + 0.02)),
        )
    return INACTIVE


def detect_leaning_in(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    b = ctx.baseline
    if f.face is None or b is None or not f.face.fresh:
        return INACTIVE
    if f.face.fw > b.fw * (1 + cfg.param):
        return Signal(True, 0.6, f.face.box)
    return INACTIVE


def detect_frowning(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    bs = f.blendshapes
    if f.face is None or not bs:
        return INACTIVE
    brow = (bs.get("browDownLeft", 0.0) + bs.get("browDownRight", 0.0)) / 2
    if brow > cfg.param:
        z = f.face.zones["face"]
        return Signal(True, brow, Box(z.x0, z.y0 - 0.05 * f.face.fh, z.x1, z.cy))
    return INACTIVE


def detect_out_of_frame(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    return Signal(True, 1.0) if f.face is None and ctx.baseline is not None else INACTIVE


def detect_fidgeting(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    if f.face is None or not f.hands:
        return INACTIVE
    speeds = [s for h in f.hands if (s := ctx.hand_speed(h.key, f.t, f.face.fw, window=3.0)) is not None]
    if speeds and max(speeds) > cfg.param:
        return Signal(True, 0.6, Box.around(np.vstack([h.points for h in f.hands])))
    return INACTIVE


def detect_arms_crossed(f: Features, cfg: ConditionConfig, ctx: Context) -> Signal:
    p = f.pose
    if p is None or min(p[i][2] for i in (SHOULDER_L, SHOULDER_R, WRIST_L, WRIST_R, ELBOW_L, ELBOW_R)) < 0.5:
        return INACTIVE
    mid_x = (p[SHOULDER_L][0] + p[SHOULDER_R][0]) / 2
    side_l, side_r = np.sign(p[SHOULDER_L][0] - mid_x), np.sign(p[SHOULDER_R][0] - mid_x)
    # Each wrist has crossed the body midline to the other shoulder's side.
    crossed = np.sign(p[WRIST_L][0] - mid_x) == side_r and np.sign(p[WRIST_R][0] - mid_x) == side_l
    if crossed:
        return Signal(True, 0.7, Box.around(p[[ELBOW_L, ELBOW_R, WRIST_L, WRIST_R], :2]).pad(0.03))
    return INACTIVE


Detector = Callable[[Features, ConditionConfig, Context], Signal]

DETECTORS: dict[str, Detector] = {
    "face_touch": _contact("face"),
    "hand_to_mouth": _contact("mouth"),
    "neck_touch": _contact("neck"),
    "hair_touch": _contact("hair"),
    "beard_stroke": detect_beard_stroke,
    "chin_touch": detect_chin_touch,
    "excessive_movement": detect_movement,
    "looking_away": detect_looking_away,
    "slouching": detect_slouching,
    "leaning_in": detect_leaning_in,
    "frowning": detect_frowning,
    "out_of_frame": detect_out_of_frame,
    "fidgeting": detect_fidgeting,
    "arms_crossed": detect_arms_crossed,
}
