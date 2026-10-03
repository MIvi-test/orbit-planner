"""Explain plan losses on the active input, next to the scenario comparisons."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app import db


class QualityUnavailable(ValueError):
    pass


def evaluate(run_id: int) -> dict[str, Any]:
    run = db.query_one(
        "SELECT run_id, pi_id, as_of_sprint, created_at FROM plan_runs "
        "WHERE status IN ('ok', 'infeasible') ORDER BY run_id DESC LIMIT 1"
    )
    if run is None or run["run_id"] != run_id:
        raise QualityUnavailable("Аналитика потерь доступна для текущего прогона")
    baseline_id = db.scalar(
        "SELECT MIN(run_id) FROM plan_runs WHERE pi_id = %s AND as_of_sprint = 0",
        (run["pi_id"],),
    )
    if baseline_id is None:
        raise QualityUnavailable("Для анализа обещаний нужен базовый план")
    completed = db.query_one(
        """SELECT COUNT(*) AS tasks, COALESCE(SUM(t.estimation_sp), 0) AS sp
           FROM v_plan_goal_outcome g JOIN tasks t USING (task_id)
           WHERE g.run_id = %s AND g.confirmation_state = 'confirmed_achieved'
             AND g.target_goal_rank IS NOT NULL
             AND g.confirmed_goal_rank >= g.target_goal_rank""", (run_id,),
    )
    partial = db.query_dicts(
        """SELECT t.prodf_id, COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE s.decision = 'in_quarter') AS planned
           FROM tasks t LEFT JOIN plan_task_schedule s
             ON s.task_id = t.task_id AND s.run_id = %s
           GROUP BY t.prodf_id
           HAVING COUNT(*) FILTER (WHERE s.decision = 'in_quarter') BETWEEN 1 AND COUNT(*) - 1
           ORDER BY t.prodf_id""", (run_id,),
    )
    waiting = db.query_one(
        """SELECT COUNT(*) AS tasks,
                  COALESCE(SUM(GREATEST(b.earliest_start_sprint - 1, 0)), 0) AS earliest_wait_sprints
           FROM plan_dependency_bounds b JOIN plan_task_schedule s
             ON s.run_id = b.run_id AND s.task_id = b.task_id
           WHERE b.run_id = %s AND s.decision = 'in_quarter'
             AND b.earliest_start_sprint > 1""", (run_id,),
    )
    deferred = db.query_one(
        """SELECT COUNT(*) AS tasks, COALESCE(SUM(b.planned_sp), 0) AS sp
           FROM plan_baseline b LEFT JOIN plan_task_schedule s
             ON s.run_id = %s AND s.task_id = b.task_id
           WHERE b.run_id = %s AND b.committed
             AND COALESCE(s.decision, 'deferred_next_pi') <> 'in_quarter'""",
        (run_id, baseline_id),
    )
    unplanned_sp = db.scalar(
        """SELECT COALESCE(SUM(a.completed_sp), 0)
           FROM task_actuals a JOIN actual_uploads u ON u.upload_id = a.upload_id
           LEFT JOIN plan_baseline b ON b.run_id = %s AND b.task_id = a.task_id
           WHERE u.pi_id = %s AND u.coverage_status = 'complete'
             AND u.sprint_no < %s AND u.uploaded_at <= %s
             AND NOT COALESCE(b.committed, false)""",
        (baseline_id, run["pi_id"], run["as_of_sprint"], run["created_at"]),
    )
    scarce = db.query_dicts(
        """WITH demand AS (
             SELECT role_id, SUM(needed_hours) AS hours
             FROM plan_role_demand_snapshot WHERE run_id = %s GROUP BY role_id
           ), supply AS (
             SELECT role_id, SUM(hh_remaining_pi) AS hours
             FROM v_role_supply_hh GROUP BY role_id
           ), assigned AS (
             SELECT role_id, SUM(hours) AS hours
             FROM plan_assignments WHERE run_id = %s GROUP BY role_id
           )
           SELECT r.canonical_name AS role, demand.hours AS demand_hh,
                  COALESCE(supply.hours, 0) AS supply_hh,
                  GREATEST(COALESCE(supply.hours, 0) - COALESCE(assigned.hours, 0), 0) AS unused_hh
           FROM demand JOIN roles r USING (role_id)
           LEFT JOIN supply USING (role_id) LEFT JOIN assigned USING (role_id)
           WHERE demand.hours > COALESCE(supply.hours, 0)
             AND COALESCE(supply.hours, 0) > COALESCE(assigned.hours, 0)
           ORDER BY unused_hh DESC""", (run_id, run_id),
    )
    previous_id = db.scalar(
        "SELECT MAX(run_id) FROM plan_runs WHERE pi_id = %s AND run_id < %s "
        "AND status IN ('ok', 'infeasible')", (run["pi_id"], run_id),
    )
    switches: list[dict[str, Any]] = []
    if previous_id is not None:
        rows = db.query_dicts(
            "SELECT run_id, task_id, role_id, engineer_id FROM plan_assignments "
            "WHERE run_id IN (%s, %s)", (previous_id, run_id),
        )
        groups: dict[tuple[int, str, int], set[str]] = {}
        for row in rows:
            key = (row["run_id"], row["task_id"], row["role_id"])
            groups.setdefault(key, set()).add(row["engineer_id"])
        for (old_run, task_id, role_id), people in groups.items():
            if old_run != previous_id:
                continue
            new_people = groups.get((run_id, task_id, role_id))
            if new_people is not None and new_people != people:
                switches.append({"task_id": task_id, "role_id": role_id,
                                 "before": sorted(people), "after": sorted(new_people)})
    return {
        "run_id": run_id,
        "completed_value": {"tasks": completed["tasks"], "sp": str(completed["sp"])},
        "partial_initiatives": partial,
        "dependency_wait": waiting,
        "deferred_commitments": {"tasks": deferred["tasks"], "sp": str(deferred["sp"])},
        "unplanned_completed_sp": str(unplanned_sp or Decimal(0)),
        "scarce_unused_roles": scarce,
        "people_switches": switches,
        "method": (
            "Текущий вход; бизнес ценность — только подтверждённая цель. "
            "Дефицит и свободный фонд роли сопоставлены для оставшихся спринтов."
        ),
    }
