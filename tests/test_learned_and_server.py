import struct

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from meeting_coach.engine import CoachSession
from meeting_coach.learned import FEATURE_DIMS, PersonalModel
from meeting_coach.report import generate_report, rule_based_report
from meeting_coach.server import create_app

from synth import make_hand, obs, run

CX, CY, FW = 0.89, 0.45, 0.22


@pytest.fixture
def personal(tmp_path):
    return PersonalModel(tmp_path)


def test_teach_train_and_learned_mode(personal):
    s = CoachSession(personal=personal)
    t, _ = run(s, 3.5, start=0.0)  # calibrate

    # The user's own idiosyncratic habit: a hand resting *beside* the face,
    # which the rule zones don't cover. Teach it as "chin_touch".
    def custom(tt):
        return obs(tt, hands=[make_hand(CX + 1.0 * FW, CY + 0.1 * FW * np.sin(tt * 3))])

    s.start_teaching("neutral", 5)
    t, res = run(s, 5.2, start=t)
    s.start_teaching("chin_touch", 5)
    t, res = run(s, 5.2, start=t, make=custom)
    assert personal.counts() == {"neutral": pytest.approx(76, abs=3), "chin_touch": pytest.approx(76, abs=3)}

    result = personal.train()
    assert result["ok"] and set(result["classes"]) == {"neutral", "chin_touch"}
    assert result["holdout_accuracy"] >= 0.9

    # Rules don't see it...
    t, res = run(s, 2.0, start=t, make=custom)
    assert "chin_touch" not in {a["id"] for a in res["alerts"]}
    # ...the personal model does.
    s.configure({"chin_touch": {"mode": "either"}})
    t, res = run(s, 2.0, start=t, make=custom)
    assert "chin_touch" in {a["id"] for a in res["alerts"]}

    # Persistence round-trip.
    again = PersonalModel(personal.dir)
    assert again.ready and again.classes == personal.classes


def test_train_requires_neutral(personal):
    personal.add(np.zeros(FEATURE_DIMS, dtype=np.float32), "face_touch")
    assert personal.train()["ok"] is False


class FakePerception:
    def __init__(self):
        self.closed = False

    def observe(self, rgb, t_ms):
        assert rgb.ndim == 3 and rgb.shape[2] == 3
        return obs(t_ms / 1000.0)

    def close(self):
        self.closed = True


def _frame(t_ms: float) -> bytes:
    img = np.zeros((90, 160, 3), dtype=np.uint8)
    ok, jpeg = cv2.imencode(".jpg", img)
    return struct.pack("<d", t_ms) + jpeg.tobytes()


def test_websocket_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MEETING_COACH_LLM", "none")
    app = create_app(perception_factory=FakePerception, personal=PersonalModel(tmp_path))
    client = TestClient(app)
    conds = client.get("/api/conditions").json()
    assert conds["conditions"][0]["id"] == "beard_stroke" and conds["focus_area"]
    assert "learned" in conds["modes"]
    assert client.get("/").status_code == 200
    coach = client.get("/coach")
    assert coach.status_code == 200 and 'data-mode="coach"' in coach.text
    assert client.get("/static/app.js").status_code == 200

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "config", "conditions": {"face_touch": {"sensitivity": 80}}, "debug": True})
        ws.send_bytes(_frame(1000.0))
        res = ws.receive_json()
        assert res["type"] == "result" and res["face_box"] is not None
        assert "zones" in res["debug"]
        ws.send_bytes(b"\x00" * 12)
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "report"})
        rep = ws.receive_json()
        assert rep["type"] == "report" and rep["source"] == "rules" and rep["markdown"]
        ws.send_json({"type": "status"})
        assert ws.receive_json()["personal"]["ready"] is False


def test_report_falls_back_when_gemini_unconfigured(monkeypatch):
    for k in ("MEETING_COACH_LLM", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"):
        monkeypatch.delenv(k, raising=False)
    import asyncio

    stats = {
        "duration_seconds": 600,
        "enabled": ["face_touch"],
        "habits": {
            "face_touch": {
                "label": "Touching face",
                "emoji": "🙈",
                "count": 4,
                "total_seconds": 9,
                "longest_seconds": 3,
                "per_10_min": 4,
                "first_at_s": 30,
                "minutes": [0.5, 2, 5, 9],
            }
        },
    }
    rep = asyncio.run(generate_report(stats))
    assert rep["source"] == "rules" and "GEMINI_API_KEY" in rep["note"]
    assert "Touching face" in rule_based_report(stats)
