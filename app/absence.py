"""Read-only absence scenario for the current published plan."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from app import db, planner


class ScenarioUnavailable(ValueError):
    pass


def evaluate(engineer_id: str, run_id: int) -> dict[str, Any]:
    active = db.query_one(
        """SELECT run_id, as_of_sprint, params FROM plan_runs
           WHERE status IN ('ok', 'infeasible') ORDER BY run_id DESC LIMIT 1"""
    )
    if active is None or int(active["run_id"]) != run_id:
        raise ScenarioUnavailable("Сценарий доступен только для текущего опубликованного прогона")

    inputs = planner.load_inputs()
    if engineer_id not in {row.engineer_id for row in inputs.engineers}:
        raise ValueError(f"инженер {engineer_id} не найден")
    modes = active["params"] or {}
    scenario_inputs = replace(
        inputs,
        engineers=tuple(row for row in inputs.engineers if row.engineer_id != engineer_id),
        coverage={key: value for key, value in inputs.coverage.items() if key[0] != engineer_id},
        engineer_skills={key: value for key, value in inputs.engineer_skills.items()
                         if key != engineer_id},
    )
    proposed = planner.build_plan(
        scenario_inputs,
        as_of_sprint=int(active["as_of_sprint"]),
        baseline_starts=planner.load_baseline_starts(),
        dependency_mode=modes.get("dependency_mode", planner.DEFAULT_DEPENDENCY_MODE),
        initiative_mode=modes.get("initiative_mode", planner.INITIATIVE_MODE_GREEDY),
        priority_strategy=modes.get("priority_strategy", planner.DEFAULT_PRIORITY_STRATEGY),
        simulate_next_pi=False,
    )
    previous = db.query_dicts(
        """SELECT s.task_id, s.decision, s.start_sprint, s.end_sprint, t.prodf_id
           FROM plan_task_schedule s JOIN tasks t USING (task_id)
           WHERE s.run_id = %s ORDER BY s.task_id""",
        [run_id],
    )
    latest = db.query_one(
        """SELECT MAX(run_id) AS run_id FROM plan_runs
           WHERE status IN ('ok', 'infeasible')"""
    )
    if latest is None or int(latest["run_id"]) != run_id:
        raise ScenarioUnavailable("План обновился во время расчёта сценария; откройте текущий прогон")

    new = {row.task_id: row for row in proposed.schedule}
    affected = []
    for old in previous:
        row = new.get(old["task_id"])
        if row is None:
            continue
        new_end = row.end_sprint if row.decision == "in_quarter" else None
        old_end = old["end_sprint"] if old["decision"] == "in_quarter" else None
        if old_end is None or (new_end is not None and new_end <= old_end):
            continue
        affected.append({
            "task_id": old["task_id"],
            "prodf_id": old["prodf_id"],
            "previous_end_sprint": old_end,
            "scenario_end_sprint": new_end,
            "delay_sprints": new_end - old_end if new_end is not None else None,
            "decision": row.decision,
            "reason": row.reason_text,
        })
    affected_ids = {row["task_id"] for row in affected}
    chain = [
        {"blocking": blocking, "blocked": blocked}
        for blocking, blocked, _gap in inputs.deps
        if blocking in affected_ids and blocked in affected_ids
    ]
    old_in_quarter = {row["task_id"] for row in previous if row["decision"] == "in_quarter"}
    new_in_quarter = {row.task_id for row in proposed.schedule if row.decision == "in_quarter"}
    prodf_tasks: dict[str, set[str]] = {}
    for old in previous:
        prodf_tasks.setdefault(old["prodf_id"], set()).add(old["task_id"])
    lost = sorted(
        prodf_id for prodf_id, task_ids in prodf_tasks.items()
        if task_ids <= old_in_quarter and not task_ids <= new_in_quarter
    )
    by_id = {task.task_id: task for task in inputs.tasks}
    extra_deferred = sum(
        (by_id[task_id].demand_hh for task_id in old_in_quarter - new_in_quarter
         if task_id in by_id), Decimal(0)
    )
    return {
        "run_id": run_id,
        "engineer_id": engineer_id,
        "assumptions": "Инженер недоступен до конца PI; штат, задачи и правила текущего прогона сохранены. Новый план не публикуется.",
        "affected_tasks": affected,
        "affected_chain": chain,
        "lost_initiatives": lost,
        "extra_deferred_hh": str(extra_deferred),
        "scenario_reasons": proposed.params["reasons"],
    }
