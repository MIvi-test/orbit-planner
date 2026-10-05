"""Core chat boundaries without a live provider or database."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import auth
from app.assistant import conversations, memory, worker


def test_knowledge_chat_facts_need_no_dataset():
    assert "без прогона" in memory.facts(None, "Как работает система?")


def test_answer_shape_and_clarification():
    raw = {
        "status": "needs_clarification", "summary": "Уточните команду",
        "explanation": "Есть несколько вариантов", "clarification": "Какую команду вы имеете в виду?",
    }
    answer = memory.parse_answer(json.dumps(raw), 3, False, uuid4(), ("team", "ALPHA"))
    assert answer["context_revision"] == 3
    assert answer["evidence_ids"] == []
    assert answer["entity_refs"] == [{"type": "team", "id": "ALPHA", "context_revision": 3}]
    assert answer["clarification"]
    with pytest.raises(ValueError, match="missing_clarification"):
        memory.parse_answer(json.dumps({**raw, "clarification": ""}), 3, False, None)


def test_history_keeps_last_question_and_current_revision(monkeypatch):
    latest = uuid4()
    older = uuid4()
    seen = {}

    def fake_query(sql, params):
        seen["params"] = params
        return [{"message_id": latest, "role": "user", "content": "эта команда?"},
                {"message_id": older, "role": "assistant", "content": "Команда Альфа"}]

    monkeypatch.setattr(memory.db, "query_dicts", fake_query)
    cid = uuid4()
    assert memory.history(cid, 2, latest) == [
        {"role": "assistant", "content": "Команда Альфа"},
        {"role": "user", "content": "эта команда?"},
    ]
    assert seen["params"] == (cid, 2)


def test_followup_resolves_saved_team_only_in_same_revision(monkeypatch):
    monkeypatch.setattr(memory.snapshots, "load", lambda _sid: (
        SimpleNamespace(team_sp_per_sprint={"ALPHA": 10}, tasks=[]), None, None, None))
    seen = {}

    def fake_query(_sql, params):
        seen["revision"] = params[1]
        return {"payload": {"entity_refs": [{"type": "team", "id": "ALPHA"}]}}

    monkeypatch.setattr(memory.db, "query_one", fake_query)
    cid, sid = uuid4(), uuid4()
    assert memory.focus(cid, 4, sid, "Что с этой командой?") == ("team", "ALPHA")
    assert seen["revision"] == 4
    assert memory.focus(cid, 5, sid, "Сравни ALPHA") == ("team", "ALPHA")


def test_worker_rechecks_user_role(monkeypatch):
    monkeypatch.setattr(worker.db, "query_one", lambda *_: {
        "user_id": 7, "name": "Пользователь", "role": "viewer"})
    principal = worker._current_principal({
        "owner_key": "db:7", "input_payload": {"principal": {
            "source": "db", "user_id": 7, "role": "admin", "name": "старое имя"}},
    })
    assert principal == auth.Principal("Пользователь", "viewer", "db", 7)
    monkeypatch.setattr(worker.db, "query_one", lambda *_: None)
    with pytest.raises(conversations.ChatError, match="user_no_longer_active"):
        worker._current_principal({"owner_key": "db:7", "input_payload": {
            "principal": {"source": "db", "user_id": 7}}})
