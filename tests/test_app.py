import base64
import io

from fastapi.testclient import TestClient
from PIL import Image

import miyagi.app as module
from miyagi.providers.cloud import Review

client = TestClient(module.app)
ORIGIN = {"origin": "http://testserver"}


def jpeg():
    buffer = io.BytesIO()
    Image.new("RGB", (64,64)).save(buffer, "JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_home_and_defaults():
    response = client.get("/")
    assert response.status_code == 200
    assert "Chin &amp; beard touching" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/api/status").json()["cloud"]["provider"] == "gemini"


def test_review_requires_same_origin_and_consent():
    body = {"frames": [jpeg()], "consent": True}
    assert client.post("/api/review", json=body).status_code == 403
    assert client.post("/api/review", headers={"origin":"https://evil.invalid"}, json=body).status_code == 403
    body["consent"] = False
    assert client.post("/api/review", headers=ORIGIN, json=body).status_code == 403


def test_auth_validation_and_image_limits():
    body = {"provider":"openai", "auth":"vertex_adc", "frames":[jpeg()], "consent":True}
    assert client.post("/api/review", headers=ORIGIN, json=body).status_code == 422
    body.update(provider="gemini",auth="api_key",frames=["bad-image"])
    assert client.post("/api/review", headers=ORIGIN, json=body).status_code == 400
    assert client.post("/api/review", headers=ORIGIN, content=b"x"*2_100_001).status_code == 413


def test_review_success_rate_limit_and_error_redaction(monkeypatch):
    monkeypatch.setattr(module, "last_review", -1e9)
    monkeypatch.setattr(module.SDKReviewer, "review", lambda *args: Review(observations=[],note="No person visible."))
    body={"frames":[jpeg()],"consent":True}
    response=client.post("/api/review",headers=ORIGIN,json=body)
    assert response.status_code == 200 and response.json()["observations"] == []
    assert client.post("/api/review",headers=ORIGIN,json=body).status_code == 429
    monkeypatch.setattr(module, "last_review", -1e9)
    def failing(*args):
        raise RuntimeError("sensitive request text must never appear")
    monkeypatch.setattr(module.SDKReviewer,"review",failing)
    response=client.post("/api/review",headers=ORIGIN,json=body)
    assert response.status_code == 502
    assert "sensitive" not in response.text


def test_websocket_rejects_cross_origin():
    from starlette.websockets import WebSocketDisconnect
    import pytest
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/coach",headers={"origin":"https://evil.invalid"}):
            pass


def test_camera_protocol_without_physical_camera(monkeypatch):
    from miyagi.vision import Landmarks
    closed=[]
    class FakeVision:
        def detect(self,*args): return Landmarks()
        def close(self): closed.append(True)
    monkeypatch.setattr(module,"MediaPipeProvider",FakeVision)
    with client.websocket_connect("/ws/coach", headers=ORIGIN) as socket:
        assert socket.receive_json() == {"ready":True}
        socket.send_json({"type":"settings","settings":{"enabled":["chin_touch"]}})
        socket.send_bytes(base64.b64decode(jpeg()))
        result=socket.receive_json()
        assert result["tracking"] is False and result["alerts"] == []
    assert closed
