from app import absence, planner
from tests.test_planner import engineer, inputs, task


def test_absence_replans_when_same_role_colleague_is_fully_occupied(monkeypatch) -> None:
    source = inputs(
        [task("A", roles={1: 80}, topo=1), task("B", roles={1: 80}, topo=2)],
        [engineer("E-1"), engineer("E-2")],
    )
    original = planner.build_plan(source)
    old = [
        {"task_id": row.task_id, "decision": row.decision,
         "start_sprint": row.start_sprint, "end_sprint": row.end_sprint,
         "prodf_id": f"PRODF-{row.task_id}"}
        for row in original.schedule
    ]
    monkeypatch.setattr(absence.planner, "load_inputs", lambda: source)
    monkeypatch.setattr(absence.planner, "load_baseline_starts", lambda: {})
    monkeypatch.setattr(absence.db, "query_one", lambda sql: (
        {"run_id": 1, "as_of_sprint": 0, "params": {}}
        if "as_of_sprint" in sql else {"run_id": 1}
    ))
    monkeypatch.setattr(absence.db, "query_dicts", lambda _sql, _params: old)

    result = absence.evaluate("E-1", 1)

    assert len(result["affected_tasks"]) == 1
    assert result["affected_tasks"][0]["task_id"] == "B"
    assert result["affected_tasks"][0]["delay_sprints"] == 1
    assert result["lost_initiatives"] == []
