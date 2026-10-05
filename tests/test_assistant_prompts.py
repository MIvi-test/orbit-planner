from app import auth
from app.assistant import prompts


def test_prompt_layers_and_versions(monkeypatch):
    seen = []

    def fake_get(scope, principal=None):
        seen.append((scope, principal.owner_key if principal else None))
        return {"prompt_id": 11 if scope == "default" else 22,
                "version": 3 if scope == "default" else 2,
                "content": "Общие правила" if scope == "default" else "Мой стиль"}

    monkeypatch.setattr(prompts, "get", fake_get)
    principal = auth.Principal("Лена", "viewer", "db", 8)
    bundle = prompts.assemble(principal, "Объясни метрику")
    assert seen == [("default", None), ("user", "db:8")]
    assert (bundle.default_id, bundle.personal_id, bundle.default_version,
            bundle.personal_version) == (11, 22, 3, 2)
    assert bundle.system.index("Общие правила") < bundle.system.index("Мой стиль")
    assert "роль=viewer" in bundle.system


def test_prompt_content_limit():
    for content in ("", "  ", "x" * 12001):
        try:
            prompts._validate(content)
        except prompts.PromptError:
            pass
        else:
            raise AssertionError("invalid prompt accepted")
