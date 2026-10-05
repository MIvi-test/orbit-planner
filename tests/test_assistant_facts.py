"""Snapshot facts retain full selections and explicit provenance."""
from decimal import Decimal
from types import SimpleNamespace as Row
from uuid import uuid4

from app.assistant import evidence, facts, retrieval
from app import auth
from app.assistant.conversations import ChatError
import pytest


def test_team_and_metric_use_complete_snapshot(monkeypatch):
    tasks = tuple(Row(task_id=f"T{i}", team_id="A", summary=f"Task {i}", prodf_id="P",
                      demand_hh=Decimal("2"), sp_to_plan=Decimal("1"), status="Open")
                  for i in range(70))
    plan = Row(pi_id="PI", as_of_sprint=0, status="built",
               params={"algorithm": "a", "formula_version": "f"}, actuals_upload_id=None,
               schedule=tuple(Row(task_id=f"T{i}", decision="in_quarter") for i in range(70)),
               states=(), assignments=(), alerts=(), team_capacity=(), role_demands=(),
               kpis=(Row(kpi_code="KPI", sprint_no=1, kind="forecast", value=Decimal("3")),),
               baseline=())
    inputs = Row(tasks=tasks, team_sp_per_sprint={"A": Decimal("5")}, sprint_count=6,
                 last_reported_sprint=0, fund_hours_per_fte=Decimal("480"))
    monkeypatch.setattr(facts.snapshots, "load", lambda _sid: (inputs, plan, {}, {}))
    sid = uuid4()
    team = facts.get_team(sid, "A")
    assert team["complete_selection"] and len(team["tasks"]) == 70
    assert len(team["schedule"]) == 70
    metric = facts.get_metric(sid, "kpi")
    assert metric["rows"][0]["value"] == "3"
    records, context = evidence.prepare(sid, "Почему KPI 3?", None,
                                        retrieval.SearchResult(None, (), "kb_not_indexed"), "")
    assert records[0]["payload"]["rows"][0]["value"] == "3"
    assert f"[evidence:{records[0]['evidence_id']}]" in context


def test_compare_runs_marks_observation_not_cause(monkeypatch):
    before_id, after_id = uuid4(), uuid4()

    def load(sid):
        end = 1 if sid == before_id else 2
        inputs = Row(source_sha256="source")
        plan = Row(pi_id="PI", as_of_sprint=0, params={"algorithm": "a", "formula_version": "f"},
                   actuals_upload_id=None, schedule=(Row(task_id="T", end_sprint=end),), kpis=())
        return inputs, plan, {}, {}

    monkeypatch.setattr(facts.snapshots, "load", load)
    result = facts.compare_runs(before_id, after_id)
    assert result["shared_tasks"] == 1 and len(result["changed_tasks"]) == 1
    assert "причины" in result["interpretation"]


def test_evidence_read_is_scoped_to_owner(monkeypatch):
    seen = {}

    def query(_sql, params):
        seen["params"] = params
        return None

    monkeypatch.setattr(evidence.db, "query_one", query)
    eid = uuid4()
    with pytest.raises(ChatError, match="evidence_not_found"):
        evidence.get(auth.Principal("user", "viewer", "db", 17), str(eid))
    assert seen["params"] == (eid, "db:17")


def test_unverified_citation_is_rejected():
    with pytest.raises(ValueError, match="unverified_evidence_reference"):
        evidence.check_citations({"summary": "[evidence:made-up]", "explanation": ""}, [])


def test_numeric_claim_is_rendered_from_saved_evidence():
    eid = uuid4()
    answer = {"summary": "Команда испытывает дефицит.", "explanation": "Есть незавершённые задачи.",
              "fact_refs": [{"evidence_id": str(eid), "field": "task_count"}]}
    records = [{"evidence_id": eid, "source_type": "snapshot", "payload": {"task_count": 17}}]
    evidence.render_fact_refs(answer, records)
    assert f"task_count = 17 [evidence:{eid}]" in answer["explanation"]
    answer["summary"] = "Команда имеет 99 задач."
    with pytest.raises(ValueError, match="untyped_numeric_claim"):
        evidence.render_fact_refs(answer, records)
