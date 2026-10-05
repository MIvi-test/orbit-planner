"""Versioned provider profiles and bounded, secret-safe model calls."""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from app import auth, db

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 512 * 1024
MAX_CONCURRENT = 4
_HEADER = re.compile(r"^[A-Za-z0-9-]{1,80}$")
_ENV = re.compile(r"^env:[A-Za-z_][A-Za-z0-9_]*$")
_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT)


class ProfileError(ValueError):
    pass


class ProviderError(Exception):
    def __init__(self, code: str, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class Generation:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    structured_output: bool


def _endpoint(profile: dict[str, Any]) -> str:
    root = str(profile["base_url"]).rstrip("/")
    protocol = profile["protocol"]
    if protocol == "gemini":
        model = urllib.parse.quote(str(profile["model"]), safe="")
        return f"{root}/models/{model}:generateContent"
    return root + ("/api/chat" if protocol == "ollama" else "/chat/completions")


def validate(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProfileError("profile must be an object")
    allowed = {"name", "protocol", "base_url", "model", "auth_type", "auth_header_name",
               "api_key_ref", "network_scope", "capabilities", "limits", "min_role"}
    if set(raw) - allowed:
        raise ProfileError("unknown profile fields")
    profile = dict(raw)
    for key in ("name", "protocol", "base_url", "model", "auth_type", "network_scope"):
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            raise ProfileError(f"{key} is required")
        profile[key] = profile[key].strip()
    if len(profile["name"]) > 100 or len(profile["model"]) > 200:
        raise ProfileError("name or model is too long")
    if profile["protocol"] not in {"gemini", "ollama", "openai_compatible"}:
        raise ProfileError("unsupported protocol")
    if profile["auth_type"] not in {"bearer", "header", "none"}:
        raise ProfileError("unsupported auth_type")
    if profile["network_scope"] not in {"internal", "external"}:
        raise ProfileError("unsupported network_scope")
    parsed = urllib.parse.urlsplit(profile["base_url"])
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or len(profile["base_url"]) > 2048):
        raise ProfileError("base_url must be an HTTP(S) API root without credentials or query")
    if profile["network_scope"] == "external" and parsed.scheme != "https":
        raise ProfileError("external endpoint requires HTTPS")
    allowed_internal = {"localhost", "127.0.0.1", "::1"}
    allowed_internal.update(x.strip().lower() for x in
                            os.environ.get("PI_PLANNER_INTERNAL_LLM_HOSTS", "").split(",") if x.strip())
    if profile["network_scope"] == "internal" and parsed.hostname.lower() not in allowed_internal:
        raise ProfileError("internal host is not allowlisted")
    if profile["auth_type"] == "header":
        if not isinstance(profile.get("auth_header_name"), str) or not _HEADER.fullmatch(profile["auth_header_name"]):
            raise ProfileError("valid auth_header_name is required")
        if profile["auth_header_name"].lower() in {"host", "content-length", "content-type", "authorization"}:
            raise ProfileError("reserved auth header")
    else:
        profile["auth_header_name"] = None
    ref = profile.get("api_key_ref")
    if profile["auth_type"] != "none":
        if not isinstance(ref, str) or not (_ENV.fullmatch(ref) or (ref.startswith("file:/") and ".." not in Path(ref[5:]).parts)):
            raise ProfileError("api_key_ref must be env:NAME or file:/absolute/path")
    elif ref is not None:
        raise ProfileError("auth_type=none cannot have api_key_ref")
    profile["api_key_ref"] = ref
    for key in ("capabilities", "limits"):
        profile[key] = dict(profile.get(key, {})) if isinstance(profile.get(key, {}), dict) else profile.get(key)
        if not isinstance(profile[key], dict) or len(json.dumps(profile[key])) > 4096:
            raise ProfileError(f"{key} must be a small object")
    if set(profile["capabilities"]) - {"json_mode"} or any(
        not isinstance(value, bool) for value in profile["capabilities"].values()
    ):
        raise ProfileError("unsupported capabilities; runtime capabilities come from /check")
    profile["min_role"] = profile.get("min_role", "viewer")
    if profile["min_role"] not in auth.RANK:
        raise ProfileError("invalid min_role")
    return profile


def _secret(profile: dict[str, Any]) -> str | None:
    if profile["auth_type"] == "none":
        return None
    ref = profile["api_key_ref"]
    try:
        value = os.environ.get(ref[4:]) if ref.startswith("env:") else Path(ref[5:]).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProviderError("credential_unavailable") from exc
    if not value or not value.strip():
        raise ProviderError("credential_unavailable")
    return value.strip()


def public(profile: dict[str, Any]) -> dict[str, Any]:
    result = {key: profile[key] for key in ("profile_id", "name", "protocol", "base_url", "model",
              "auth_type", "network_scope", "version", "capabilities", "min_role")}
    try:
        result["credential_configured"] = bool(_secret(profile) or profile["auth_type"] == "none")
    except ProviderError:
        result["credential_configured"] = False
    return result


def list_profiles(principal: auth.Principal) -> list[dict[str, Any]]:
    rows = db.query_dicts("SELECT * FROM public.assistant_provider_profiles WHERE active ORDER BY name")
    return [public(row) for row in rows if principal.allows(row["min_role"])]


def get(profile_id: int, *, active_only: bool = True) -> dict[str, Any] | None:
    return db.query_one("SELECT * FROM public.assistant_provider_profiles WHERE profile_id = %s"
                        + (" AND active" if active_only else ""), (profile_id,))


_COLUMNS = ("name", "protocol", "base_url", "model", "auth_type", "auth_header_name", "api_key_ref",
            "network_scope", "capabilities", "limits", "min_role")


def save(raw: Any, profile_id: int | None = None) -> dict[str, Any] | None:
    p = validate(raw)
    values = tuple(Jsonb(p[key]) if key in {"capabilities", "limits"} else p[key] for key in _COLUMNS)
    with db.transaction(operation="assistant_profile_save") as cur:
        version = 1
        if profile_id is not None:
            cur.execute("SELECT name, version FROM public.assistant_provider_profiles "
                        "WHERE profile_id = %s AND active FOR UPDATE", (profile_id,))
            previous = cur.fetchone()
            if previous is None:
                return None
            if previous["name"] != p["name"]:
                raise ProfileError("profile name cannot change")
            version = previous["version"] + 1
            cur.execute("UPDATE public.assistant_provider_profiles SET active = FALSE WHERE profile_id = %s", (profile_id,))
        cur.execute("INSERT INTO public.assistant_provider_profiles (" + ",".join(_COLUMNS) + ", version) "
                    "VALUES (" + ",".join(["%s"] * len(_COLUMNS)) + ", %s) RETURNING *", values + (version,))
        return public(cur.fetchone())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _request(profile: dict[str, Any], body: dict[str, Any], timeout: float) -> dict[str, Any]:
    secret = _secret(profile)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if secret is not None:
        if profile["auth_type"] == "bearer":
            headers["Authorization"] = "Bearer " + secret
        else:
            headers[profile["auth_header_name"]] = secret
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if len(raw) > MAX_REQUEST_BYTES:
        raise ProviderError("request_too_large")
    request = urllib.request.Request(_endpoint(profile), raw, headers, method="POST")
    if not _semaphore.acquire(timeout=timeout):
        raise ProviderError("provider_busy", True)
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ProviderError("response_too_large")
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            raise ValueError("object expected")
        return parsed
    except urllib.error.HTTPError as exc:
        code = "authentication_failed" if exc.code in (401, 403) else "rate_limited" if exc.code == 429 else "provider_unavailable"
        raise ProviderError(code, exc.code in (429, 500, 502, 503, 504)) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise ProviderError("provider_unavailable", True) from exc
    except (ValueError, UnicodeError) as exc:
        raise ProviderError("invalid_provider_response") from exc
    finally:
        _semaphore.release()


def _request_with_retry(profile: dict[str, Any], body: dict[str, Any], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    for attempt in range(2):
        try:
            return _request(profile, body, max(0.1, deadline - time.monotonic()))
        except ProviderError as exc:
            if not exc.retryable or attempt or deadline - time.monotonic() < 0.5:
                raise
            time.sleep(0.2)
    raise AssertionError("unreachable")


def generate(profile: dict[str, Any], messages: list[dict[str, str]], system: str,
             output_schema: dict[str, Any] | None = None, *, privacy_mode: str = "configured",
             timeout: float = 30.0, max_output_tokens: int = 1024) -> Generation:
    """Single bounded call; callers validate generated JSON against output_schema."""
    if privacy_mode == "local_only" and profile["network_scope"] != "internal":
        raise ProfileError("local_only forbids external providers")
    if not 0 < timeout <= 120 or not 0 < max_output_tokens <= 8192:
        raise ProfileError("invalid generation limits")
    if not isinstance(messages, list) or any(
        not isinstance(m, dict) or m.get("role") not in {"user", "assistant"}
        or not isinstance(m.get("content"), str) for m in messages
    ):
        raise ProfileError("invalid messages")
    protocol = profile["protocol"]
    structured = bool(output_schema and profile.get("capabilities", {}).get("structured_output_verified"))
    if protocol == "gemini":
        body: dict[str, Any] = {"contents": [{"role": "model" if m["role"] == "assistant" else "user",
                             "parts": [{"text": m["content"]}]} for m in messages],
                                "systemInstruction": {"parts": [{"text": system}]},
                                "generationConfig": {"maxOutputTokens": max_output_tokens}}
        if structured:
            body["generationConfig"].update({"responseMimeType": "application/json", "responseSchema": output_schema})
    else:
        body = {"model": profile["model"], "messages": [{"role": "system", "content": system}, *messages],
                "stream": False}
        if protocol == "ollama":
            body["options"] = {"num_predict": max_output_tokens}
            if structured:
                body["format"] = output_schema
        else:
            body["max_tokens"] = max_output_tokens
            if structured:
                body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "schema": output_schema}}
    response = _request_with_retry(profile, body, timeout)
    try:
        if protocol == "gemini":
            content = "".join(part.get("text", "") for part in response["candidates"][0]["content"]["parts"])
            usage = response.get("usageMetadata", {})
            input_tokens, output_tokens = usage.get("promptTokenCount"), usage.get("candidatesTokenCount")
        elif protocol == "ollama":
            content = response["message"]["content"]
            input_tokens, output_tokens = response.get("prompt_eval_count"), response.get("eval_count")
        else:
            content = response["choices"][0]["message"]["content"]
            usage = response.get("usage", {})
            input_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if not isinstance(content, str) or not content:
            raise ValueError("empty content")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError("invalid_provider_response") from exc
    return Generation(content, str(response.get("model") or profile["model"]), input_tokens, output_tokens, structured)


def check(profile: dict[str, Any]) -> dict[str, Any]:
    """Probe ordinary generation, then verify schema output with a separate call."""
    try:
        generate(profile, [{"role": "user", "content": "Reply OK."}], "Connection check.", timeout=12, max_output_tokens=16)
    except ProviderError as exc:
        return {"reachable": False, "structured_output": False, "error": exc.code}
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    probe = dict(profile)
    probe["capabilities"] = {"structured_output_verified": True}
    try:
        reply = generate(probe, [{"role": "user", "content": 'Return {"ok":true}.'}],
                         "Return only JSON matching the schema.", schema, timeout=12, max_output_tokens=32)
        verified = json.loads(reply.text) == {"ok": True}
    except (ProviderError, ValueError):
        verified = False
    result: dict[str, Any] = {"reachable": True, "structured_output": verified}
    if profile["protocol"] == "ollama":
        try:
            request = urllib.request.Request(str(profile["base_url"]).rstrip("/") + "/api/tags")
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=5) as response:
                models = json.loads(response.read(MAX_RESPONSE_BYTES + 1))["models"]
            digest = next((item.get("digest") for item in models if item.get("name") == profile["model"]), None)
            if isinstance(digest, str) and digest:
                result["model_digest"] = digest
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            pass
    return result


def record_check(profile_id: int, result: dict[str, Any]) -> None:
    if not result["reachable"]:
        return
    observed = {"structured_output_verified": result["structured_output"]}
    if result.get("model_digest"):
        observed["model_digest"] = result["model_digest"]
    db.execute_write("UPDATE public.assistant_provider_profiles "
                     "SET capabilities = capabilities || %s::jsonb WHERE profile_id = %s AND active",
                     (Jsonb(observed), profile_id), operation="assistant_profile_check")
