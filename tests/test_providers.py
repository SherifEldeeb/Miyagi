from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from miyagi.providers.cloud import ReviewRequest, SDKReviewer, parse_review

EMPTY = '{"observations":[],"note":"No visible person."}'


def test_parse_validates_content():
    assert parse_review("```json\n"+EMPTY+"\n```").observations == []
    with pytest.raises(ValueError):
        parse_review('{"observations":[{"condition":"anxiety","confidence":1,"cue":"bad"}],"note":""}')
    with pytest.raises(ValueError):
        parse_review('{"observations":[],"note":"ok","extra":"ignored?"}')


@pytest.mark.parametrize("provider,auth",[("gemini","api_key"),("gemini","vertex_adc"),("gemini","vertex_api_key"),("openai","api_key"),("anthropic","api_key"),("anthropic","vertex_adc")])
def test_sdk_routing_and_auth(provider,auth,monkeypatch):
    for variable in ("OPENAI_API_KEY","ANTHROPIC_API_KEY","GEMINI_API_KEY","VERTEX_API_KEY"):
        monkeypatch.setenv(variable,"test-placeholder")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT","test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION","global")
    fake=MagicMock();fake.__enter__.return_value=fake
    fake.models.generate_content.return_value=SimpleNamespace(text=EMPTY)
    fake.responses.create.return_value=SimpleNamespace(output_text=EMPTY)
    fake.messages.create.return_value=SimpleNamespace(content=[SimpleNamespace(type="text",text=EMPTY)])
    constructor=MagicMock(return_value=fake)
    credentials=object()
    monkeypatch.setattr("google.auth.default",lambda **kwargs:(credentials,"detected-project"))
    if provider=="gemini": monkeypatch.setattr("google.genai.Client",constructor)
    elif provider=="openai":monkeypatch.setattr("openai.OpenAI",constructor)
    else:monkeypatch.setattr("anthropic.AnthropicVertex" if auth=="vertex_adc" else "anthropic.Anthropic",constructor)
    result=SDKReviewer().review(ReviewRequest(provider=provider,auth=auth,frames=["placeholder"]),[b"jpeg"])
    assert not result.observations
    kwargs=constructor.call_args.kwargs
    if auth=="vertex_adc":
        assert "api_key" not in kwargs
        assert kwargs.get("project",kwargs.get("project_id"))=="test-project"
        if provider=="gemini":assert kwargs["credentials"] is credentials and kwargs["vertexai"]
    else:
        assert kwargs["api_key"]=="test-placeholder"
    if provider=="openai":assert fake.responses.create.call_args.kwargs["store"] is False
    if provider=="gemini":
        config=fake.models.generate_content.call_args.kwargs["config"]
        assert config.response_json_schema["additionalProperties"] is False
        assert config.response_schema is None


def test_disabled_cloud_conditions_filtered(monkeypatch):
    monkeypatch.setattr(SDKReviewer,"_gemini",lambda *args:'{"observations":[{"condition":"face_touch","confidence":0.9,"cue":"Rest hand"}],"note":"test"}')
    assert not SDKReviewer().review(ReviewRequest(frames=["placeholder"]),[b"jpeg"]).observations
