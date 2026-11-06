"""FastAPI app: static UI + a WebSocket that receives frames and returns alerts.

Wire protocol on ``/ws``:

* client -> server, **binary**: 8-byte little-endian float64 timestamp (ms,
  client monotonic clock) followed by a JPEG frame. The client sends the next
  frame only after it receives the result, so the server never queues up.
* client -> server, **text** JSON control messages:
  ``{"type": "config", "conditions": {id: {...}}, "debug": bool}``,
  ``{"type": "calibrate"}``, ``{"type": "reset"}``, ``{"type": "report"}``,
  ``{"type": "teach", "label": id|"neutral", "seconds": 10}``,
  ``{"type": "train"}``, ``{"type": "teach_clear", "label": id|null}``,
  ``{"type": "status"}`` (personal-model status).
* server -> client: JSON ``result`` per frame, plus ``report``, ``trained``,
  ``personal``, ``error`` messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .conditions import ALERT_STYLES, DETECTION_MODES, FOCUS_AREA, default_conditions
from .engine import CoachSession
from .learned import NEUTRAL, PersonalModel
from .report import generate_report

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def _default_perception():
    from .perception import MediaPipePerception

    return MediaPipePerception()


def decode_frame(data: bytes) -> tuple[float, np.ndarray]:
    if len(data) < 9:
        raise ValueError("frame too short")
    (t_ms,) = struct.unpack("<d", data[:8])
    img = cv2.imdecode(np.frombuffer(data[8:], dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode JPEG")
    return t_ms, cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def create_app(perception_factory: Callable | None = None, personal: PersonalModel | None = None) -> FastAPI:
    app = FastAPI(title="Miyagi")
    factory = perception_factory or _default_perception
    app.state.personal = personal or PersonalModel()

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/coach")
    async def coach():
        """Coach-only ("production") view: camera + cues, no other UI."""
        return FileResponse(STATIC / "coach.html")

    @app.get("/api/conditions")
    async def conditions():
        return {
            "conditions": [c.to_dict() for c in default_conditions().values()],
            "focus_area": FOCUS_AREA,
            "styles": ALERT_STYLES,
            "modes": DETECTION_MODES,
            "personal": app.state.personal.status(),
        }

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        try:
            perception = await asyncio.to_thread(factory)
        except Exception as e:  # models missing, no network for download, ...
            log.exception("Perception init failed")
            await websocket.send_json({"type": "error", "message": f"Vision models failed to load: {e}"})
            await websocket.close()
            return
        session = CoachSession(perception=perception, personal=app.state.personal)
        try:
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    try:
                        t_ms, rgb = decode_frame(msg["bytes"])
                    except ValueError as e:
                        await websocket.send_json({"type": "error", "message": str(e)})
                        continue
                    result = await asyncio.to_thread(session.process_frame, rgb, t_ms)
                    await websocket.send_json(result)
                elif msg.get("text") is not None:
                    await _control(websocket, session, app.state.personal, msg["text"])
        except WebSocketDisconnect:
            pass
        finally:
            perception.close()

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


async def _control(websocket: WebSocket, session: CoachSession, personal: PersonalModel, text: str) -> None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "message": "bad JSON"})
        return
    kind = data.get("type")
    if kind == "config":
        session.configure(data.get("conditions") or {})
        if "debug" in data:
            session.debug = bool(data["debug"])
    elif kind == "calibrate":
        session.calibrate()
    elif kind == "reset":
        session.reset()
    elif kind == "report":
        stats = session.stats()
        await websocket.send_json({"type": "report", "stats": stats, "markdown": generate_report(stats)})
    elif kind == "teach":
        try:
            session.start_teaching(str(data.get("label", NEUTRAL)), float(data.get("seconds", 10)))
        except ValueError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
    elif kind == "train":
        result = await asyncio.to_thread(personal.train)
        await websocket.send_json({"type": "trained", **result, "personal": personal.status()})
    elif kind == "teach_clear":
        personal.clear(data.get("label"))
        await websocket.send_json({"type": "personal", "personal": personal.status()})
    elif kind == "status":
        await websocket.send_json({"type": "personal", "personal": personal.status()})
    else:
        await websocket.send_json({"type": "error", "message": f"unknown message type {kind!r}"})
