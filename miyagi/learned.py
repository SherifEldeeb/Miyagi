"""Personal (few-shot) habit model.

Rules work out of the box, but everybody touches their face differently. In
*Teach* mode the user performs a habit for a few seconds (and sits normally
for a few seconds as "neutral"); we store **landmark feature vectors only -
never images** - and fit a small tree ensemble on the CPU in well under a
second. Each condition can then use ``rules``, ``learned`` or ``either``.

Why landmarks instead of pixels: the heavy lifting (finding faces and hands)
is done by MediaPipe, so the classifier only has to learn a ~70-dimensional
geometric pattern. That needs ~100 examples, not ~100k, and is robust to
lighting, background and clothing.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import numpy as np

from .detectors import Context
from .features import Features

log = logging.getLogger(__name__)

NEUTRAL = "neutral"
BLENDSHAPES = [
    "browDownLeft",
    "browDownRight",
    "browInnerUp",
    "mouthFrownLeft",
    "mouthFrownRight",
    "mouthPressLeft",
    "mouthPressRight",
    "jawOpen",
    "eyeBlinkLeft",
    "eyeBlinkRight",
    "mouthPucker",
    "cheekPuff",
]
N_CONTACT = 10
HAND_DIMS = 1 + 2 * N_CONTACT + 2  # present, contact points, scale, speed
FEATURE_DIMS = 2 * HAND_DIMS + 7 + len(BLENDSHAPES) + 2


def data_dir() -> Path:
    env = os.environ.get("MIYAGI_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "miyagi"


def feature_vector(f: Features, ctx: Context) -> np.ndarray | None:
    """Face-relative, scale-normalised description of one frame (None without a face)."""
    face = f.face
    if face is None:
        return None
    fw, c = face.fw, face.center
    b = ctx.baseline

    hands = sorted(f.hands, key=lambda h: float(h.center[0]))[:2]
    hand_parts = []
    for i in range(2):
        if i < len(hands):
            h = hands[i]
            rel = ((h.contact - c) / fw).ravel()
            speed = ctx.hand_speed(h.key, f.t, fw) or 0.0
            hand_parts.append(np.concatenate([[1.0], rel, [h.scale / fw, min(speed, 5.0)]]))
        else:
            hand_parts.append(np.zeros(HAND_DIMS))

    sh = f.shoulders()
    neck = (sh[0][1] - c[1]) / sh[1] if sh and sh[1] > 1e-4 else 0.0
    head = [
        face.yaw - (b.yaw if b else 0.0),
        face.pitch - (b.pitch if b else face.pitch),
        face.roll_deg / 45.0,
        (face.gaze - (b.gaze if b and b.gaze is not None else 0.5)) if face.gaze is not None else 0.0,
        face.fw / b.fw if b else 1.0,
        min(ctx.face_speed(f.t) or 0.0, 5.0),
        float(face.fresh),
    ]
    blend = [f.blendshapes.get(k, 0.0) for k in BLENDSHAPES]
    posture = [neck - (b.neck_ratio if b and b.neck_ratio is not None else neck), float(sh is not None)]
    vec = np.concatenate([*hand_parts, head, blend, posture]).astype(np.float32)
    assert vec.shape[0] == FEATURE_DIMS
    return vec


class PersonalModel:
    """Sample store + classifier, persisted under the data dir."""

    def __init__(self, directory: Path | None = None):
        self.dir = directory or data_dir()
        self._lock = threading.Lock()
        self.X: list[np.ndarray] = []
        self.y: list[str] = []
        self.clf = None
        self.classes: list[str] = []
        self.metrics: dict = {}
        self._load()

    # -- persistence -----------------------------------------------------
    @property
    def _samples_path(self) -> Path:
        return self.dir / "teach_samples.npz"

    @property
    def _model_path(self) -> Path:
        return self.dir / "personal_model.joblib"

    def _load(self) -> None:
        try:
            if self._samples_path.is_file():
                data = np.load(self._samples_path, allow_pickle=False)
                if data["X"].ndim == 2 and data["X"].shape[1] == FEATURE_DIMS:
                    self.X, self.y = list(data["X"]), [str(v) for v in data["y"]]
            if self._model_path.is_file():
                import joblib

                saved = joblib.load(self._model_path)
                if saved.get("dims") == FEATURE_DIMS:
                    self.clf, self.classes, self.metrics = saved["clf"], saved["classes"], saved["metrics"]
        except Exception:  # corrupt/old files should never stop the app
            log.exception("Could not load personal model; starting fresh")

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self._samples_path, X=np.array(self.X).reshape(-1, FEATURE_DIMS), y=np.array(self.y))
        if self.clf is not None:
            import joblib

            joblib.dump(
                {"clf": self.clf, "classes": self.classes, "metrics": self.metrics, "dims": FEATURE_DIMS},
                self._model_path,
            )
        elif self._model_path.exists():
            self._model_path.unlink()

    # -- samples ---------------------------------------------------------
    def add(self, vec: np.ndarray, label: str) -> None:
        with self._lock:
            self.X.append(vec)
            self.y.append(label)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for label in self.y:
            out[label] = out.get(label, 0) + 1
        return out

    def clear(self, label: str | None = None) -> None:
        with self._lock:
            if label is None:
                self.X, self.y = [], []
            else:
                keep = [i for i, v in enumerate(self.y) if v != label]
                self.X, self.y = [self.X[i] for i in keep], [self.y[i] for i in keep]
            self.clf, self.classes, self.metrics = None, [], {}
            self._save()

    # -- training --------------------------------------------------------
    def train(self, min_per_class: int = 20) -> dict:
        from sklearn.ensemble import ExtraTreesClassifier

        with self._lock:
            counts = self.counts()
            usable = {k for k, n in counts.items() if n >= min_per_class}
            if NEUTRAL not in usable or len(usable) < 2:
                return {
                    "ok": False,
                    "error": f"Need at least {min_per_class} samples of '{NEUTRAL}' and of one habit.",
                    "counts": counts,
                }
            idx = [i for i, v in enumerate(self.y) if v in usable]
            X = np.array([self.X[i] for i in idx])
            y = np.array([self.y[i] for i in idx])

            # Honest-ish evaluation: frames are highly correlated in time, so a
            # random split would leak. Hold out the *last* 25% of each class.
            test = np.zeros(len(y), dtype=bool)
            for label in usable:
                where = np.flatnonzero(y == label)
                test[where[int(len(where) * 0.75) :]] = True

            def make():
                return ExtraTreesClassifier(
                    n_estimators=200, min_samples_leaf=2, class_weight="balanced", n_jobs=-1, random_state=0
                )

            holdout = make().fit(X[~test], y[~test])
            acc = float((holdout.predict(X[test]) == y[test]).mean()) if test.any() else None

            self.clf = make().fit(X, y)
            self.classes = list(self.clf.classes_)
            self.metrics = {"holdout_accuracy": acc, "samples": int(len(y)), "counts": counts}
            self._save()
            return {"ok": True, "classes": self.classes, **self.metrics}

    def predict(self, vec: np.ndarray) -> dict[str, float]:
        clf = self.clf
        if clf is None:
            return {}
        probs = clf.predict_proba(vec.reshape(1, -1))[0]
        return {c: float(p) for c, p in zip(self.classes, probs)}

    @property
    def ready(self) -> bool:
        return self.clf is not None

    def status(self) -> dict:
        return {"ready": self.ready, "classes": self.classes, "counts": self.counts(), "metrics": self.metrics}
