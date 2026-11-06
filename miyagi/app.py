import asyncio
import base64
import binascii
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from miyagi.config import missing_models
from miyagi.engine import CoachEngine, CoachSettings
from miyagi.providers.cloud import ReviewRequest, SDKReviewer, public_configuration
from miyagi.vision import MediaPipeProvider

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Miyagi", docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])
app.mount("/static", StaticFiles(directory=STATIC), name="static")
camera_lock = asyncio.Lock()
review_lock = asyncio.Lock()
last_review = -1e9


def same_origin(origin: str | None, host: str) -> bool:
    if not origin:
        return False
    parsed = urlparse(origin)
    return parsed.scheme in ("http", "https") and parsed.netloc == host


@app.middleware("http")
async def boundaries(request: Request, call_next):
    if request.method == "POST":
        if not same_origin(request.headers.get("origin"), request.headers.get("host", "")):
            return JSONResponse({"detail": "Same-origin requests only."}, status_code=403)
        # Bound the body even for chunked requests, before JSON parsing.
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 2_100_000:
                return JSONResponse({"detail": "Request too large."}, status_code=413)
        request._body = bytes(data)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
    return response


@app.get("/")
async def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
async def status():
    missing = missing_models()
    return {"local_ready": not missing, "missing_models": missing,
            "detector": "ONNX temporal" if os.getenv("MIYAGI_ONNX_MODEL") else "Local landmarks + timing rules",
            "cloud": public_configuration()}


def decode_frame(data: bytes) -> np.ndarray:
    if len(data) > 500_000:
        raise ValueError("Frame exceeds 500 KB.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG" or image.width > 960 or image.height > 720:
                raise ValueError("Send JPEG frames at most 960×720.")
            return np.array(image.convert("RGB"))
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Invalid JPEG frame.") from exc


def sanitize_jpeg(encoded: str) -> bytes:
    if len(encoded) > 670_000:
        raise ValueError("Frame too large.")
    rgb = decode_frame(base64.b64decode(encoded, validate=True))
    output = io.BytesIO()
    Image.fromarray(rgb).save(output, format="JPEG", quality=75)
    return output.getvalue()


@app.post("/api/review")
async def cloud_review(body: ReviewRequest):
    global last_review
    if not body.consent:
        raise HTTPException(403, "Enable cloud snapshots before sending images.")
    if review_lock.locked() or time.monotonic() - last_review < 10:
        raise HTTPException(429, "Wait at least 10 seconds between cloud reviews.")
    try:
        images = [sanitize_jpeg(frame) for frame in body.frames]
    except (ValueError, binascii.Error):
        raise HTTPException(400, "Invalid or oversized JPEG snapshots.")
    async with review_lock:
        last_review = time.monotonic()
        try:
            result = await asyncio.to_thread(SDKReviewer().review, body, images)
        except Exception as exc:
            # Never return SDK exceptions, which can contain request bodies or credentials.
            name = type(exc).__name__
            raise HTTPException(502, f"Cloud review failed ({name}). Check the selected model, server credentials, quota, and region.") from None
    return result.model_dump()


@app.websocket("/ws/coach")
async def coach(socket: WebSocket):
    if not same_origin(socket.headers.get("origin"), socket.headers.get("host", "")):
        await socket.close(code=1008)
        return
    await socket.accept()
    if camera_lock.locked():
        await socket.send_json({"error": "A camera session is already running. Stop it before starting another."})
        await socket.close(code=1013)
        return
    async with camera_lock:
        provider = None
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="miyagi-vision")
        loop = asyncio.get_running_loop()
        engine = CoachEngine()
        classifier = None
        try:
            provider = await loop.run_in_executor(pool, MediaPipeProvider)
            if path := os.getenv("MIYAGI_ONNX_MODEL"):
                from miyagi.providers.temporal import OnnxClassifier
                classifier = await loop.run_in_executor(pool, OnnxClassifier, path)
            await socket.send_json({"ready": True})
            started = time.monotonic()
            last_ms = -1
            while True:
                message = await socket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("text") is not None:
                    if len(message["text"]) > 4000:
                        raise ValueError("Settings message too large")
                    command = json.loads(message["text"])
                    if command.get("type") == "settings":
                        engine.configure(CoachSettings.model_validate(command.get("settings", {})))
                    elif command.get("type") == "calibrate":
                        engine.recalibrate()
                        if classifier:
                            classifier.reset()
                    continue
                if message.get("bytes") is None:
                    continue
                rgb = decode_frame(message["bytes"])
                t = time.monotonic() - started
                timestamp = max(last_ms + 1, int(t * 1000))
                last_ms = timestamp
                marks = await loop.run_in_executor(pool, provider.detect, rgb, timestamp)
                result = engine.observe(marks, t, classifier)
                result["elapsed"] = t
                await socket.send_json(result)
        except (WebSocketDisconnect, RuntimeError, ValueError, ValidationError) as exc:
            try:
                await socket.send_json({"error": "Session stopped. Check model files, camera frames, and settings.",
                                        "kind": type(exc).__name__})
            except (RuntimeError, WebSocketDisconnect):
                pass
        except Exception:
            try:
                await socket.send_json({"error": "Local detector failed. Restart the session and check model installation."})
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            if provider:
                await loop.run_in_executor(pool, provider.close)
            pool.shutdown(wait=False)
            try:
                await socket.close()
            except (RuntimeError, WebSocketDisconnect):
                pass
