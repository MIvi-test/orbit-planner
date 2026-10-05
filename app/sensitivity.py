"""Deterministic sensitivity scenarios on the active plan; no probabilities."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from app import db, planner
from app.assistant import snapshots

FACTOR = Decimal("0.80")
ETC_FACTOR = Decimal("1.20")


class ScenarioUnavailable(ValueError):
    pass


def _changed_inputs(inputs: planner.Inputs, kind: str) -> planner.Inputs:
    if kind == "availability_80":
        return replace(inputs, engineers=tuple(
            replace(e, total_capacity_rate=e.total_capacity_rate * FACTOR,
                    orbits={team: rate * FACTOR for team, rate in e.orbits.items()})
            for e in inputs.engineers
        ))
    if kind == "etc_120":
        return replace(inputs, tasks=tuple(
            replace(t, remaining={role: hours * ETC_FACTOR for role, hours in t.remaining.items()})
            for t in inputs.tasks
        ))
    if kind == "velocity_80":
        return replace(inputs, team_sp_per_sprint={
            team: sp * FACTOR for team, sp in inputs.team_sp_per_sprint.items()
        })
    raise ValueError(kind)


def evaluate(run_id: int) -> dict[str, Any]:
    active = db.query_one(
        "SELECT run_id, as_of_sprint, params FROM plan_runs "
        "WHERE status IN ('ok', 'infeasible') ORDER BY run_id DESC LIMIT 1"
    )
    if active is None or int(active["run_id"]) != run_id:
        raise ScenarioUnavailable("Сценарии доступны только для текущего прогона")
    try:
        inputs, baseline, baseline_starts, options = snapshots.replay(snapshots.for_current_run(run_id))
    except snapshots.SnapshotUnavailable as exc:
        raise ScenarioUnavailable(str(exc)) from exc
    build_options = {**options, "baseline_starts": baseline_starts}
    base = {row.task_id: row for row in baseline.schedule}
    scenarios = []
    for kind, label in (
        ("availability_80", "Доступность инженеров −20%"),
        ("etc_120", "Остаток часов по ролям +20%"),
        ("velocity_80", "Скорость команд −20%"),
    ):
        changed = planner.build_plan(_changed_inputs(inputs, kind), **build_options)
        delayed = []
        for row in changed.schedule:
            old = base.get(row.task_id)
            if old is None or old.decision != "in_quarter":
                continue
            old_end = old.end_sprint
            new_end = row.end_sprint if row.decision == "in_quarter" else None
            if old_end is not None and (new_end is None or new_end > old_end):
                delayed.append({
                    "task_id": row.task_id, "previous_end_sprint": old_end,
                    "scenario_end_sprint": new_end, "decision": row.decision,
                })
        scenarios.append({
            "kind": kind, "label": label,
            "in_quarter": len(changed.in_quarter),
            "deferred": len(changed.deferred),
            "delayed_tasks": delayed,
        })
    latest = db.scalar(
        "SELECT MAX(run_id) FROM plan_runs WHERE status IN ('ok', 'infeasible')"
    )
    if latest != run_id:
        raise ScenarioUnavailable("План обновился во время расчёта; откройте текущий прогон")
    return {
        "run_id": run_id,
        "method": "Три детерминированных сценария на одинаковом текущем входе. Вероятности не оцениваются.",
        "baseline": {"in_quarter": len(baseline.in_quarter), "deferred": len(baseline.deferred)},
        "scenarios": scenarios,
    }
