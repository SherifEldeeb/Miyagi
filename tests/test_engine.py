from miyagi.engine import CoachEngine, CoachSettings
from miyagi.vision import Landmarks


def landmarks(touch=None, shift=0):
    face = [(.5 + shift, .3)] * 478
    for index, point in {234:(.35,.35),454:(.65,.35),1:(.5,.33),152:(.5,.60),175:(.5,.58),199:(.5,.56)}.items():
        face[index] = (point[0] + shift, point[1])
    hands = [[touch] * 21] if touch else []
    return Landmarks(face, hands, [(.3,.85),(.7,.85)])


def calibrated(settings=None):
    engine = CoachEngine(settings)
    for i in range(33):
        result = engine.observe(landmarks(), i / 8)
        assert not result["alerts"]
    assert result["calibrated"]
    return engine


def test_chin_only_by_default_and_sustained_contact():
    engine = calibrated()
    assert engine.settings.enabled == ["chin_touch"]
    events = []
    for i in range(33, 65):
        events.extend(engine.observe(landmarks((.5,.59)), i/8)["alerts"])
    assert [event["condition"] for event in events] == ["chin_touch"]
    assert engine.total["chin_touch"] == 1


def test_brief_touches_do_not_accumulate():
    engine = calibrated()
    for i in range(33, 100):
        touch = (.5,.59) if i % 10 < 5 else None
        assert not engine.observe(landmarks(touch), i/8)["alerts"]


def test_tracking_loss_and_time_gaps_break_hold():
    engine = calibrated()
    engine.observe(landmarks((.5,.59)), 4.1)
    engine.observe(Landmarks(), 4.2)
    assert not engine.observe(landmarks((.5,.59)), 8)["alerts"]
    assert not engine.observe(landmarks((.5,.59)), 12)["alerts"]


def test_disabled_conditions_and_pause_do_not_alert():
    engine = calibrated(CoachSettings(enabled=[]))
    for i in range(33, 80):
        assert not engine.observe(landmarks((.5,.59)), i/8)["alerts"]
    engine.configure(CoachSettings())
    assert not engine.observe(landmarks((.5,.59)), 10)["alerts"]


def test_cooldown_and_nearest_region():
    engine = calibrated(CoachSettings(enabled=["chin_touch","face_touch","neck_touch"],cooldown_seconds=3))
    events = []
    for i in range(33, 81):
        events.extend(engine.observe(landmarks((.5,.59)), i/8)["alerts"])
    assert len(events) == 2
    assert all(event["condition"] == "chin_touch" for event in events)
    assert events[1]["time"] - events[0]["time"] >= 3 - 1e-9


def test_neck_requires_shoulders():
    engine = calibrated(CoachSettings(enabled=["neck_touch"]))
    marks = landmarks((.5,.725))
    marks.shoulders = []
    for i in range(33, 65):
        assert "neck_touch" not in engine.observe(marks, i/8)["active"]


def test_recalibration_suppresses_cues():
    engine = calibrated()
    engine.recalibrate()
    result = engine.observe(landmarks((.5,.59)), 5)
    assert not result["calibrated"] and not result["alerts"]


def test_movement_is_optional_and_time_normalized():
    engine = calibrated(CoachSettings(enabled=["movement"],hold_seconds=.5))
    events = []
    for i in range(33, 80):
        events.extend(engine.observe(landmarks(shift=.12 if i%2 else -.12), i/8)["alerts"])
    assert any(event["condition"] == "movement" for event in events)
