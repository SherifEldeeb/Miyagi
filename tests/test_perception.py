import pytest

from miyagi.models import models_present


@pytest.mark.skipif(not models_present(), reason="MediaPipe models not downloaded")
def test_mediapipe_perception_smoke():
    import numpy as np

    from miyagi.perception import MediaPipePerception

    p = MediaPipePerception()
    try:
        o = p.observe(np.zeros((360, 640, 3), dtype=np.uint8), 1000)
        assert o.face is None and o.hands == []
        o2 = p.observe(np.zeros((360, 640, 3), dtype=np.uint8), 1000)  # same ts must not crash
        assert o2.t > o.t
    finally:
        p.close()
