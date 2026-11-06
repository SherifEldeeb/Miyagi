import math

import pytest

from miyagi.conditions import default_conditions
from miyagi.detectors import Signal
from miyagi.engine import CoachSession, Tracker
from miyagi.features import FeatureExtractor

from synth import make_hand, obs, run

CX, CY, FW = 0.89, 0.45, 0.22
FH = FW * 1.3


def calibrated_session(all_on=True, **cond_overrides):
    conditions = default_conditions()
    if all_on:  # most tests exercise the (off-by-default) extra habits too
        for c in conditions.values():
            c.enabled = True
    for cid, data in cond_overrides.items():
        conditions[cid].update(data)
    s = CoachSession(conditions=conditions)
    t, res = run(s, 3.5, start=0.0)
    assert res["calibrated"], "baseline should auto-calibrate within ~3 s"
    return s, t


def active(res):
    return {a["id"] for a in res["alerts"]}


def test_zones_are_ordered_top_to_bottom():
    f = FeatureExtractor()(obs(0.0))
    z = f.face.zones
    assert z["hair"].y0 < z["face"].y0 < z["mouth"].y0 < z["beard"].y1 < z["neck"].y1


def test_face_touch_fires_after_min_duration_and_counts_once():
    s, t = calibrated_session()
    cheek = make_hand(CX - 0.3 * FW, CY - 0.05 * FH, scale=0.15)
    t, res = run(s, 0.3, start=t, hands=[cheek])
    assert "face_touch" not in active(res), "should wait for min_duration"
    t, res = run(s, 1.5, start=t, hands=[cheek])
    assert "face_touch" in active(res)
    assert res["counts"]["face_touch"] == 1
    assert {"neck_touch", "hair_touch"}.isdisjoint(active(res))
    box = next(a for a in res["alerts"] if a["id"] == "face_touch")["box"]
    assert box and 0 <= box["x"] <= 1 and box["w"] > 0


def test_neck_touch():
    s, t = calibrated_session()
    t, res = run(s, 2.0, start=t, hands=[make_hand(CX, CY + 0.5 * FH + 0.4 * FH)])
    assert "neck_touch" in active(res)
    assert "face_touch" not in active(res)


def test_hair_touch():
    s, t = calibrated_session()
    t, res = run(s, 2.0, start=t, hands=[make_hand(CX + 0.2 * FW, CY - 0.5 * FH - 0.2 * FH)])
    assert "hair_touch" in active(res)


def test_hand_in_front_of_camera_is_not_a_touch():
    s, t = calibrated_session()
    huge = make_hand(CX - 0.3 * FW, CY, scale=0.6)  # hand/face ratio ~2.7 -> much closer to camera
    t, res = run(s, 2.0, start=t, hands=[huge])
    assert not active(res) & {"face_touch", "hand_to_mouth", "beard_stroke"}


def test_beard_stroke_needs_motion():
    s, t = calibrated_session()
    chin_y = CY + 0.42 * FH
    t, res = run(s, 2.5, start=t, hands=[make_hand(CX + 0.2 * FW, chin_y)])
    assert "beard_stroke" not in active(res), "a static hand on the chin is not stroking"

    def stroking(tt):
        return obs(tt, hands=[make_hand(CX + 0.2 * FW, chin_y + 0.1 * FW * math.sin(tt * 10))])

    t, res = run(s, 2.5, start=t, make=stroking)
    assert "beard_stroke" in active(res)


def test_default_enabled_set_and_border_cue():
    conds = default_conditions()
    enabled = {cid for cid, c in conds.items() if c.enabled}
    assert enabled == {"beard_stroke", "chin_touch", "face_touch", "neck_touch", "leaning_in", "slouching"}
    assert {cid for cid, c in conds.items() if c.focus} == {"beard_stroke", "chin_touch"}
    assert all("border" in c.styles for c in conds.values()), "red border cue is on for every habit"


def test_chin_touch_vs_beard_stroke_are_mutually_exclusive():
    s, t = calibrated_session(all_on=False)
    chin_y = CY + 0.45 * FH
    t, res = run(s, 2.5, start=t, hands=[make_hand(CX + 0.1 * FW, chin_y)])
    assert active(res) == {"chin_touch"}

    t, res = run(s, 3.0, start=t)  # hands down, let it end and cool down

    def stroking(tt):
        return obs(tt, hands=[make_hand(CX + 0.1 * FW, chin_y + 0.1 * FW * math.sin(tt * 10))])

    t, res = run(s, 2.5, start=t, make=stroking)
    assert active(res) == {"beard_stroke"}, "stroking must not also count as chin touching"


def test_hand_under_beard_below_jaw_counts_as_chin():
    """Beards extend below the jaw line the face mesh tracks."""
    s, t = calibrated_session(all_on=False)
    t, res = run(s, 2.5, start=t, hands=[make_hand(CX, CY + 0.5 * FH + 0.1 * FH)])
    assert "chin_touch" in active(res)


def test_propping_head_on_hand_counts_as_chin():
    s, t = calibrated_session(all_on=False)
    # fingertips up on the cheek, palm (scale small) sitting on the jaw
    t, res = run(s, 2.5, start=t, hands=[make_hand(CX + 0.3 * FW, CY + 0.1 * FH, scale=0.06)])
    assert "chin_touch" in active(res)


def test_cheek_touch_alerts_by_default_but_hair_does_not():
    s, t = calibrated_session(all_on=False)
    t, res = run(s, 2.0, start=t, hands=[make_hand(CX - 0.3 * FW, CY - 0.05 * FH)])  # cheek touch
    assert active(res) == {"face_touch"}
    t, res = run(s, 4.0, start=t)
    t, res = run(s, 2.0, start=t, hands=[make_hand(CX + 0.2 * FW, CY - 0.5 * 1.3 * FW - 0.2 * 1.3 * FW)])  # hair
    assert not active(res), "hair touching is off by default"


def test_excessive_movement():
    s, t = calibrated_session()
    t, res = run(s, 4.0, start=t)
    assert "excessive_movement" not in active(res)

    def rocking(tt):
        return obs(tt, face_kwargs={"cx": CX + 0.4 * FW * math.sin(tt * 2 * math.pi)})

    t, res = run(s, 5.0, start=t, make=rocking)
    assert "excessive_movement" in active(res)


def test_looking_away():
    s, t = calibrated_session()
    t, res = run(s, 4.0, start=t, face_kwargs={"yaw": 1.2})
    assert "looking_away" in active(res)


def test_out_of_frame():
    s, t = calibrated_session()
    t, res = run(s, 1.0, start=t, face=False)
    assert "out_of_frame" not in active(res)
    t, res = run(s, 3.0, start=t, face=False)
    assert "out_of_frame" in active(res)


def test_frowning_from_blendshapes():
    s, t = calibrated_session()
    t, res = run(s, 4.0, start=t, blend={"browDownLeft": 0.9, "browDownRight": 0.9})
    assert "frowning" in active(res)


def test_disabled_condition_never_fires():
    s, t = calibrated_session(face_touch={"enabled": False})
    t, res = run(s, 2.0, start=t, hands=[make_hand(CX - 0.3 * FW, CY - 0.05 * FH)])
    assert "face_touch" not in active(res)


def test_face_memory_bridges_occlusion():
    """Hand covers the face -> mesh lost for a moment; touch should persist."""
    s, t = calibrated_session()
    hand = make_hand(CX - 0.3 * FW, CY - 0.05 * FH)
    t, res = run(s, 1.5, start=t, hands=[hand])
    assert "face_touch" in active(res)
    t, res = run(s, 0.5, start=t, hands=[hand], face=False)
    assert "face_touch" in active(res)


def test_tracker_hysteresis_cooldown_and_escalation():
    cfg = default_conditions()["face_touch"]
    cfg.update({"min_duration": 0.5, "cooldown": 2.0})
    tr, t, fired = Tracker(), 0.0, 0

    def feed(on, seconds):
        nonlocal t, fired
        for _ in range(int(seconds * 20)):
            fired += tr.update(t, Signal(on), cfg)
            t += 0.05

    feed(True, 1.0)
    assert tr.active and fired == 1
    feed(False, 0.2)
    assert tr.active, "brief dropouts must not end the alert (linger)"
    feed(False, 1.0)
    assert not tr.active
    feed(True, 1.0)  # within cooldown -> not counted
    assert fired == 1
    feed(False, 3.0)
    for _ in range(6):
        feed(True, 1.0)
        feed(False, 3.0)
    assert fired == 7 and tr.severity == 3


def test_sensitivity_maps_param_between_hard_and_easy():
    c = default_conditions()["excessive_movement"]
    c.update({"sensitivity": 0})
    hard = c.param
    c.update({"sensitivity": 100})
    easy = c.param
    assert hard == pytest.approx(c.param_hard) and easy == pytest.approx(c.param_easy)


def test_stats_shape():
    s, t = calibrated_session()
    run(s, 2.0, start=t, hands=[make_hand(CX - 0.3 * FW, CY - 0.05 * FH)])
    st = s.stats()
    assert st["habits"]["face_touch"]["count"] == 1
    assert st["duration_seconds"] > 5
