"""Geometry + time, independent of any landmark model or cloud vendor."""
from collections import deque
from dataclasses import dataclass
from math import hypot
from typing import Literal

from pydantic import BaseModel, Field

from miyagi.vision import Landmarks

Condition = Literal["face_touch", "neck_touch", "chin_touch", "movement"]
LABELS = ["face_touch", "neck_touch", "chin_touch", "movement"]
MESSAGES = {
    "face_touch": "Let your hand rest away from your face.",
    "neck_touch": "Give your neck a little space.",
    "chin_touch": "Notice your hand near your chin or beard.",
    "movement": "Take a breath and find a comfortable position.",
}
FEATURE_NAMES = ["face_distance", "neck_distance", "chin_distance", "motion", "hands_visible", "pose_visible"]
WINDOW_SIZE = 16


class CoachSettings(BaseModel):
    enabled: list[Condition] = Field(default_factory=lambda: ["chin_touch"], max_length=4)
    hold_seconds: float = Field(default=1.5, ge=0.5, le=6)
    cooldown_seconds: float = Field(default=12, ge=3, le=120)
    sensitivity: float = Field(default=1.0, ge=0.5, le=1.8)


@dataclass
class Gate:
    since: float | None = None
    last_alert: float = -1e9


class CoachEngine:
    def __init__(self, settings: CoachSettings | None = None):
        self.settings = settings or CoachSettings()
        self.gates = {label: Gate() for label in LABELS}
        self.last_t: float | None = None
        self.previous_center = None
        self.motion = deque(maxlen=24)
        self.baseline_samples = []
        self.baseline = None
        self.calibration_started = None
        self.total = {label: 0 for label in LABELS}

    def configure(self, settings: CoachSettings):
        self.settings = settings
        for gate in self.gates.values():
            gate.since = None

    def recalibrate(self):
        self.baseline_samples.clear()
        self.baseline = None
        self.calibration_started = None
        self.previous_center = None
        self.motion.clear()
        for gate in self.gates.values():
            gate.since = None

    def observe(self, marks: Landmarks, t: float, classifier=None) -> dict:
        gap = self.last_t is not None and t - self.last_t > 0.75
        if gap:
            self.previous_center = None
            self.motion.clear()
            for gate in self.gates.values():
                gate.since = None
        dt = max(0.01, t - self.last_t) if self.last_t is not None else 0.125
        self.last_t = t
        if len(marks.face) < 455:
            self.previous_center = None
            self.motion.clear()
            for gate in self.gates.values():
                gate.since = None
            self.baseline_samples.clear() if self.baseline is None else None
            self.calibration_started = None if self.baseline is None else self.calibration_started
            if classifier:
                classifier.reset()
            return {"tracking": False, "calibrated": self.baseline is not None, "alerts": [], "active": [],
                    "counts": self.total.copy(), "features": None, "calibration": 0}
        # Convert to pixel-isotropic units before computing distances.
        point = lambda p: (p[0] * marks.aspect, p[1])
        face = [point(p) for p in marks.face]
        dist = lambda a, b: hypot(a[0] - b[0], a[1] - b[1])
        width = max(dist(face[234], face[454]), 0.03)
        chin = face[152]
        center = face[1]
        shoulder_center = None
        if len(marks.shoulders) == 2:
            shoulders = [point(p) for p in marks.shoulders]
            shoulder_center = tuple((a + b) / 2 for a, b in zip(*shoulders))
        neck = ((chin[0] + shoulder_center[0]) / 2, (chin[1] + shoulder_center[1]) / 2) if shoulder_center else None
        fingertips = [point(h[i]) for h in marks.hands if len(h) == 21 for i in (4, 8, 12, 16, 20)]
        face_targets = [face[i] for i in (1, 4, 33, 263, 50, 280, 61, 291, 10)]
        distance = lambda targets: min((dist(p, q) / width for p in fingertips for q in targets), default=4.0)
        face_distance = distance(face_targets)
        chin_distance = distance([chin, face[175], face[199]])
        neck_distance = distance([neck]) if neck else 4.0
        speed = dist(center, self.previous_center) / width / dt if self.previous_center else 0.0
        self.previous_center = center
        self.motion.append(min(speed, 5.0))
        movement = sum(self.motion) / len(self.motion)
        if self.baseline is None:
            if gap:
                self.baseline_samples.clear()
                self.calibration_started = None
            if self.calibration_started is None:
                self.calibration_started = t
            self.baseline_samples.append(movement)
            if t - self.calibration_started >= 3 and len(self.baseline_samples) >= 12:
                self.baseline = min(0.8, sum(self.baseline_samples) / len(self.baseline_samples))
        progress = 1.0 if self.baseline is not None else min(0.99, (t - self.calibration_started) / 3)
        threshold = 0.23 * self.settings.sensitivity
        # A single hand region gets the nearest touch label; avoids three cues for one contact.
        candidates = {"face_touch": face_distance, "chin_touch": chin_distance, "neck_touch": neck_distance}
        nearest = min(candidates, key=candidates.get)
        active = [nearest] if candidates[nearest] < threshold else []
        if movement > max(0.45, (self.baseline or 0) * 2.5) / self.settings.sensitivity:
            active.append("movement")
        features = [min(face_distance, 4), min(neck_distance, 4), min(chin_distance, 4), movement,
                    float(bool(fingertips)), float(bool(neck))]
        if classifier:
            if gap:
                classifier.reset()
            active = classifier.predict(features)
        calibrated = self.baseline is not None
        active = [c for c in active if c in self.settings.enabled] if calibrated else []
        alerts = []
        for label, gate in self.gates.items():
            if label not in active:
                gate.since = None
                continue
            if gate.since is None:
                gate.since = t
            if t - gate.since >= self.settings.hold_seconds and t - gate.last_alert >= self.settings.cooldown_seconds:
                gate.last_alert = t
                self.total[label] += 1
                alerts.append({"condition": label, "message": MESSAGES[label], "time": round(t, 2)})
        return {"tracking": True, "calibrated": calibrated, "calibration": progress, "alerts": alerts,
                "active": active, "counts": self.total.copy(), "features": features,
                "face_box": [min(p[0] for p in marks.face), min(p[1] for p in marks.face),
                             max(p[0] for p in marks.face), max(p[1] for p in marks.face)]}
