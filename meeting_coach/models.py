"""Download and cache the MediaPipe task models on first run."""

from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

_BASE = "https://storage.googleapis.com/mediapipe-models"
MODELS = {
    "face_landmarker.task": f"{_BASE}/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
    "hand_landmarker.task": f"{_BASE}/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
    "pose_landmarker_lite.task": f"{_BASE}/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
}


def model_dir() -> Path:
    env = os.environ.get("MEETING_COACH_MODEL_DIR")
    if env:
        return Path(env).expanduser()
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "meeting_coach" / "models"


def models_present(directory: Path | None = None) -> bool:
    directory = directory or model_dir()
    return all((directory / name).is_file() for name in MODELS)


def ensure_models(directory: Path | None = None) -> Path:
    directory = directory or model_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        target = directory / name
        if target.is_file() and target.stat().st_size > 0:
            continue
        log.info("Downloading %s ...", name)
        tmp = target.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)  # noqa: S310 - fixed https URLs
        tmp.replace(target)
    return directory
