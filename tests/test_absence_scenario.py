from app import absence, planner
from tests.test_planner import engineer, inputs, task


def test_absence_replans_when_same_role_colleague_is_fully_occupied(monkeypatch) -> None:
    source = inputs(
        [task("A", roles={1: 80}, topo=1), task("B", roles={1: 80}, topo=2)],
        [engineer("E-1"), engineer("E-2")],
    )
    original = planner.build_plan(source)
    options = {
        "as_of_sprint": 0,
        "dependency_mode": planner.DEFAULT_DEPENDENCY_MODE,
        "initiative_mode": planner.INITIATIVE_MODE_GREEDY,
        "priority_strategy": planner.DEFAULT_PRIORITY_STRATEGY,
        "simulate_next_pi": True,
    }
    monkeypatch.setattr(absence.snapshots, "for_current_run", lambda _run_id: "snapshot-1")
    monkeypatch.setattr(absence.snapshots, "replay", lambda _snapshot_id: (source, original, {}, options))
    monkeypatch.setattr(absence.db, "query_one", lambda sql: (
        {"run_id": 1, "as_of_sprint": 0, "params": {}}
        if "as_of_sprint" in sql else {"run_id": 1}
    ))
    result = absence.evaluate("E-1", 1)

    assert len(result["affected_tasks"]) == 1
    assert result["affected_tasks"][0]["task_id"] == "B"
    assert result["affected_tasks"][0]["delay_sprints"] == 1
    assert result["lost_initiatives"] == []
