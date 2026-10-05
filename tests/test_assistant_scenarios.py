"""Staffing package accounting on the planner's own input model."""
from decimal import Decimal
from uuid import uuid4

import pytest

from app import planner
from app.assistant import scenarios
from test_planner import T1, T2, engineer, inputs, task


def test_package_recalculates_once_and_preserves_source(monkeypatch):
    original = inputs([task("A", roles={1: 250})], [engineer("E1", rate="0.50")],
                      team_sp={T1: 100, T2: 100})
    baseline = planner.build_plan(original, simulate_next_pi=False)
    sid = uuid4()
    monkeypatch.setattr(scenarios.snapshots, "replay", lambda _sid: (
        original, baseline, {}, {"as_of_sprint": 0, "dependency_mode": "finish_start",
                                 "initiative_mode": "greedy", "priority_strategy": "max",
                                 "simulate_next_pi": False}))
    calls = []
    real_build = planner.build_plan

    def build(*args, **kwargs):
        calls.append(1)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(scenarios.planner, "build_plan", build)
    result = scenarios.evaluate(sid, [{"measures": [
        {"kind": "hire", "role_id": 1, "team_id": T1, "rate": 0.5,
         "start_sprint": 1, "hiring_lag_sprints": 1, "skill_ids": []},
        {"kind": "hire", "role_id": 1, "team_id": T1, "rate": 0.5,
         "start_sprint": 1, "hiring_lag_sprints": 1, "skill_ids": []},
    ]}])
    assert len(calls) == 1
    assert result["alternatives"][0]["verified_by_scenario"] is True
    assert original.engineers == (engineer("E1", rate="0.50"),)
    repeated = scenarios.evaluate(sid, [{"measures": [
        {"kind": "hire", "role_id": 1, "team_id": T1, "rate": 0.5,
         "start_sprint": 1, "hiring_lag_sprints": 1, "skill_ids": []},
        {"kind": "hire", "role_id": 1, "team_id": T1, "rate": 0.5,
         "start_sprint": 1, "hiring_lag_sprints": 1, "skill_ids": []},
    ]}])
    assert len(calls) == 1
    assert repeated == result and repeated is not result


def test_loan_keeps_total_rate_and_rejects_duplicate_allocation():
    original = inputs([task("A", team=T2, roles={1: 40})],
                      [engineer("E1", rate="0.50", orbits=(T1,))],
                      team_sp={T1: 100, T2: 100})
    moved, _ = scenarios._apply(original, {"kind": "loan", "engineer_id": "E1",
                                       "team_id": T2, "rate": 0.5, "start_sprint": 1}, 1, 0)
    assert moved.sprint_orbit_rates["E1", T1, 1] == Decimal(0)
    assert moved.sprint_orbit_rates["E1", T2, 1] == Decimal("0.5")
    with pytest.raises(scenarios.ScenarioError, match="insufficient_worker_capacity"):
        scenarios._apply(moved, {"kind": "loan", "engineer_id": "E1",
                                 "team_id": T2, "rate": 0.5, "start_sprint": 1}, 2, 0)


def test_training_loses_trainee_and_mentor_capacity_before_effective():
    original = inputs([task("A", roles={1: 40})],
                      [engineer("T", role_id=2), engineer("M", role_id=1)],
                      team_sp={T1: 100})
    changed, note = scenarios._apply(original, {
        "kind": "train", "trainee_id": "T", "mentor_id": "M", "role_id": 1,
        "team_id": T1, "rate": 0.5, "start_sprint": 1,
        "training_sprints": 1, "mentor_rate": 0.1, "skill_ids": []}, 1, 0)
    virtual = "assistant-trained-1-T"
    assert changed.sprint_orbit_rates["T", T1, 1] == Decimal("0.5")
    assert changed.sprint_orbit_rates["M", T1, 1] == Decimal("0.9")
    assert changed.sprint_orbit_rates[virtual, T1, 1] == 0
    assert note["effective_sprint"] == 2
