"""Provider contract boundaries without external model calls."""
import json

import pytest

from app.assistant import providers


def profile(protocol="openai_compatible", **changes):
    values = {
        "name": "qwen", "protocol": protocol, "base_url": "https://models.example/api/v1",
        "model": "qwen3.5:9b", "auth_type": "bearer", "api_key_ref": "env:MODEL_KEY",
        "network_scope": "external",
    }
    values.update(changes)
    return providers.validate(values)


def test_custom_endpoint_keeps_prefix_and_uses_own_key(monkeypatch):
    p = profile()
    monkeypatch.setenv("MODEL_KEY", "example-secret")
    assert providers._endpoint(p) == "https://models.example/api/v1/chat/completions"
    assert providers._secret(p) == "example-secret"
    assert "example-secret" not in json.dumps({**p, "api_key_ref": "env:MODEL_KEY"})


def test_local_only_rejects_external_before_network(monkeypatch):
    monkeypatch.setattr(providers, "_request", lambda *_: pytest.fail("network used"))
    with pytest.raises(providers.ProfileError, match="local_only"):
        providers.generate(profile(), [{"role": "user", "content": "hi"}], "system",
                           privacy_mode="local_only")


@pytest.mark.parametrize("protocol,response,text", [
    ("openai_compatible", {"choices": [{"message": {"content": "yes"}}],
                           "usage": {"prompt_tokens": 2, "completion_tokens": 1}}, "yes"),
    ("ollama", {"message": {"content": "local"}, "prompt_eval_count": 2, "eval_count": 1}, "local"),
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "cloud"}]}}],
                "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 1}}, "cloud"),
])
def test_normalized_generation(monkeypatch, protocol, response, text):
    captured = {}

    def fake_request(profile, body, timeout):
        captured.update(body)
        return response

    monkeypatch.setattr(providers, "_request", fake_request)
    p = profile(protocol, **({"base_url": "http://127.0.0.1:11434", "network_scope": "internal",
                             "auth_type": "none", "api_key_ref": None} if protocol == "ollama" else {}))
    result = providers.generate(p, [{"role": "user", "content": "question"}], "system")
    assert result.text == text
    assert result.input_tokens == 2
    assert result.output_tokens == 1
    assert "response_format" not in captured


def test_unverified_schema_is_not_sent(monkeypatch):
    bodies = []
    monkeypatch.setattr(providers, "_request", lambda _p, body, _t: bodies.append(body) or
                        {"choices": [{"message": {"content": '{}'}}]})
    p = profile()
    result = providers.generate(p, [{"role": "user", "content": "json"}], "system", {"type": "object"})
    assert not result.structured_output
    assert "response_format" not in bodies[0]


def test_secret_never_in_public_profile(monkeypatch):
    monkeypatch.setenv("MODEL_KEY", "example-secret")
    p = profile() | {"profile_id": 5, "version": 1}
    result = providers.public(p)
    assert result["credential_configured"]
    assert "example-secret" not in json.dumps(result)
    assert "api_key_ref" not in result
