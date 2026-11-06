"""Replaceable landmark adapter. Nothing here calls a hosted AI service."""
from dataclasses import dataclass, field
from typing import Protocol
from contextlib import ExitStack

import numpy as np

from miyagi.config import MODEL_DIR, missing_models


@dataclass
class Landmarks:
    face: list[tuple[float, float]] = field(default_factory=list)
    hands: list[list[tuple[float, float]]] = field(default_factory=list)
    shoulders: list[tuple[float, float]] = field(default_factory=list)
    aspect: float = 4 / 3


class LandmarkProvider(Protocol):
    def detect(self, rgb: np.ndarray, timestamp_ms: int) -> Landmarks: ...
    def close(self) -> None: ...


class MediaPipeProvider:
    def __init__(self):
        if missing_models():
            raise RuntimeError("Run uv run miyagi download-models before starting the camera.")
        import mediapipe as mp
        self.mp = mp
        vision = mp.tasks.vision
        base = mp.tasks.BaseOptions
        self.stack = ExitStack()
        try:
            self.face = self.stack.enter_context(vision.FaceLandmarker.create_from_options(
                vision.FaceLandmarkerOptions(base_options=base(model_asset_path=str(MODEL_DIR / "face_landmarker.task")),
                    running_mode=vision.RunningMode.VIDEO, num_faces=1)))
            self.hand = self.stack.enter_context(vision.HandLandmarker.create_from_options(
                vision.HandLandmarkerOptions(base_options=base(model_asset_path=str(MODEL_DIR / "hand_landmarker.task")),
                    running_mode=vision.RunningMode.VIDEO, num_hands=2)))
            self.pose = self.stack.enter_context(vision.PoseLandmarker.create_from_options(
                vision.PoseLandmarkerOptions(base_options=base(model_asset_path=str(MODEL_DIR / "pose_landmarker_lite.task")),
                    running_mode=vision.RunningMode.VIDEO, num_poses=1)))
        except Exception:
            self.stack.close()
            raise

    def detect(self, rgb: np.ndarray, timestamp_ms: int) -> Landmarks:
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        face = self.face.detect_for_video(image, timestamp_ms)
        hands = self.hand.detect_for_video(image, timestamp_ms)
        pose = self.pose.detect_for_video(image, timestamp_ms)
        points = lambda items: [(p.x, p.y) for p in items]
        shoulders = []
        if pose.pose_landmarks:
            p = pose.pose_landmarks[0]
            if all(p[i].visibility > 0.6 and p[i].presence > 0.6 for i in (11, 12)):
                shoulders = points([p[11], p[12]])
        return Landmarks(points(face.face_landmarks[0]) if face.face_landmarks else [],
                         [points(h) for h in hands.hand_landmarks], shoulders, rgb.shape[1] / rgb.shape[0])

    def close(self):
        self.stack.close()
