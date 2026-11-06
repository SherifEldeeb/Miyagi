"""The catalogue of habits we can coach on, and their user-tunable settings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

ALERT_STYLES = ["box", "mask", "border", "avatar", "toast", "sound"]
DETECTION_MODES = ["rules", "learned", "either"]


@dataclass
class ConditionConfig:
    id: str
    label: str
    emoji: str
    tip: str
    needs: str  # what must be visible: "face", "hands", "pose"
    # Detector parameter at sensitivity 0 ("hard") and 100 ("easy").
    param_hard: float = 1.0
    param_easy: float = 1.0
    enabled: bool = True
    sensitivity: int = 50  # 0..100
    min_duration: float = 0.6  # seconds the condition must hold before alerting
    cooldown: float = 2.0  # seconds after an alert ends before a new one counts
    styles: list[str] = field(default_factory=lambda: ["box", "avatar", "toast"])
    mode: str = "rules"  # rules | learned | either (learned needs a trained personal model)
    focus: bool = False  # part of the current focus area (enabled by default)

    @property
    def param(self) -> float:
        s = min(max(self.sensitivity, 0), 100) / 100
        return self.param_hard + (self.param_easy - self.param_hard) * s

    # Fields the client may change.
    MUTABLE = ("enabled", "sensitivity", "min_duration", "cooldown", "styles", "mode")

    def update(self, data: dict[str, Any]) -> None:
        if "enabled" in data:
            self.enabled = bool(data["enabled"])
        if "sensitivity" in data:
            self.sensitivity = int(min(max(int(data["sensitivity"]), 0), 100))
        if "min_duration" in data:
            self.min_duration = float(min(max(float(data["min_duration"]), 0.0), 30.0))
        if "cooldown" in data:
            self.cooldown = float(min(max(float(data["cooldown"]), 0.0), 120.0))
        if "styles" in data:
            self.styles = [s for s in data["styles"] if s in ALERT_STYLES]
        if "mode" in data and data["mode"] in DETECTION_MODES:
            self.mode = data["mode"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_DEFAULTS: list[ConditionConfig] = [
    # --- Focus area: beard & chin ------------------------------------------
    ConditionConfig(
        "beard_stroke",
        "Stroking beard",
        "🧔",
        "Beard stroking looks like deep doubt (or a villain). Rest your hands, or try a slow nod instead.",
        needs="hands",
        param_hard=0.9,
        param_easy=0.2,
        min_duration=0.8,
        focus=True,
        styles=["box", "mask", "avatar", "toast"],
    ),
    ConditionConfig(
        "chin_touch",
        "Touching chin",
        "🤔",
        "Hand on the chin or propping up your head reads as boredom or doubt. Sit tall, hands down.",
        needs="hands",
        param_hard=0.85,
        param_easy=1.3,
        min_duration=1.2,
        cooldown=3.0,
        focus=True,
        styles=["box", "avatar", "toast"],
    ),
    # --- More habits (off by default; enable in the Habits tab) -------------
    ConditionConfig(
        "face_touch",
        "Touching face",
        "🙈",
        "Rest your hands on the desk or hold a pen - touching your face reads as nervousness.",
        needs="hands",
        param_hard=0.85,
        param_easy=1.25,
        styles=["box", "mask", "avatar", "toast"],
    ),
    ConditionConfig(
        "hand_to_mouth",
        "Hand at mouth",
        "🤐",
        "Covering your mouth muffles your voice and can signal doubt. Hands down while speaking.",
        needs="hands",
        param_hard=0.85,
        param_easy=1.3,
        min_duration=0.8,
    ),
    ConditionConfig(
        "neck_touch",
        "Touching neck",
        "🦒",
        "Neck touching is a classic self-soothing gesture - it signals anxiety. Ground your hands.",
        needs="hands",
        param_hard=0.85,
        param_easy=1.25,
        styles=["box", "mask", "avatar", "toast"],
    ),
    ConditionConfig(
        "hair_touch",
        "Playing with hair",
        "💇",
        "Fiddling with hair is distracting on camera. Tuck it back before the call starts.",
        needs="hands",
        param_hard=0.85,
        param_easy=1.25,
        min_duration=0.8,
    ),
    ConditionConfig(
        "excessive_movement",
        "Moving / rocking a lot",
        "🌀",
        "Lots of head and body movement is distracting on video. Plant your feet and settle.",
        needs="face",
        param_hard=1.3,
        param_easy=0.3,
        min_duration=1.5,
        cooldown=5.0,
        styles=["border", "avatar", "toast"],
    ),
    ConditionConfig(
        "looking_away",
        "Looking away from camera",
        "👀",
        "Look at the camera (not the screen) when you make a key point - it reads as eye contact.",
        needs="face",
        param_hard=0.7,
        param_easy=0.3,
        min_duration=3.0,
        cooldown=6.0,
        styles=["avatar", "toast"],
    ),
    ConditionConfig(
        "slouching",
        "Slouching",
        "🐢",
        "Sit up: shoulders back, screen at eye level. You'll sound more confident too.",
        needs="pose",
        param_hard=0.3,
        param_easy=0.08,
        min_duration=4.0,
        cooldown=20.0,
        styles=["avatar", "toast"],
    ),
    ConditionConfig(
        "leaning_in",
        "Too close to camera",
        "🔍",
        "You're filling the frame. Lean back so your shoulders are visible.",
        needs="face",
        param_hard=0.5,
        param_easy=0.15,
        min_duration=3.0,
        cooldown=20.0,
        styles=["avatar", "toast"],
    ),
    ConditionConfig(
        "frowning",
        "Frowning",
        "😠",
        "Your brows are furrowed. Relax your forehead - a neutral face reads as friendlier.",
        needs="face",
        param_hard=0.75,
        param_easy=0.25,
        min_duration=2.5,
        cooldown=15.0,
        styles=["avatar", "toast"],
    ),
    ConditionConfig(
        "out_of_frame",
        "Out of frame",
        "🫥",
        "We lost you! Re-centre yourself in the camera.",
        needs="face",
        min_duration=2.5,
        cooldown=10.0,
        styles=["border", "avatar", "toast"],
    ),
    ConditionConfig(
        "fidgeting",
        "Restless hands",
        "🫨",
        "Lots of hand motion. Gesture with purpose, then rest your hands.",
        needs="hands",
        param_hard=3.0,
        param_easy=0.8,
        min_duration=3.0,
        cooldown=15.0,
        styles=["avatar", "toast"],
    ),
    ConditionConfig(
        "arms_crossed",
        "Arms crossed",
        "🙅",
        "Crossed arms can look defensive. Open your posture.",
        needs="pose",
        min_duration=3.0,
        cooldown=20.0,
        styles=["avatar", "toast"],
    ),
]


# Only the focus area is on out of the box; everything else is one click away.
for _c in _DEFAULTS:
    _c.enabled = _c.focus

FOCUS_AREA = "Beard & chin"


def default_conditions() -> dict[str, ConditionConfig]:
    return {c.id: replace(c, styles=list(c.styles)) for c in _DEFAULTS}
