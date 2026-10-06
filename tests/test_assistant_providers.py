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


def test_edit_without_key_ref_keeps_previous_reference():
    previous = {"auth_type": "bearer", "api_key_ref": "env:OLD_KEY", "auth_header_name": None,
                "limits": {"max_tokens": 900}, "min_role": "planner"}
    raw = {"name": "x", "auth_type": "bearer"}
    merged = providers._merge_previous(raw, previous)
    assert merged["api_key_ref"] == "env:OLD_KEY"
    assert merged["limits"] == {"max_tokens": 900} and merged["min_role"] == "planner"
    assert providers._merge_previous({**raw, "api_key_ref": "env:NEW"}, previous)["api_key_ref"] == "env:NEW"
    assert "api_key_ref" not in providers._merge_previous({"auth_type": "none"}, previous)
    header = {"auth_type": "header", "api_key_ref": "env:G", "auth_header_name": "x-goog-api-key"}
    merged = providers._merge_previous({"auth_type": "header", "api_key_ref": "env:H"}, header)
    assert merged["auth_header_name"] == "x-goog-api-key" and merged["api_key_ref"] == "env:H"


def test_profile_delete_is_admin_only():
    from app import auth
    assert auth.required_role("DELETE", "/api/assistant/profiles/3") == "admin"


@pytest.mark.parametrize("protocol, check", [
    ("openai_compatible", lambda b: b["enable_thinking"] is False),
    ("ollama", lambda b: b["think"] is False),
    ("gemini", lambda b: b["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}),
])
def test_thinking_off_is_sent_per_protocol(monkeypatch, protocol, check):
    bodies = []
    reply = ({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]} if protocol == "gemini"
             else {"message": {"content": "{}"}} if protocol == "ollama"
             else {"choices": [{"message": {"content": "{}"}}]})
    monkeypatch.setattr(providers, "_request", lambda _p, body, _t: bodies.append(body) or reply)
    p = profile() | {"protocol": protocol, "capabilities": {"thinking": False}}
    providers.generate(p, [{"role": "user", "content": "q"}], "system")
    assert check(bodies[0])


def test_thinking_flag_is_omitted_by_default(monkeypatch):
    bodies = []
    monkeypatch.setattr(providers, "_request", lambda _p, body, _t: bodies.append(body) or
                        {"choices": [{"message": {"content": "{}"}}]})
    providers.generate(profile(), [{"role": "user", "content": "q"}], "system")
    assert "enable_thinking" not in bodies[0]


def test_gemini_3_uses_minimal_thinking_and_json_schema(monkeypatch):
    bodies = []
    monkeypatch.setattr(providers, "_request", lambda _p, body, _t: bodies.append(body) or
                        {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
    p = profile("gemini", model="gemini-3.5-flash-lite", capabilities={"thinking": False})
    p["capabilities"]["structured_output_verified"] = True
    schema = {"type": "object", "additionalProperties": False}
    providers.generate(p, [{"role": "user", "content": "q"}], "system", schema)
    assert bodies[0]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert bodies[0]["generationConfig"]["responseJsonSchema"] == schema


@pytest.mark.parametrize("protocol,base_url,model,expected_field", [
    ("gemini", "https://generativelanguage.googleapis.com/v1beta", "gemini-3.5-flash-lite", "responseJsonSchema"),
    ("openai_compatible", "https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "response_format"),
])
def test_known_cloud_model_requests_schema_before_manual_check(monkeypatch, protocol, base_url, model, expected_field):
    bodies = []
    reply = ({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]} if protocol == "gemini"
             else {"choices": [{"message": {"content": "{}"}}]})
    monkeypatch.setattr(providers, "_request", lambda _p, body, _t: bodies.append(body) or reply)
    p = profile(protocol, base_url=base_url, model=model)
    schema = {"type": "object", "additionalProperties": False}
    providers.generate(p, [{"role": "user", "content": "q"}], "system", schema)
    assert expected_field in (bodies[0]["generationConfig"] if protocol == "gemini" else bodies[0])


def test_edit_keeps_admin_capabilities_but_not_observed_ones():
    previous = {"auth_type": "none", "api_key_ref": None, "auth_header_name": None,
                "capabilities": {"thinking": False, "structured_output_verified": True}}
    assert providers._merge_previous({"auth_type": "none"}, previous)["capabilities"] == {"thinking": False}
