"""MediaPipe-based perception: face mesh (+ blendshapes), hands and pose."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Protocol

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from .models import ensure_models
from .observation import HandObs, Observation


class Perception(Protocol):
    def observe(self, rgb: np.ndarray, t_ms: float) -> Observation: ...

    def close(self) -> None: ...


class MediaPipePerception:
    """Runs the three landmarkers in VIDEO mode (uses temporal tracking)."""

    def __init__(self, directory: Path | None = None, enable_pose: bool = True):
        directory = ensure_models(directory)
        video = vision.RunningMode.VIDEO

        def opts(name: str) -> BaseOptions:
            return BaseOptions(model_asset_path=str(directory / name))

        self._face = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=opts("face_landmarker.task"),
                running_mode=video,
                num_faces=1,
                output_face_blendshapes=True,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )
        self._hands = vision.HandLandmarker.create_from_options(
            vision.HandLandmarkerOptions(
                base_options=opts("hand_landmarker.task"),
                running_mode=video,
                num_hands=2,
                min_hand_detection_confidence=0.4,
                min_hand_presence_confidence=0.4,
                min_tracking_confidence=0.4,
            )
        )
        self._pose = None
        if enable_pose:
            self._pose = vision.PoseLandmarker.create_from_options(
                vision.PoseLandmarkerOptions(
                    base_options=opts("pose_landmarker_lite.task"),
                    running_mode=video,
                    num_poses=1,
                )
            )
        self._last_ts = -1

    def observe(self, rgb: np.ndarray, t_ms: float) -> Observation:
        # VIDEO mode requires strictly increasing integer timestamps.
        ts = max(int(t_ms), self._last_ts + 1)
        self._last_ts = ts
        h, w = rgb.shape[:2]
        aspect = w / h
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        obs = Observation(t=ts / 1000.0, aspect=aspect)

        fr = self._face.detect_for_video(image, ts)
        if fr.face_landmarks:
            obs.face = np.array([[p.x * aspect, p.y] for p in fr.face_landmarks[0]], dtype=np.float32)
            if fr.face_blendshapes:
                obs.blendshapes = {c.category_name: float(c.score) for c in fr.face_blendshapes[0]}

        hr = self._hands.detect_for_video(image, ts)
        for i, lm in enumerate(hr.hand_landmarks):
            cat = hr.handedness[i][0] if i < len(hr.handedness) and hr.handedness[i] else None
            obs.hands.append(
                HandObs(
                    points=np.array([[p.x * aspect, p.y] for p in lm], dtype=np.float32),
                    label=cat.category_name if cat else f"hand{i}",
                    score=float(cat.score) if cat else 1.0,
                )
            )

        if self._pose is not None:
            pr = self._pose.detect_for_video(image, ts)
            if pr.pose_landmarks:
                obs.pose = np.array(
                    [[p.x * aspect, p.y, p.visibility or 0.0] for p in pr.pose_landmarks[0]],
                    dtype=np.float32,
                )
        return obs

    def close(self) -> None:
        for task in (self._face, self._hands, self._pose):
            if task is not None:
                task.close()


@functools.cache
def landmark_connections() -> dict[str, list[list[int]]]:
    """MediaPipe's landmark connection lists as [start, end] index pairs, for the debug overlay."""
    face = vision.FaceLandmarksConnections

    def pairs(conns) -> list[list[int]]:
        return [[c.start, c.end] for c in conns]

    return {
        "face_contours": pairs(face.FACE_LANDMARKS_CONTOURS),
        "face_nose": pairs(face.FACE_LANDMARKS_NOSE),
        "face_irises": pairs(face.FACE_LANDMARKS_LEFT_IRIS + face.FACE_LANDMARKS_RIGHT_IRIS),
        "face_mesh": pairs(face.FACE_LANDMARKS_TESSELATION),
        "hand": pairs(vision.HandLandmarksConnections.HAND_CONNECTIONS),
        "pose": pairs(vision.PoseLandmarksConnections.POSE_LANDMARKS),
    }
