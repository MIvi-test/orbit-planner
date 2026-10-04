"""Explain plan losses on the active input, next to the scenario comparisons."""
from __future__ import annotations

from decimal import Decimal
from collections import defaultdict
from dataclasses import replace
from itertools import permutations
from typing import Any

from app import db, planner


class QualityUnavailable(ValueError):
    pass


def evaluate(run_id: int) -> dict[str, Any]:
    run = db.query_one(
        "SELECT run_id, pi_id, as_of_sprint, created_at, params FROM plan_runs "
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
    comparison = compare_modes(int(run["as_of_sprint"]), run["params"] or {})
    return {
        "run_id": run_id,
        "completed_value": {"tasks": completed["tasks"], "sp": str(completed["sp"])},
        "partial_initiatives": partial,
        "dependency_wait": waiting,
        "deferred_commitments": {"tasks": deferred["tasks"], "sp": str(deferred["sp"])},
        "unplanned_completed_sp": str(unplanned_sp or Decimal(0)),
        "scarce_unused_roles": scarce,
        "people_switches": switches,
        "mode_comparison": comparison,
        "method": (
            "Текущий вход; бизнес ценность — только подтверждённая цель. "
            "Дефицит и свободный фонд роли сопоставлены для оставшихся спринтов."
        ),
    }


def compare_modes(as_of_sprint: int, params: dict[str, Any]) -> dict[str, Any]:
    """Price of both published heuristics on the same current input.

    Complete initiative SP is a technical proxy, never labelled business value.
    The total live SP is a valid but loose upper bound; no optimality claim.
    """
    inputs = planner.load_inputs()
    groups: dict[str, list[Any]] = defaultdict(list)
    for task in inputs.tasks:
        groups[task.prodf_id].append(task)
    modes: dict[str, dict[str, Any]] = {}
    for mode in (planner.INITIATIVE_MODE_GREEDY, planner.INITIATIVE_MODE_ATOMIC):
        plan = planner.build_plan(
            inputs, as_of_sprint=as_of_sprint, initiative_mode=mode,
            dependency_mode=str(params.get("dependency_mode", planner.DEFAULT_DEPENDENCY_MODE)),
            priority_strategy=str(params.get("priority_strategy", planner.DEFAULT_PRIORITY_STRATEGY)),
            simulate_next_pi=False,
        )
        placed = {row.task_id for row in plan.in_quarter}
        complete = [prodf_id for prodf_id, tasks in groups.items()
                    if all(task.task_id in placed for task in tasks)]
        partial = [prodf_id for prodf_id, tasks in groups.items()
                   if any(task.task_id in placed for task in tasks) and prodf_id not in complete]
        complete_sp = sum((task.sp_to_plan for prodf_id in complete
                           for task in groups[prodf_id]), Decimal(0))
        modes[mode] = {
            "complete_initiatives": len(complete),
            "complete_initiative_sp": str(complete_sp),
            "partial_initiatives": len(partial),
            "planned_tasks": len(placed),
        }
    upper = sum((task.sp_to_plan for task in inputs.tasks), Decimal(0))
    order_search = reference_order_search(inputs, as_of_sprint, params)
    return {"modes": modes, "upper_bound_sp": str(upper), "order_search": order_search,
            "method": "Один текущий вход и правила ограничений; SP завершённых инициатив — техническая мера. "
                      "Верхняя граница — все живые SP, оптимум не доказан."}


def reference_order_search(inputs: planner.Inputs, as_of_sprint: int,
                           params: dict[str, Any]) -> dict[str, Any]:
    """Exhaust all initiative orders on small inputs, keeping every feasibility rule.

    The result is exact among these orders and this placement algorithm; it is
    not a proof of optimality over arbitrary schedules.
    """
    groups: dict[str, list[Any]] = defaultdict(list)
    for task in inputs.tasks:
        groups[task.prodf_id].append(task)
    if len(groups) > 5 or len(inputs.tasks) > 10:
        return {"status": "skipped", "reason": "перебор ограничен 5 инициативами и 10 задачами"}
    best: dict[str, dict[str, Any]] = {}
    for order in permutations(sorted(groups)):
        rank = {prodf_id: len(order) - index for index, prodf_id in enumerate(order)}
        ordered_input = replace(inputs, tasks=tuple(
            replace(task, business_priority=rank[task.prodf_id]) for task in inputs.tasks
        ))
        for mode in (planner.INITIATIVE_MODE_GREEDY, planner.INITIATIVE_MODE_ATOMIC):
            plan = planner.build_plan(
                ordered_input, as_of_sprint=as_of_sprint, initiative_mode=mode,
                dependency_mode=str(params.get("dependency_mode", planner.DEFAULT_DEPENDENCY_MODE)),
                priority_strategy=str(params.get("priority_strategy", planner.DEFAULT_PRIORITY_STRATEGY)),
                simulate_next_pi=False,
            )
            placed = {row.task_id for row in plan.in_quarter}
            complete = [prodf_id for prodf_id, tasks in groups.items()
                        if all(task.task_id in placed for task in tasks)]
            score = sum((task.sp_to_plan for prodf_id in complete
                         for task in groups[prodf_id]), Decimal(0))
            if mode not in best or score > Decimal(best[mode]["complete_initiative_sp"]):
                best[mode] = {"complete_initiative_sp": str(score), "order": list(order)}
    return {"status": "computed", "permutations": len(list(permutations(groups))),
            "best_by_mode": best,
            "method": "Полный перебор порядка инициатив при том же алгоритме размещения; "
                      "другие расписания могут быть лучше."}
