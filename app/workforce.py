"""Compare explicit hiring, training and loan interventions on one plan input."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from app import db, planner

HALF = Decimal("0.50")
MENTOR_COST = Decimal("0.10")


class ScenarioUnavailable(ValueError):
    pass


def _plan(inputs: planner.Inputs, as_of: int, modes: dict) -> planner.Plan:
    return planner.build_plan(
        inputs, as_of_sprint=as_of,
        baseline_starts=planner.load_baseline_starts(),
        dependency_mode=modes.get("dependency_mode", planner.DEPENDENCY_MODE_START_START),
        initiative_mode=modes.get("initiative_mode", planner.INITIATIVE_MODE_GREEDY),
        simulate_next_pi=False,
    )


def _assumed_skills(inputs: planner.Inputs, role_id: int) -> frozenset[int]:
    return frozenset(skill for (task_id, role), skills in inputs.skill_requirements.items()
                     if role == role_id for skill in skills)


def _virtual_worker(inputs: planner.Inputs, role_id: int, team_id: str,
                    worker_id: str, effective: int) -> planner.Inputs:
    worker = planner.EngineerInput(worker_id, role_id, "Middle", HALF, {team_id: HALF})
    rates = dict(inputs.sprint_orbit_rates)
    for sprint in range(1, min(effective, inputs.sprint_count + 1)):
        rates[(worker_id, team_id, sprint)] = Decimal(0)
    return replace(
        inputs, engineers=(*inputs.engineers, worker),
        coverage={**inputs.coverage, (worker_id, role_id): Decimal(1)},
        engineer_skills={**inputs.engineer_skills,
                         worker_id: _assumed_skills(inputs, role_id)},
        sprint_orbit_rates=rates,
    )


def _take_half(inputs: planner.Inputs, worker: planner.EngineerInput,
               from_sprint: int, rates: dict[tuple[str, str, int], Decimal]) -> None:
    for sprint in range(from_sprint, inputs.sprint_count + 1):
        remaining = HALF
        for team_id, original in sorted(worker.orbits.items(), key=lambda row: -row[1]):
            current = rates.get((worker.engineer_id, team_id, sprint), original)
            taken = min(current, remaining)
            rates[(worker.engineer_id, team_id, sprint)] = current - taken
            remaining -= taken
            if remaining <= 0:
                break


def _loan(inputs: planner.Inputs, worker: planner.EngineerInput,
          target_team: str, start: int) -> planner.Inputs:
    rates = dict(inputs.sprint_orbit_rates)
    _take_half(inputs, worker, start, rates)
    for sprint in range(start, inputs.sprint_count + 1):
        rates[(worker.engineer_id, target_team, sprint)] = HALF
    people = tuple(replace(item, orbits={**item.orbits, target_team: Decimal(0)})
                   if item.engineer_id == worker.engineer_id else item
                   for item in inputs.engineers)
    return replace(inputs, engineers=people, sprint_orbit_rates=rates)


def _training(inputs: planner.Inputs, trainee: planner.EngineerInput,
              mentor: planner.EngineerInput, role_id: int, team_id: str,
              start: int) -> planner.Inputs:
    effective = start + 1
    worker_id = f"scenario-trained-{trainee.engineer_id}"
    changed = _virtual_worker(inputs, role_id, team_id, worker_id, effective)
    rates = dict(changed.sprint_orbit_rates)
    _take_half(inputs, trainee, effective, rates)
    mentor_rate = mentor.orbits[team_id]
    rates[(mentor.engineer_id, team_id, start)] = mentor_rate - MENTOR_COST
    return replace(changed, sprint_orbit_rates=rates)


def _outcome(base: planner.Plan, changed: planner.Plan, inputs: planner.Inputs,
             kind: str, label: str, effective: int, cost: str) -> dict[str, Any]:
    base_in = {row.task_id for row in base.in_quarter}
    changed_in = {row.task_id for row in changed.in_quarter}
    sp = {task.task_id: task.sp_to_plan for task in inputs.tasks}
    prodf: dict[str, set[str]] = {}
    for task in inputs.tasks:
        prodf.setdefault(task.prodf_id, set()).add(task.task_id)
    restored = sorted(prodf_id for prodf_id, tasks in prodf.items()
                      if tasks <= changed_in and not tasks <= base_in)
    gained_tasks = sorted(changed_in - base_in)
    lost_tasks = sorted(base_in - changed_in)
    base_end = {row.task_id: row.end_sprint for row in base.in_quarter}
    earlier = sum(max(0, base_end[row.task_id] - row.end_sprint)
                  for row in changed.in_quarter
                  if row.task_id in base_end and row.end_sprint is not None
                  and base_end[row.task_id] is not None)
    return {
        "kind": kind, "label": label, "effective_sprint": effective,
        "resource_cost": cost, "restored_initiatives": restored,
        "gained_tasks": gained_tasks, "lost_tasks": lost_tasks,
        "net_sp_gain": str(sum((sp.get(task_id, Decimal(0)) for task_id in gained_tasks), Decimal(0))
                           - sum((sp.get(task_id, Decimal(0)) for task_id in lost_tasks), Decimal(0))),
        "earlier_task_sprints": earlier,
        "in_quarter": len(changed_in),
    }


def evaluate(run_id: int, role_id: int, team_id: str, start_sprint: int) -> dict[str, Any]:
    active = db.query_one(
        "SELECT run_id, as_of_sprint, params FROM plan_runs "
        "WHERE status IN ('ok', 'infeasible') ORDER BY run_id DESC LIMIT 1"
    )
    if active is None or int(active["run_id"]) != run_id:
        raise ScenarioUnavailable("Сценарии доступны только для текущего прогона")
    inputs = planner.load_inputs()
    if not 1 <= start_sprint <= inputs.sprint_count or start_sprint < max(1, active["as_of_sprint"]):
        raise ValueError("спринт начала вне открытого PI")
    if team_id not in inputs.team_sp_per_sprint:
        raise ValueError(f"команда {team_id} не найдена")
    if not any((task.team_id == team_id and role_id in task.needed) for task in inputs.tasks):
        raise ValueError("для выбранной команды и роли нет живого спроса")
    base = _plan(inputs, int(active["as_of_sprint"]), active["params"] or {})
    results = []

    # One sprint is reserved for hiring; candidate is assumed to have all
    # explicitly confirmed skills of the target role, shown in the response.
    hire_start = start_sprint + 1
    hired = _virtual_worker(inputs, role_id, team_id, "scenario-hire", hire_start)
    results.append(_outcome(base, _plan(hired, int(active["as_of_sprint"]), active["params"] or {}),
                            inputs, "hire", "+0,5 ставки после найма", hire_start,
                            "0,5 ставки с даты выхода; лаг найма — один спринт"))

    mentors = [e for e in inputs.engineers if e.role_id == role_id
               and e.orbits.get(team_id, Decimal(0)) >= MENTOR_COST]
    if mentors and start_sprint < inputs.sprint_count:
        mentor = sorted(mentors, key=lambda e: (-e.orbits[team_id], e.engineer_id))[0]
        trainees = [e for e in inputs.engineers if e.role_id != role_id
                    and e.total_capacity_rate >= HALF and team_id in e.orbits
                    and e.engineer_id != mentor.engineer_id]
        for trainee in trainees:
            trained = _training(inputs, trainee, mentor, role_id, team_id, start_sprint)
            results.append(_outcome(
                base, _plan(trained, int(active["as_of_sprint"]), active["params"] or {}),
                inputs, "train", f"Обучить {trainee.engineer_id} у {mentor.engineer_id}",
                start_sprint + 1,
                "0,5 ставки сотрудника меняет роль после одного спринта; наставник теряет 0,1 ставки в учебном спринте",
            ))

    lenders = [e for e in inputs.engineers if e.role_id == role_id
               and e.total_capacity_rate >= HALF and team_id not in e.orbits]
    for lender in lenders:
        loaned = _loan(inputs, lender, team_id, start_sprint)
        results.append(_outcome(
            base, _plan(loaned, int(active["as_of_sprint"]), active["params"] or {}),
            inputs, "loan", f"Перевести 0,5 ставки {lender.engineer_id} в {team_id}",
            start_sprint, "0,5 ставки сняты с прежних орбит; общий фонд организации не вырос",
        ))
    results.sort(key=lambda row: (-len(row["restored_initiatives"]),
                                  -Decimal(row["net_sp_gain"]), -row["earlier_task_sprints"], row["label"]))
    latest = db.scalar("SELECT MAX(run_id) FROM plan_runs WHERE status IN ('ok', 'infeasible')")
    if latest != run_id:
        raise ScenarioUnavailable("План обновился во время расчёта")
    return {
        "run_id": run_id, "role_id": role_id, "team_id": team_id,
        "start_sprint": start_sprint,
        "assumptions": "Гипотезы не публикуются. Наём и обучение занимают один спринт. Для нового или обученного специалиста предполагаются подтверждённые навыки целевой роли; замещения ролей в штатном плане не разрешаются.",
        "assumed_skill_ids": sorted(_assumed_skills(inputs, role_id)),
        "baseline_in_quarter": len(base.in_quarter), "ranked_measures": results,
    }
