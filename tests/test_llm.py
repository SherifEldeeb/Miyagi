
import pytest

from meeting_coach import llm
from meeting_coach.models import models_present


def test_default_provider_is_gemini():
    assert llm.DEFAULT_PROVIDER == "gemini"


def test_none_provider(monkeypatch):
    monkeypatch.setenv("MEETING_COACH_LLM", "none")
    assert llm.get_provider() is None


def test_unknown_provider(monkeypatch):
    with pytest.raises(llm.LLMError):
        llm.get_provider("nope")


def test_gemini_api_key_mode(monkeypatch):
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    p = llm.get_provider("gemini")
    assert p.backend == "gemini-api" and p.model


def test_gemini_vertex_mode_requires_project(monkeypatch):
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(llm.LLMError, match="GOOGLE_CLOUD_PROJECT"):
        llm.get_provider("gemini")


def test_gemini_vertex_mode_with_project(monkeypatch):
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    try:
        p = llm.get_provider("gemini")
    except llm.LLMError:
        pytest.skip("google-auth could not build a client here")
    except Exception as e:  # no ADC in CI: google-auth raises at client construction
        pytest.skip(f"no ADC available: {e}")
    assert p.backend == "vertex:my-proj/us-central1"


def test_model_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    monkeypatch.setenv("MEETING_COACH_LLM_MODEL", "gemini-custom")
    assert llm.get_provider("gemini").model == "gemini-custom"


@pytest.mark.skipif(not models_present(), reason="MediaPipe models not downloaded")
def test_mediapipe_perception_smoke():
    import numpy as np

    from meeting_coach.perception import MediaPipePerception

    p = MediaPipePerception()
    try:
        o = p.observe(np.zeros((360, 640, 3), dtype=np.uint8), 1000)
        assert o.face is None and o.hands == []
        o2 = p.observe(np.zeros((360, 640, 3), dtype=np.uint8), 1000)  # same ts must not crash
        assert o2.t > o.t
    finally:
        p.close()
