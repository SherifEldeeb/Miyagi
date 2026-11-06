"""Temporal alert engine and the per-connection coaching session.

Raw per-frame signals are noisy (landmark jitter, a hand flickering in and out
of detection). Each condition therefore goes through:

    signal -> EMA smoothing -> hysteresis (on 0.6 / off 0.3)
           -> must hold for ``min_duration`` -> alert (counted once)
           -> linger 0.6s after it stops -> ``cooldown`` before the next count

Repeat offenders escalate: severity grows with the number of occurrences in
the last 5 minutes, which the UI uses to make the visual cue louder.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .conditions import ConditionConfig, default_conditions
from .detectors import DETECTORS, INACTIVE, Context, Signal
from .features import FeatureExtractor, Features
from .geometry import Box
from .learned import NEUTRAL, PersonalModel, feature_vector
from .observation import Observation

EMA_TAU = 0.25
ON_LEVEL, OFF_LEVEL = 0.6, 0.3
LINGER_S = 0.6
ESCALATION_WINDOW_S = 300.0


@dataclass
class Episode:
    start: float
    end: float | None = None


@dataclass
class Tracker:
    ema: float = 0.0
    active: bool = False
    on_since: float | None = None
    off_since: float | None = None
    last_end: float = -1e9
    last_t: float | None = None
    box: Box | None = None
    episodes: list[Episode] = field(default_factory=list)
    recent: deque = field(default_factory=deque)  # alert start times, for escalation

    def update(self, t: float, sig: Signal, cfg: ConditionConfig) -> bool:
        """Advance the state machine. Returns True when a *new* alert fires."""
        dt = 0.066 if self.last_t is None else max(0.0, min(t - self.last_t, 1.0))
        self.last_t = t
        alpha = 1 - math.exp(-dt / EMA_TAU) if dt > 0 else 0.0
        self.ema += alpha * ((1.0 if sig.active else 0.0) - self.ema)
        if sig.active and sig.box is not None:
            self.box = sig.box

        fired = False
        if not self.active:
            if self.ema >= ON_LEVEL:
                self.on_since = t if self.on_since is None else self.on_since
                if t - self.on_since >= cfg.min_duration and t - self.last_end >= cfg.cooldown:
                    self.active, self.off_since, fired = True, None, True
                    self.episodes.append(Episode(start=self.on_since))
                    self.recent.append(t)
            else:
                self.on_since = None
        else:
            if self.ema < OFF_LEVEL:
                self.off_since = t if self.off_since is None else self.off_since
                if t - self.off_since >= LINGER_S:
                    self.close(t)
            else:
                self.off_since = None
        while self.recent and t - self.recent[0] > ESCALATION_WINDOW_S:
            self.recent.popleft()
        return fired

    def close(self, t: float) -> None:
        if self.active:
            self.active = False
            self.last_end = t
            self.on_since = None
            if self.episodes and self.episodes[-1].end is None:
                self.episodes[-1].end = t

    @property
    def severity(self) -> int:
        n = len(self.recent)
        return 1 if n <= 2 else 2 if n <= 5 else 3


@dataclass
class TeachState:
    label: str
    until: float | None = None  # set on the first frame (client clock)
    seconds: float = 10.0
    added: int = 0


class CoachSession:
    def __init__(
        self,
        perception=None,
        conditions: dict[str, ConditionConfig] | None = None,
        personal: PersonalModel | None = None,
    ):
        self.perception = perception
        self.conditions = conditions or default_conditions()
        self.personal = personal
        self.debug = False
        self.reset()

    def reset(self) -> None:
        self.extract = FeatureExtractor()
        self.ctx = Context(configs=self.conditions)
        self.trackers = {cid: Tracker() for cid in self.conditions}
        self.started_wall = time.time()
        self.t0: float | None = None
        self.t_last: float | None = None
        self.frames = 0
        self.teach: TeachState | None = None

    # -- control -----------------------------------------------------------
    def configure(self, updates: dict[str, dict[str, Any]]) -> None:
        for cid, data in updates.items():
            if cid in self.conditions and isinstance(data, dict):
                self.conditions[cid].update(data)
                if not self.conditions[cid].enabled and self.t_last is not None:
                    self.trackers[cid].close(self.t_last)

    def calibrate(self) -> None:
        if self.t_last is not None:
            self.ctx.start_calibration(self.t_last)
        else:
            self.ctx.baseline = None  # will auto-calibrate on the first face

    def start_teaching(self, label: str, seconds: float = 10.0) -> None:
        if label != NEUTRAL and label not in self.conditions:
            raise ValueError(f"Unknown label {label!r}")
        self.teach = TeachState(label=label, seconds=float(min(max(seconds, 2.0), 60.0)))

    # -- per frame -----------------------------------------------------------
    def process_frame(self, rgb: np.ndarray, t_ms: float) -> dict[str, Any]:
        return self.step(self.perception.observe(rgb, t_ms))

    def step(self, obs: Observation) -> dict[str, Any]:
        f = self.extract(obs)
        self.ctx.update(f)
        self.t0 = f.t if self.t0 is None else self.t0
        self.t_last = f.t
        self.frames += 1

        vec = feature_vector(f, self.ctx) if self.personal is not None else None
        teach_info = self._teach_step(f, vec)
        probs = (
            self.personal.predict(vec)
            if vec is not None and self.personal and self.personal.ready and not self.teach
            else {}
        )

        alerts = []
        for cid, cfg in self.conditions.items():
            tracker = self.trackers[cid]
            if not cfg.enabled or self.teach is not None:
                sig = INACTIVE
            else:
                sig = self._signal(cid, cfg, f, probs)
            fired = tracker.update(f.t, sig, cfg)
            if tracker.active:
                alerts.append(
                    {
                        "id": cid,
                        "label": cfg.label,
                        "emoji": cfg.emoji,
                        "tip": cfg.tip,
                        "styles": cfg.styles,
                        "severity": tracker.severity,
                        "count": len(tracker.episodes),
                        "new": fired,
                        "box": tracker.box.to_normalized(f.aspect) if tracker.box else None,
                    }
                )

        result: dict[str, Any] = {
            "type": "result",
            "t": f.t,
            "alerts": alerts,
            "face_box": f.face.box.to_normalized(f.aspect) if f.face else None,
            "calibrating": self.ctx.calibrating,
            "calibrated": self.ctx.baseline is not None,
            "counts": {cid: len(tr.episodes) for cid, tr in self.trackers.items()},
            "elapsed": f.t - self.t0,
            "learned": {k: round(v, 3) for k, v in probs.items()} if self.debug else None,
        }
        if teach_info:
            result["teach"] = teach_info
        if self.debug:
            result["debug"] = self._debug(f)
        return result

    def _signal(self, cid: str, cfg: ConditionConfig, f: Features, probs: dict[str, float]) -> Signal:
        rules = DETECTORS[cid](f, cfg, self.ctx) if cfg.mode in ("rules", "either") or cid not in probs else INACTIVE
        if cfg.mode == "rules" or cid not in probs:
            return rules
        # Personal model: sensitivity 0 -> needs p >= 0.85, 100 -> p >= 0.35.
        threshold = 0.85 - 0.5 * (cfg.sensitivity / 100)
        p = probs[cid]
        learned = Signal(True, p, self._learned_box(cid, f)) if p >= threshold else INACTIVE
        if cfg.mode == "learned":
            return learned
        return rules if rules.active else learned

    @staticmethod
    def _learned_box(cid: str, f: Features) -> Box | None:
        if f.face is None:
            return None
        zone = {
            "face_touch": "face",
            "hand_to_mouth": "mouth",
            "beard_stroke": "beard",
            "chin_touch": "beard",
            "neck_touch": "neck",
            "hair_touch": "hair",
        }.get(cid)
        return f.face.zones[zone] if zone else f.face.box

    def _teach_step(self, f: Features, vec: np.ndarray | None) -> dict | None:
        st = self.teach
        if st is None or self.personal is None:
            return None
        if st.until is None:
            st.until = f.t + st.seconds
        if vec is not None:
            self.personal.add(vec, st.label)
            st.added += 1
        remaining = max(0.0, st.until - f.t)
        info = {"label": st.label, "remaining": round(remaining, 1), "samples": st.added, "done": remaining <= 0}
        if remaining <= 0:
            self.teach = None
        return info

    def _debug(self, f: Features) -> dict:
        a = f.aspect
        out: dict[str, Any] = {"zones": {}, "hands": []}
        if f.face:
            out["zones"] = {k: z.to_normalized(a) for k, z in f.face.zones.items()}
            out["head"] = {
                "yaw": round(f.face.yaw, 3),
                "pitch": round(f.face.pitch, 3),
                "gaze": None if f.face.gaze is None else round(f.face.gaze, 3),
                "fresh": f.face.fresh,
            }
        for h in f.hands:
            out["hands"].append([[round(float(x) / a, 4), round(float(y), 4)] for x, y in h.points])
        return out

    # -- reporting -----------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        end = self.t_last if self.t_last is not None else 0.0
        duration = (end - self.t0) if self.t0 is not None else 0.0
        per = {}
        for cid, tr in self.trackers.items():
            eps = tr.episodes
            if not eps:
                continue
            lengths = [((e.end if e.end is not None else end) - e.start) for e in eps]
            cfg = self.conditions[cid]
            per[cid] = {
                "label": cfg.label,
                "emoji": cfg.emoji,
                "count": len(eps),
                "total_seconds": round(sum(lengths), 1),
                "longest_seconds": round(max(lengths), 1),
                "per_10_min": round(len(eps) / max(duration, 1.0) * 600, 1),
                "first_at_s": round(eps[0].start - (self.t0 or 0), 1),
                "minutes": [round((e.start - (self.t0 or 0)) / 60, 1) for e in eps][:200],
            }
        return {
            "duration_seconds": round(duration, 1),
            "frames": self.frames,
            "enabled": [cid for cid, c in self.conditions.items() if c.enabled],
            "habits": dict(sorted(per.items(), key=lambda kv: -kv[1]["count"])),
        }
