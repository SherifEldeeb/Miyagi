import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MODEL_DIR = Path(os.getenv("MIYAGI_MODEL_DIR", "models"))
MODEL_URLS = {
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "pose_landmarker_lite.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
}


def model_name(provider: str, auth: str = "api_key") -> str:
    if provider == "anthropic" and auth == "vertex_adc":
        return os.getenv("MIYAGI_ANTHROPIC_VERTEX_MODEL", "claude-haiku-5-5")
    return os.getenv(f"MIYAGI_{provider.upper()}_MODEL", {
        "gemini": "gemini-3.8-flash", "openai": "gpt-6-luna", "anthropic": "claude-haiku-5-5",
    }[provider])


def missing_models() -> list[str]:
    return [name for name in MODEL_URLS if not (MODEL_DIR / name).is_file()]
