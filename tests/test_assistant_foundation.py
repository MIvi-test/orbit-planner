"""The assistant must not inherit the legacy admin-only default for writes."""
from __future__ import annotations

import pytest

from app import auth


@pytest.mark.parametrize(("method", "path", "role"), [
    ("POST", "/api/assistant/conversations", "viewer"),
    ("POST", "/api/assistant/conversations/c/messages", "viewer"),
    ("PUT", "/api/assistant/conversations/c/settings", "viewer"),
    ("PUT", "/api/assistant/prompts/me", "viewer"),
    ("PUT", "/api/assistant/prompts/default", "admin"),
    ("POST", "/api/assistant/profiles/1/check", "admin"),
    ("POST", "/api/assistant/conversations/c/scenarios/compare", "planner"),
    ("POST", "/api/assistant/kb/reindex", "admin"),
    ("POST", "/api/assistant/unrecognized", "admin"),
])
def test_assistant_write_roles(method: str, path: str, role: str) -> None:
    assert auth.required_role(method, path) == role


def test_owner_key_uses_stable_id_and_separate_service_namespaces() -> None:
    before = auth.Principal("renamed-user", "viewer", "db", user_id=7)
    after = auth.Principal("same-user", "planner", "db", user_id=7)
    assert before.owner_key == after.owner_key == "db:7"
    assert auth.Principal("same-user", "admin", "env").owner_key != after.owner_key
    with pytest.raises(ValueError):
        _ = auth.Principal("missing-id", "viewer", "db").owner_key
