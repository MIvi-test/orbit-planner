"""Алерты прогона: дефицит ролей, срыв квартала, каскадные сдвиги."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.planner.constants import (
    DEPENDENCY_MODE_FINISH_START,
    DEFAULT_DEPENDENCY_MODE,
    REASON_ROLE_NOT_IN_STAFF,
)
from app.planner.model import AlertRow, Assignment, Inputs, ScheduleRow
from app.planner.fmt import _q


def _build_alerts(
    inputs: Inputs,
    schedule: list[ScheduleRow],
    baseline_starts: dict[str, int],
    *,
    assignments: list[Assignment] | tuple[Assignment, ...] = (),
    lower_bounds: dict[str, int] | None = None,
    as_of_sprint: int = 0,
    dependency_mode: str = DEFAULT_DEPENDENCY_MODE,
) -> list[AlertRow]:
    """Три типа рисков из ТЗ.

    * orange — «дефицит специалистов на следующий спринт»: независимый от
      расписания спрос готовых задач за один спринт больше фонда роли. Доля
      каждой задачи ограничена одним полным фондом инженера за спринт;
    * red — «выход прогнозной даты завершения за пределы квартала»: инициатива,
      у которой есть задачи вне квартала; дата указана только если её даёт
      явно помеченный сценарий следующего PI;
    * yellow — «сдвиг цепочки зависимых задач»: прогноз окончания предшественника
      и срок хотя бы одного потомка ухудшились относительно базового плана.
    """
    by_id = {task.task_id: task for task in inputs.tasks}
    fte = Decimal(inputs.fte_hours_per_sprint)
    lower_bounds = lower_bounds or {}
    alerts: list[AlertRow] = []

    # --- orange: дефицит специалистов на следующий спринт -------------------
    next_sprint = max(1, as_of_sprint)
    if next_sprint <= inputs.sprint_count:
        factor = inputs.sprint_factors.get(next_sprint, Decimal("1"))
        supply: dict[int, Decimal] = defaultdict(Decimal)
        for engineer in inputs.engineers:
            supply[engineer.role_id] += engineer.total_capacity_rate * fte * factor
        demand: dict[int, Decimal] = defaultdict(Decimal)
        ready_tasks: dict[int, list[str]] = defaultdict(list)
        names: dict[int, str] = {}
        scheduled = {row.task_id: row for row in schedule}
        blockers: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for blocking, blocked, gap in inputs.deps:
            blockers[blocked].append((blocking, gap))
        for row in schedule:
            task = by_id.get(row.task_id)
            if task is None or row.decision == "cancelled":
                continue
            earliest = lower_bounds.get(row.task_id, task.earliest_start_sprint)
            for blocking, gap in blockers.get(row.task_id, ()):
                predecessor = scheduled.get(blocking)
                if predecessor is None:
                    continue  # Done-предшественник уже включён в earliest_start_sprint
                anchor = (predecessor.end_sprint if dependency_mode == DEPENDENCY_MODE_FINISH_START
                          else predecessor.start_sprint)
                earliest = max(earliest, anchor + gap if anchor is not None else next_sprint + 1)
            if earliest > next_sprint:
                continue
            for role_id, remaining_hh in task.needed.items():
                if remaining_hh <= 0:
                    continue
                # У длинной задачи спрос одного спринта не равен всему
                # квартальному остатку. Одна задача не требует более одного
                # полного инженера одной роли в этом индикаторе.
                demand[role_id] += min(remaining_hh, fte * factor)
                ready_tasks[role_id].append(task.task_id)
                names[role_id] = task.role_names.get(role_id, str(role_id))
        for role_id in sorted(demand):
            need = demand[role_id]
            have = supply.get(role_id, Decimal("0"))
            if need <= have:
                continue
            tail = (
                "в штате нет ни одного специалиста — нужен наём или дообучение"
                if have == 0
                else f"не хватает {_q(need - have)} ЧЧ"
            )
            alerts.append(
                AlertRow(
                    sprint_no=next_sprint,
                    level="orange",
                    alert_type="role_deficit",
                    entity_type="role",
                    entity_id=names[role_id],
                    message=(
                        f"спринт {next_sprint}: готовому бэклогу роли «{names[role_id]}» "
                        f"нужно {_q(need)} ЧЧ, доступно {_q(have)} ЧЧ — {tail}"
                    ),
                    payload={
                        "role_id": role_id,
                        "role_name": names[role_id],
                        "sprint_no": next_sprint,
                        "demand_hh": str(need),
                        "demand_rule": "для каждой готовой задачи min(остаток роли, 80 ЧЧ × доля спринта)",
                        "supply_hh": str(have),
                        "tasks": sorted(ready_tasks[role_id]),
                        "verdict": "НАЙМ: закрыть некем" if have == 0 else "НАЙМ: не хватает часов",
                        "reason": "замещения ролей отклонены организаторами (ответ №2, ADR-010)",
                    },
                )
            )

    # --- red: прогноз выходит за квартал, цель инициативы под угрозой -------
    base = inputs.baseline_schedule
    committed: set[str] = set()
    if base:
        tasks_of: dict[str, list[str]] = defaultdict(list)
        for task_id in base:
            tasks_of[inputs.task_prodf.get(task_id, by_id[task_id].prodf_id if task_id in by_id else "?")].append(task_id)
        committed = {
            prodf_id for prodf_id, ids in tasks_of.items()
            if all(base[task_id][0] == "in_quarter" for task_id in ids)
        }
    outside: dict[str, list[ScheduleRow]] = defaultdict(list)
    for row in schedule:
        if row.decision != "in_quarter" and row.task_id in by_id:
            outside[by_id[row.task_id].prodf_id].append(row)
    for prodf_id in sorted(outside):
        rows = sorted(outside[prodf_id], key=lambda item: item.task_id)
        task_ids = [row.task_id for row in rows]
        hh = sum((by_id[task_id].demand_hh for task_id in task_ids), Decimal("0"))
        threatened = prodf_id in committed and as_of_sprint > 0
        dated = [row.forecast_end_date for row in rows if row.forecast_end_date is not None]
        forecast_end = max(dated) if len(dated) == len(rows) else None
        deadline = inputs.sprints.get(inputs.sprint_count, (None, None))[1]
        detected_on = inputs.sprints.get(min(max(1, as_of_sprint), inputs.sprint_count), (None, None))[0]
        delay_days = (forecast_end - deadline).days if forecast_end and deadline else None
        missing_role = any(row.reason_code == REASON_ROLE_NOT_IN_STAFF for row in rows)
        if forecast_end is not None:
            forecast_text = (f"прогноз завершения {forecast_end.isoformat()}, "
                             f"задержка {delay_days} дн. при том же штате и календаре")
        elif missing_role:
            forecast_text = "дата завершения не определена: нет требуемой роли в штате"
        else:
            forecast_text = ("дата завершения не определена: выбранный сценарий "
                             "следующего PI не разместил все задачи")
        message = (
            f"{prodf_id}: цель квартала под угрозой — {len(task_ids)} задач из первоначального "
            f"плана больше не укладываются в 12 недель ({_q(hh)} ЧЧ); {forecast_text}"
            if threatened
            else f"{prodf_id}: {len(task_ids)} задач вне квартала, {hh} ЧЧ "
            f"не закрыто — инициатива не уложится в квартал; {forecast_text}"
        )
        alerts.append(
            AlertRow(
                sprint_no=inputs.sprint_count,
                level="red",
                alert_type="deadline_miss",
                entity_type="initiative",
                entity_id=prodf_id,
                message=message,
                payload={
                    "deferred_tasks": task_ids,
                    "deferred_hh": str(hh),
                    "baseline_committed": prodf_id in committed,
                    "threatened_goal": threatened,
                    "detected_on": detected_on.isoformat() if detected_on else None,
                    "deadline": deadline.isoformat() if deadline else None,
                    "forecast_end_date": forecast_end.isoformat() if forecast_end else None,
                    "delay_days": delay_days,
                    "forecast_basis": "тот же штат и календарь, без новых задач и найма",
                    "reasons": {row.task_id: row.reason_code for row in rows},
                    "cancelled": [row.task_id for row in rows if row.decision == "cancelled"],
                },
            )
        )

    # --- yellow: сдвиг сроков в цепочке зависимостей -------------------------
    dependents: dict[str, list[str]] = defaultdict(list)
    blockers_of: dict[str, list[str]] = defaultdict(list)
    for blocking, blocked, _gap in inputs.deps:
        dependents[blocking].append(blocked)
        blockers_of[blocked].append(blocking)
    current = {row.task_id: row for row in schedule}
    for row in schedule:
        base_entry = base.get(row.task_id)
        if row.decision != "in_quarter" or base_entry is None or row.end_sprint is None:
            continue
        base_end = base_entry[2]
        if base_end is None or row.end_sprint <= base_end or not dependents.get(row.task_id):
            continue
        affected = []
        for child_id in sorted(dependents[row.task_id]):
            child_base = base.get(child_id)
            child = current.get(child_id)
            if child_base is None or child_base[2] is None or child is None:
                continue
            new_end = child.end_sprint if child.decision == "in_quarter" else None
            if new_end is None or new_end > child_base[2]:
                affected.append({
                    "task_id": child_id,
                    "baseline_end_sprint": child_base[2],
                    "new_end_sprint": new_end,
                    "delay_sprints": new_end - child_base[2] if new_end is not None else None,
                })
        if not affected:
            continue
        base_start = baseline_starts.get(row.task_id) or base_entry[1]
        shifted_blockers = [
            b for b in blockers_of.get(row.task_id, ())
            if b in current and b in base and base[b][2] is not None
            and (current[b].end_sprint or 0) > base[b][2]
        ]
        if inputs.last_reported_sprint and base_end is not None and base_end <= inputs.last_reported_sprint:
            cause, cause_text = "own_slip", (
                f"не закрыта к концу спринта {inputs.last_reported_sprint}, как было в плане"
            )
        elif shifted_blockers:
            cause, cause_text = "dependency", f"сдвинулась блокирующая {', '.join(shifted_blockers)}"
        else:
            cause, cause_text = "capacity", "ресурс перераспределён после отклонений других задач"
        alerts.append(
            AlertRow(
                sprint_no=row.end_sprint,
                level="yellow",
                alert_type="cascade_shift",
                entity_type="task",
                entity_id=row.task_id,
                message=(
                    f"{row.task_id} завершится в спринте {row.end_sprint} вместо {base_end}; "
                    f"сдвинулись {len(affected)} зависимых задач — {cause_text}"
                ),
                payload={
                    "baseline_start_sprint": base_start,
                    "new_start_sprint": row.start_sprint,
                    "dependents": sorted(dependents[row.task_id]),
                    "baseline_end_sprint": base_end,
                    "new_end_sprint": row.end_sprint,
                    "affected_dependents": affected,
                    "cause": cause,
                    "cause_text": cause_text,
                    "reported_sprint": inputs.last_reported_sprint,
                },
            )
        )
    return alerts
