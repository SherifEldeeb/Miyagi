"""Synthetic landmark generators so detectors can be tested without a camera."""

from __future__ import annotations

import numpy as np

from meeting_coach.observation import HandObs, Observation

ASPECT = 16 / 9


def make_face(cx: float = 0.89, cy: float = 0.45, fw: float = 0.22, yaw: float = 0.0) -> np.ndarray:
    """A 478-point 'mesh' with the indices the app relies on placed sensibly."""
    fh = fw * 1.3
    rng = np.random.default_rng(0)
    ang = rng.uniform(0, 2 * np.pi, 478)
    rad = np.sqrt(rng.uniform(0, 1, 478))
    pts = np.stack([cx + np.cos(ang) * rad * fw / 2, cy + np.sin(ang) * rad * fh / 2], axis=1)

    def put(i, dx, dy):
        pts[i] = [cx + dx * fw, cy + dy * fh]

    put(10, 0, -0.5)
    put(152, 0, 0.5)
    put(234, -0.5, 0)
    put(454, 0.5, 0)
    put(1, yaw * 0.5, 0.05)
    put(13, 0, 0.22)
    put(14, 0, 0.27)
    put(61, -0.18, 0.25)
    put(291, 0.18, 0.25)
    put(33, -0.35, -0.12)
    put(133, -0.12, -0.12)
    put(362, 0.12, -0.12)
    put(263, 0.35, -0.12)
    put(468, -0.235, -0.12)
    put(473, 0.235, -0.12)
    return pts.astype(np.float32)


def make_hand(tx: float, ty: float, scale: float = 0.15, label: str = "Right") -> HandObs:
    """Hand whose fingertips cluster around (tx, ty), wrist below."""
    pts = np.zeros((21, 2), dtype=np.float32)
    wrist = np.array([tx, ty + 2.0 * scale])
    pts[0] = wrist
    for finger, base in enumerate(range(1, 21, 4)):
        off = (finger - 2) * 0.12 * scale
        for j in range(4):
            frac = (j + 1) / 4
            pts[base + j] = [tx + off, wrist[1] - frac * 2.0 * scale + (0.02 * scale if j == 3 else 0)]
    pts[9] = [tx, wrist[1] - scale]  # middle MCP -> scale = wrist..MCP
    return HandObs(points=pts, label=label)


def obs(t: float, face=True, hands=(), face_kwargs=None, pose=None, blend=None) -> Observation:
    return Observation(
        t=t,
        aspect=ASPECT,
        face=make_face(**(face_kwargs or {})) if face else None,
        hands=list(hands),
        pose=pose,
        blendshapes=blend or {},
    )


def run(session, seconds: float, start: float, fps: float = 15, **kw):
    """Feed constant (or callable-per-t) observations; returns (end_t, last_result)."""
    t, res, n = start, None, int(seconds * fps)
    for _ in range(n):
        o = kw["make"](t) if "make" in kw else obs(t, **kw)
        res = session.step(o)
        t += 1 / fps
    return t, res
