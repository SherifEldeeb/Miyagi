import struct

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from miyagi.engine import CoachSession
from miyagi.learned import FEATURE_DIMS, PersonalModel
from miyagi.report import generate_report
from miyagi.server import create_app

from synth import ASPECT, make_hand, obs, run

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


def test_websocket_roundtrip(tmp_path):
    app = create_app(perception_factory=FakePerception, personal=PersonalModel(tmp_path))
    client = TestClient(app)
    conds = client.get("/api/conditions").json()
    assert conds["conditions"][0]["id"] == "beard_stroke" and conds["focus_area"]
    assert "learned" in conds["modes"]
    assert client.get("/").status_code == 200
    coach = client.get("/coach")
    assert coach.status_code == 200 and 'data-mode="coach"' in coach.text
    assert client.get("/static/app.js").status_code == 200
    links = client.get("/api/landmarks").json()
    assert len(links["hand"]) == 21 and len(links["face_mesh"]) > 2000 and links["face_contours"]
    assert links["face_keys"]["152"] == "chin" and links["hand_tips"] == [4, 8, 12, 16, 20]

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "config", "conditions": {"face_touch": {"sensitivity": 80}}, "debug": True})
        ws.send_bytes(_frame(1000.0))
        res = ws.receive_json()
        assert res["type"] == "result" and res["face_box"] is not None
        assert "zones" in res["debug"] and len(res["debug"]["face"]) == 478
        ws.send_json({"type": "config", "debug": False})
        ws.send_bytes(_frame(1100.0))
        assert "debug" not in ws.receive_json()
        ws.send_bytes(b"\x00" * 12)
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "report"})
        rep = ws.receive_json()
        assert rep["type"] == "report" and rep["markdown"].startswith("## Session summary")
        assert set(rep) == {"type", "stats", "markdown"}
        ws.send_json({"type": "status"})
        assert ws.receive_json()["personal"]["ready"] is False


def test_report_lists_habits_with_tips():
    stats = {
        "duration_seconds": 600,
        "enabled": ["face_touch", "chin_touch"],
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
    md = generate_report(stats)
    assert md.startswith("## Session summary (10 min 0 s)")
    assert "**4** moments across **1** habits" in md and "**Touching face**: 4x" in md
    assert "### Went well" in md and "touching chin" in md


def test_report_with_no_habits():
    md = generate_report({"duration_seconds": 45, "enabled": ["beard_stroke"], "habits": {}})
    assert md.startswith("## Session summary (45 s)") and "No habits detected" in md
    assert "Focus on" not in md


def test_debug_payload_draws_everything_in_frame_coordinates():
    s = CoachSession()
    s.debug = True
    pose = np.array([[0.5 * ASPECT, 0.8, 0.9]] * 33, dtype=np.float32)
    hand = make_hand(CX, CY + 0.6 * FW)  # on the beard
    o = obs(1.0, hands=[hand], pose=pose, blend={"jawOpen": 0.42, "browDownLeft": 0.2, "eyeBlinkLeft": 0.01})
    d = s.step(o)["debug"]
    # x is divided by the aspect ratio, so every point lands in [0, 1] of the frame
    assert d["face"][152] == pytest.approx([o.face[152][0] / ASPECT, o.face[152][1]], abs=1e-3)
    assert d["hands"][0][8] == pytest.approx([hand.points[8][0] / ASPECT, hand.points[8][1]], abs=1e-4)
    assert d["pose"][0] == pytest.approx([0.5, 0.8, 0.9], abs=1e-3)
    assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in d["face"])
    # strongest expressions first, tiny ones dropped
    assert list(d["blendshapes"]) == ["jawOpen", "browDownLeft"]
    # one signal row per enabled habit: [fired this frame, smoothed level, alert active]
    assert set(d["signals"]) == {cid for cid, c in s.conditions.items() if c.enabled}
    assert d["levels"] == [0.6, 0.3]
    fired, level, active = d["signals"]["face_touch"]
    assert fired in (0, 1) and 0 <= level <= 1 and active is False


def test_debug_payload_without_a_face():
    s = CoachSession()
    s.debug = True
    d = s.step(obs(1.0, face=False))["debug"]
    assert d["face"] is None and d["zones"] == {} and d["pose"] is None and d["hands"] == []
    s.debug = False
    assert "debug" not in s.step(obs(1.1))
