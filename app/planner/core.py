"""Ядро: чистая функция `build_plan` (вход -> `Plan`, без обращений к базе)."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.planner.constants import (
    ALGORITHM,
    DEFERRED_REASON,
    DEFERRED_REASON_BLOCKED,
    DEPENDENCY_MODES,
    DEPENDENCY_MODE_FINISH_START,
    DEPENDENCY_MODE_START_START,
    EFFICIENCY_NOTE,
    ESTIMATE_SOURCE,
    FORMULA_VERSION,
    INITIATIVE_MODES,
    INITIATIVE_MODE_ATOMIC,
    INITIATIVE_MODE_GREEDY,
    OBJECTIVE,
    OBJECTIVE_NOTE,
    REASON_ATOMIC,
    REASON_BLOCKED,
    REASON_ETC_REQUIRED,
    REASON_PI_CLOSED,
    REASON_PLANNED,
    REASON_ROLE_HOURS,
    REASON_ROLE_NOT_IN_STAFF,
    REASON_SKILL_UNAVAILABLE,
    REASON_TEAM_SP,
    SUBSTITUTION_MODE,
)
from app.planner.model import Assignment, BaselineRow, Inputs, Plan, ScheduleRow, TaskInput
from app.planner.fmt import _q, _sprints_word
from app.planner.funds import _Funds, _allocate_task, _sp_flow
from app.planner.graph import _refresh_live_graph
from app.planner.alerts import _build_alerts
from app.planner.kpi import _build_kpis, _build_states


def build_plan(
    inputs: Inputs,
    as_of_sprint: int = 0,
    baseline_starts: dict[str, int] | None = None,
    dependency_mode: str = DEPENDENCY_MODE_START_START,
    initiative_mode: str = INITIATIVE_MODE_GREEDY,
    simulate_next_pi: bool = True,
) -> Plan:
    """Строит план. Ни одного обращения к базе: всё, что нужно, уже во `Inputs`.

    `simulate_next_pi` — пробный сценарий (ADR-022): задачи, перенесённые
    из-за нехватки часов или ёмкости, раскладываются в следующий квартал
    с тем же штатом. Конкуренция и самостоятельная невместимость объясняются
    отдельно; сценарий не принимает решение об отмене бизнес-задачи.
    Внутренний вызов симуляции идёт с False, чтобы не уйти в рекурсию.

    `dependency_mode` и `initiative_mode` — решения ADR-013; оба уезжают
    в `plan_runs.params`, поэтому любой прогон сам объясняет, по каким правилам
    он построен. Значения по умолчанию — те, на которых прошла приёмка M2.
    """
    if not 0 <= as_of_sprint <= 12:
        raise ValueError(f"as_of_sprint={as_of_sprint} вне диапазона 0..12 (CHECK в plan_runs)")
    if dependency_mode not in DEPENDENCY_MODES:
        raise ValueError(f"dependency_mode={dependency_mode!r} не из {DEPENDENCY_MODES}")
    if initiative_mode not in INITIATIVE_MODES:
        raise ValueError(f"initiative_mode={initiative_mode!r} не из {INITIATIVE_MODES}")

    # В закрытые спринты план не пишется (ADR-014): при `as_of_sprint = k` спринт
    # k начинается «сегодня», всё до него — история. Инвариант
    # `ASSIGNMENT_IN_CLOSED_SPRINT` проверяет это независимо от алгоритма.
    replan_floor = max(1, as_of_sprint)

    inputs, dependency_fact_issues = _refresh_live_graph(inputs, as_of_sprint, dependency_mode)

    by_id = {task.task_id: task for task in inputs.tasks}
    # Кандидаты на роль — из покрытия (ADR-012), а не из `engineers.role_id`:
    # вьюха — единственный источник правды о паре «инженер × роль».
    by_role: dict[int, list[str]] = defaultdict(list)
    for engineer_id, role_id in inputs.coverage:
        by_role[role_id].append(engineer_id)
    for ids in by_role.values():
        ids.sort()
    qualified_by_task: dict[str, dict[int, list[str]]] = {}
    for task in inputs.tasks:
        eligible: dict[int, list[str]] = {}
        for role_id in task.needed:
            required = inputs.skill_requirements.get((task.task_id, role_id), frozenset())
            eligible[role_id] = [
                engineer_id for engineer_id in by_role.get(role_id, ())
                if required.issubset(inputs.engineer_skills.get(engineer_id, frozenset()))
            ]
        qualified_by_task[task.task_id] = eligible

    deps_by_blocked: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for blocking, blocked, gap in inputs.deps:
        deps_by_blocked[blocked].append((blocking, gap))

    # Порядок обхода: инициатива по скорингу (NULL — в конец), внутри — топология.
    ordered = sorted(
        inputs.tasks,
        key=lambda t: (t.priority_rung is None, -(t.priority_rung or 0), t.topo_order, t.task_id),
    )

    funds = _Funds(inputs)
    starts: dict[str, int] = {}
    ends: dict[str, int] = {}
    placed: dict[str, list[Assignment]] = {}
    sp_shares: dict[str, dict[int, Decimal]] = {}
    deferred: dict[str, str] = {}
    atomic_deferred: set[str] = set()
    # Итог квартала: факт загружен за последний спринт — планировать некуда (ADR-021).
    pi_closed = replan_floor > inputs.sprint_count

    def release(task_id: str) -> None:
        """Снять задачу с плана: вернуть в фонд её SP (по всем спринтам) и часы."""
        task = by_id[task_id]
        funds.free(placed.pop(task_id, []))
        for sprint_no, sp in sp_shares.pop(task_id, {}).items():
            funds.release_sp(task.team_id, sprint_no, sp)
        starts.pop(task_id, None)
        ends.pop(task_id, None)

    def release_initiative(prodf_id: str) -> list[str]:
        """Откат ВСЕЙ инициативы: вернуть в фонд её SP и часы (ADR-013)."""
        rolled = [
            task.task_id for task in ordered if task.prodf_id == prodf_id and task.task_id in starts
        ]
        for task_id in rolled:
            release(task_id)
        return rolled

    def defer_initiative(prodf_id: str) -> None:
        """Атомарный режим: откатанные задачи инициативы — тоже переносы.

        Раньше откат снимал задачи с плана, но не помечал их перенесёнными,
        и сборка расписания падала бы на `ends[task_id]`.
        """
        for rolled in release_initiative(prodf_id):
            deferred[rolled] = blocked_reason(by_id[rolled])
            atomic_deferred.add(rolled)

    def ready_from(blocking: str, gap: int) -> int:
        """С какого спринта блокируемая задача вправе стартовать (ADR-013).

        `start_start`: старт блокирующей + зазор. `finish_start`: КОНЕЦ
        блокирующей + зазор. Блокирующая могла быть снята с плана между
        проходами — тогда ограничение не действует и берётся нижняя граница
        пересчёта.
        """
        if dependency_mode == DEPENDENCY_MODE_FINISH_START:
            return (ends.get(blocking) or starts.get(blocking, replan_floor)) + gap
        return starts.get(blocking, replan_floor) + gap

    def blocked_reason(task: TaskInput) -> str:
        """M3 — если задачу держит перенесённая блокирующая чужая команда."""
        for blocking, _gap in deps_by_blocked.get(task.task_id, ()):
            if blocking in deferred and by_id[blocking].team_id != task.team_id:
                return DEFERRED_REASON_BLOCKED
        return DEFERRED_REASON

    def lower_bound(task: TaskInput) -> int:
        """Нижняя граница старта: закрытые спринты, граф и уже принятые зазоры."""
        lower = max(replan_floor, task.earliest_start_sprint)
        for blocking, gap in deps_by_blocked.get(task.task_id, ()):
            if blocking in starts:  # блокирующая уже поставлена — держим зазор
                lower = max(lower, ready_from(blocking, gap))
        return lower

    def missing_roles(task: TaskInput) -> list[int]:
        """Роли задачи, на которые в штате нет НИ ОДНОГО инженера."""
        return [role_id for role_id in sorted(task.needed) if not by_role.get(role_id)]

    def missing_skills(task: TaskInput) -> list[int]:
        return [
            role_id for role_id in sorted(task.needed)
            if inputs.skill_requirements.get((task.task_id, role_id))
            and by_role.get(role_id)
            and not qualified_by_task[task.task_id][role_id]
        ]

    def place(task: TaskInput, lower: int) -> bool:
        """Поставить задачу в минимальный подходящий спринт. False — не влезла.

        Часы раскладываются первыми, затем SP текут по спринтам начиная со
        спринта ФАКТИЧЕСКОГО старта (ADR-020): в каждом спринте команда берёт не
        больше свободной ёмкости, остаток — в следующих. Окно задачи —
        от первого спринта с часами до последнего спринта с часами или с SP.
        """
        if task.remaining_unknown or not task.needed:
            return False
        capacity = inputs.team_sp_per_sprint.get(task.team_id, Decimal("0"))
        for candidate in range(max(replan_floor, lower), inputs.sprint_count + 1):
            result = _allocate_task(
                task, candidate, funds, qualified_by_task[task.task_id],
                inputs.sprint_count, inputs.coverage
            )
            if result is None:
                continue
            rows, start_used, end_hours = result
            shares = _sp_flow(task, start_used, funds, capacity, inputs.sprint_count)
            if shares is None:
                funds.free(rows)  # SP не укладываются от этого старта — пробуем позже
                continue
            for sprint_no, sp in shares.items():
                funds.take_sp(task.team_id, sprint_no, sp)
            starts[task.task_id] = start_used
            ends[task.task_id] = max([end_hours, *shares])
            placed[task.task_id] = rows
            sp_shares[task.task_id] = shares
            deferred.pop(task.task_id, None)
            atomic_deferred.discard(task.task_id)
            return True
        return False

    def propagate_deferrals() -> None:
        """Перенесённая блокирующая тянет за собой зависимые (инвариант
        `DEPENDENCY_BLOCKER_DEFERRED`). Зовётся после КАЖДОГО прохода, который
        может что-то перенести: раньше переносы третьего прохода не протягивались."""
        changed = True
        while changed:
            changed = False
            for task in ordered:
                if task.task_id in deferred:
                    continue
                if any(b in deferred for b, _gap in deps_by_blocked.get(task.task_id, ())):
                    release(task.task_id)
                    deferred[task.task_id] = blocked_reason(task)
                    if initiative_mode == INITIATIVE_MODE_ATOMIC:
                        defer_initiative(task.prodf_id)
                    changed = True

    def fix_gaps() -> None:
        """Догон зазоров, если блокирующая уехала позже, чем стояла зависимая."""
        for _ in range(len(ordered) + 1):
            violations = [
                (blocking, blocked, gap)
                for blocking, blocked, gap in inputs.deps
                if blocking in starts
                and blocked in starts
                and starts[blocked] < ready_from(blocking, gap)
            ]
            if not violations:
                return
            for blocking, blocked, gap in violations:
                if blocked not in starts:  # уже снята выше по этому же циклу
                    continue
                task = by_id[blocked]
                release(blocked)
                if not place(task, max(lower_bound(task), ready_from(blocking, gap))):
                    deferred[blocked] = blocked_reason(task)
                    if initiative_mode == INITIATIVE_MODE_ATOMIC:
                        defer_initiative(task.prodf_id)

    # ---- проход 1: обход в порядке приоритетов ----------------------------
    if pi_closed:
        for task in ordered:
            deferred[task.task_id] = DEFERRED_REASON
    elif initiative_mode == INITIATIVE_MODE_ATOMIC:
        # Пробная упаковка инициативы целиком (ADR-013): не влезла хоть одна
        # задача — откат всех. Иначе дефицитный исполнитель занят инициативой,
        # которая всё равно не завершится, а KPI считает только завершённые.
        groups: dict[str, list[TaskInput]] = defaultdict(list)
        for task in ordered:  # `ordered` уже отсортирован — порядок инициатив сохранён
            groups[task.prodf_id].append(task)
        for prodf_id, members in groups.items():
            for task in members:
                if not place(task, lower_bound(task)):
                    break
            else:
                continue
            release_initiative(prodf_id)
            for task in members:
                deferred[task.task_id] = blocked_reason(task)
                atomic_deferred.add(task.task_id)
    else:
        for task in ordered:
            if not place(task, lower_bound(task)):
                deferred[task.task_id] = DEFERRED_REASON

    if not pi_closed:
        # ---- проходы 2–3: перенос тянет зависимые, догон зазоров -----------
        propagate_deferrals()
        fix_gaps()
        propagate_deferrals()

        # ---- проход 4: повторная упаковка (ADR-020) ------------------------
        # Переносы проходов 2–3 возвращают часы и SP в фонд. Без этого прохода
        # освободившийся ресурс пропадал, а причина «не хватило ресурсов» у
        # перенесённой задачи была бы неправдой. Атомарный режим не трогаем:
        # там упаковка — по инициативам целиком.
        if initiative_mode == INITIATIVE_MODE_GREEDY:
            for _ in range(len(ordered) + 1):
                placed_now = False
                for task in ordered:
                    if task.task_id not in deferred or missing_roles(task):
                        continue
                    if any(b in deferred for b, _gap in deps_by_blocked.get(task.task_id, ())):
                        continue
                    if place(task, lower_bound(task)):
                        placed_now = True
                if not placed_now:
                    break
                fix_gaps()
                propagate_deferrals()

    # ---- причины решений (ADR-022) ---------------------------------------
    rank = {task.task_id: index for index, task in enumerate(ordered, start=1)}

    def taken_by(role_id: int, limit: int = 5) -> list[str]:
        """Какие поставленные задачи больше всех заняли часы этой роли."""
        hours: dict[str, Decimal] = defaultdict(Decimal)
        for task_id, rows in placed.items():
            for row in rows:
                if row.role_id == role_id:
                    hours[task_id] += row.hours
        ranked = sorted(hours.items(), key=lambda item: (-item[1], item[0]))
        return [task_id for task_id, _hours in ranked[:limit]]

    def diagnose(task: TaskInput) -> tuple[str, str, dict[str, Any]]:
        """Почему задача не в квартале — по фактическому состоянию фонда."""
        task_id = task.task_id
        if task.remaining_unknown or not task.needed:
            return (
                REASON_ETC_REQUIRED,
                "Перенесена: для незакрытой задачи остаток работ неизвестен или равен нулю; "
                "уточните ETC по ролям либо подтвердите статус Done",
                {"remaining_unknown": task.remaining_unknown, "remaining_hh": str(task.demand_hh)},
            )
        if pi_closed:
            return (
                REASON_PI_CLOSED,
                f"Перенесена: квартал завершён (факт загружен за спринт "
                f"{inputs.last_reported_sprint}), остаток {_q(task.demand_hh)} ЧЧ уходит "
                f"в следующий PI",
                {"remaining_hh": str(task.demand_hh)},
            )
        missing = missing_roles(task)
        if missing:
            items = [
                {"role": task.role_names.get(role_id, str(role_id)), "hours": str(task.needed[role_id])}
                for role_id in missing
            ]
            listed = ", ".join(f"«{item['role']}» ({_q(Decimal(item['hours']))} ЧЧ)" for item in items)
            return (
                REASON_ROLE_NOT_IN_STAFF,
                f"Перенесена: в штате нет роли {listed} — закрыть эту часть работы некому. "
                f"Нужен наём или дообучение; замещения ролей запрещены организаторами",
                {"missing_roles": items},
            )
        skill_gaps = missing_skills(task)
        if skill_gaps:
            details = [
                {"role": task.role_names.get(role_id, str(role_id)),
                 "skills": sorted(inputs.skill_names.get(skill_id, str(skill_id))
                                  for skill_id in inputs.skill_requirements[(task.task_id, role_id)])}
                for role_id in skill_gaps
            ]
            return (
                REASON_SKILL_UNAVAILABLE,
                "Перенесена: нет инженера требуемой роли с подтверждёнными навыками "
                + "; ".join(f"{item['role']}: {', '.join(item['skills'])}" for item in details),
                {"skill_gaps": details},
            )
        blockers = sorted(b for b, _gap in deps_by_blocked.get(task_id, ()) if b in deferred)
        if blockers:
            return (
                REASON_BLOCKED,
                f"Перенесена: ждёт {', '.join(blockers)} — блокирующая задача сама не попала "
                f"в квартал, а начинать раньше неё нельзя",
                {
                    "blocked_by": blockers,
                    "other_team": any(by_id[b].team_id != task.team_id for b in blockers),
                },
            )
        lower = lower_bound(task)
        trial = _allocate_task(
            task, lower, funds, qualified_by_task[task.task_id],
            inputs.sprint_count, inputs.coverage,
        )
        if trial is not None:
            funds.free(trial[0])  # пробное распределение не должно залипнуть в фонде
            if task_id in atomic_deferred:
                return (
                    REASON_ATOMIC,
                    f"Перенесена вместе с инициативой {task.prodf_id}: сама задача помещается, "
                    f"но другая задача инициативы — нет, а режим atomic частичных инициатив "
                    f"не допускает",
                    {"prodf_id": task.prodf_id},
                )
            capacity = inputs.team_sp_per_sprint.get(task.team_id, Decimal("0"))
            free_sp = sum(
                (
                    max(capacity * funds.sprint_factor(n) - funds.used_sp[(task.team_id, n)], Decimal("0"))
                    for n in range(lower, inputs.sprint_count + 1)
                ),
                Decimal("0"),
            )
            return (
                REASON_TEAM_SP,
                f"Перенесена: часов специалистов хватает, но у {task.team_id} не осталось "
                f"ёмкости — нужно {_q(task.sp_to_plan)} SP, свободно {_q(free_sp)} SP со "
                f"спринта {lower} до конца квартала; ёмкость заняли задачи с более высоким "
                f"приоритетом",
                {
                    "team_id": task.team_id,
                    "need_sp": str(task.sp_to_plan),
                    "free_sp": str(free_sp.quantize(Decimal("0.01"))),
                    "from_sprint": lower,
                },
            )
        shortages = []
        for role_id, need in sorted(task.needed.items()):
            free = sum(
                (
                    max(funds.total_left(engineer_id, n), Decimal("0"))
                    for engineer_id in qualified_by_task[task.task_id].get(role_id, ())
                    for n in range(lower, inputs.sprint_count + 1)
                ),
                Decimal("0"),
            )
            if free < need:
                shortages.append(
                    {
                        "role": task.role_names.get(role_id, str(role_id)),
                        "need_hh": str(need),
                        "free_hh": str(free.quantize(Decimal("0.01"))),
                        "taken_by": taken_by(role_id),
                    }
                )
        if shortages:
            listed = "; ".join(
                f"«{item['role']}»: нужно {_q(Decimal(item['need_hh']))} ЧЧ, свободно "
                f"{_q(Decimal(item['free_hh']))} ЧЧ"
                + (f" (часы заняты {', '.join(item['taken_by'])})" if item["taken_by"] else "")
                for item in shortages
            )
            text = (
                f"Перенесена: не хватает часов специалистов со спринта {lower} до конца квартала — "
                f"{listed}. Часы отданы задачам с более высоким приоритетом"
            )
        else:
            text = (
                "Перенесена: часов по ролям в сумме хватает, но их не собрать в нужные спринты — "
                "свободные часы у людей разнесены по разным командам и спринтам"
            )
        return (REASON_ROLE_HOURS, text, {"shortages": shortages, "from_sprint": lower})

    reasons = {task.task_id: diagnose(task) for task in ordered if task.task_id in deferred}

    # Пробный следующий PI — сценарий с тем же штатом, не доказательство
    # невозможности задачи и не основание автоматически рекомендовать отмену.
    next_pi_check: dict[str, Any] = {
        "simulated": [], "fits_next_pi": [], "not_selected": [],
        "assumptions": "тот же штат и календарь, без новых задач и найма",
    }
    next_pi_forecast: dict[str, date] = {}
    if simulate_next_pi and not pi_closed and initiative_mode == INITIATIVE_MODE_GREEDY:
        pool = {
            task_id for task_id, (code, _text, _details) in reasons.items()
            if code in (REASON_ROLE_HOURS, REASON_TEAM_SP)
        }
        grew = True
        while grew:  # зависимые едут в симуляцию, если их держат только такие задачи
            grew = False
            for task_id, (code, _text, details) in reasons.items():
                if task_id in pool or code != REASON_BLOCKED:
                    continue
                if all(b in pool for b in details.get("blocked_by", [])):
                    pool.add(task_id)
                    grew = True
        if pool:
            simulated = replace(
                inputs,
                tasks=tuple(
                    replace(task, earliest_start_sprint=1) for task in ordered if task.task_id in pool
                ),
                deps=tuple(dep for dep in inputs.deps if dep[0] in pool and dep[1] in pool),
                all_deps=(), done_task_dates={}, task_actual_starts={},
                baseline_schedule={},
            )
            trial_plan = build_plan(
                simulated,
                as_of_sprint=0,
                dependency_mode=dependency_mode,
                initiative_mode=initiative_mode,
                simulate_next_pi=False,
            )
            fits_next = {row.task_id for row in trial_plan.schedule if row.decision == "in_quarter"}
            next_pi_forecast = {
                row.task_id: row.forecast_end_date + timedelta(days=inputs.pi_days)
                for row in trial_plan.schedule
                if row.decision == "in_quarter" and row.forecast_end_date is not None
            }
            next_pi_check.update({
                "simulated": sorted(pool), "fits_next_pi": sorted(fits_next),
                "not_selected": sorted(pool - fits_next),
                "forecast_end_dates": {task_id: end.isoformat()
                                       for task_id, end in sorted(next_pi_forecast.items())},
            })
            for task_id in sorted(pool - fits_next):
                code, text, details = reasons[task_id]
                alone = replace(
                    simulated, tasks=(next(task for task in simulated.tasks
                                            if task.task_id == task_id),), deps=(),
                )
                standalone_plan = build_plan(
                    alone, as_of_sprint=0, dependency_mode=dependency_mode,
                    initiative_mode=initiative_mode, simulate_next_pi=False,
                )
                standalone_fits = any(
                    row.task_id == task_id and row.decision == "in_quarter"
                    for row in standalone_plan.schedule
                )
                if standalone_fits:
                    scenario_note = (
                        "В выбранный сценарий следующего PI задача не вошла из-за "
                        "конкуренции за ресурс; отдельно она помещается."
                    )
                    scenario_result = "competing_capacity"
                else:
                    scenario_note = (
                        "Отдельно при том же штате и календаре задача также не помещается; "
                        "нужно пересмотреть объём, декомпозицию или ресурс."
                    )
                    scenario_result = "needs_scope_or_capacity_review"
                reasons[task_id] = (
                    code, text + " " + scenario_note,
                    {**details, "next_pi_scenario": scenario_result,
                     "next_pi_assumptions": next_pi_check["assumptions"]},
                )

    def legacy_reason(code: str, details: dict[str, Any]) -> str:
        """Старый код расхождений для колонки decision_reason (совместимость)."""
        if code == REASON_BLOCKED and details.get("other_team"):
            return DEFERRED_REASON_BLOCKED
        return DEFERRED_REASON

    def explain_planned(task: TaskInput) -> tuple[str, dict[str, Any]]:
        """Почему задача ВКЛЮЧЕНА — ТЗ требует объяснять и это."""
        task_id = task.task_id
        rows = placed.get(task_id, [])
        roles: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            roles[task.role_names.get(row.role_id, str(row.role_id))].add(row.engineer_id)
        loan_hh = sum((row.hours for row in rows if row.home_team_id != row.serving_team_id), Decimal("0"))
        shares = sp_shares.get(task_id, {})
        window = (
            f"спринт {starts[task_id]}"
            if starts[task_id] == ends[task_id]
            else f"спринты {starts[task_id]}–{ends[task_id]}"
        )
        parts = [
                f"Включена: приоритет инициативы {task.priority_rung} — {rank[task_id]}-я в очереди "
                f"из {len(ordered)}, {window}",
                "Роли закрыты: "
                + "; ".join(f"{name} — {', '.join(sorted(people))}" for name, people in sorted(roles.items())),
        ]
        if loan_hh > 0:
            parts.append(f"{_q(loan_hh)} ЧЧ взяты в заём у других команд")
        if len(shares) > 1:
            parts.append(
                f"{_q(task.sp_to_plan)} SP растянуты на {_sprints_word(len(shares))}: "
                f"это больше свободной ёмкости команды за один спринт"
            )
        hour_sprints = {row.sprint_no for row in rows}
        sp_only = sorted(set(shares) - hour_sprints)
        hours_only = sorted(hour_sprints - set(shares))
        if sp_only:
            parts.append(
                "спринты " + ", ".join(map(str, sp_only))
                + " содержат только долю SP: отдельный бюджет пропускной способности команды; "
                "дата результата ждёт последней доли SP"
            )
        if hours_only:
            parts.append(
                "спринты " + ", ".join(map(str, hours_only))
                + " содержат только работу инженеров; дата результата ждёт последних часов"
            )
        if task.remaining_provisional:
            parts.append(
                "остаток часов оценён как смета минус потраченное и не подтверждён ETC: "
                "прогресс по затратам не равен готовности — подтвердите остаток в факте спринта"
            )
        text = ". ".join(parts)
        return text, {
            "remaining_provisional": task.remaining_provisional,
            "priority_rung": task.priority_rung,
            "queue_rank": rank[task_id],
            "queue_size": len(ordered),
            "roles": {name: sorted(people) for name, people in sorted(roles.items())},
            "loan_hh": str(loan_hh),
            "sp_by_sprint": {str(n): str(sp) for n, sp in sorted(shares.items())},
        }

    # ---- расписание -------------------------------------------------------
    schedule: list[ScheduleRow] = []
    for task in ordered:
        task_id = task.task_id
        if task_id in deferred:
            code, text, details = reasons[task_id]
            forecast = next_pi_forecast.get(task_id)
            if forecast is not None:
                text += (f" Сценарий следующего PI при том же штате и календаре: "
                         f"завершение {forecast.isoformat()}.")
                details = {**details, "forecast_basis": next_pi_check["assumptions"],
                           "forecast_end_date": forecast.isoformat()}
            schedule.append(
                ScheduleRow(
                    task_id, None, None, forecast, "deferred_next_pi",
                    legacy_reason(code, details), code, text, details,
                )
            )
        else:
            end_sprint = ends[task_id]
            end_date = inputs.sprints.get(end_sprint, (None, None))[1]
            text, details = explain_planned(task)
            schedule.append(
                ScheduleRow(
                    task_id, starts[task_id], end_sprint, end_date, "in_quarter", None,
                    REASON_PLANNED, text, details,
                )
            )

    assignments = [_round_hours(row) for task in ordered for row in placed.get(task.task_id, [])]
    return _assemble(
        inputs,
        as_of_sprint,
        schedule,
        assignments,
        baseline_starts or {},
        {
            "dependency_mode": dependency_mode,
            "initiative_mode": initiative_mode,
            "replan_floor": replan_floor,
            "sp_model": "flow",
            "repack": initiative_mode == INITIATIVE_MODE_GREEDY,
            "next_pi_check": next_pi_check,
            "pi_closed": pi_closed,
            "dependency_fact_issues": dependency_fact_issues,
        },
        sp_shares=tuple(
            (task.task_id, n, sp)
            for task in ordered
            for n, sp in sorted(sp_shares.get(task.task_id, {}).items())
        ),
        lower_bounds={
            task.task_id: lower_bound(task) for task in ordered if task.task_id not in starts
        },
    )


def _round_hours(row: Assignment) -> Assignment:
    """Часы — ровно два знака: контракт хранит NUMERIC(8,2), округляем заранее."""
    return Assignment(
        task_id=row.task_id,
        sprint_no=row.sprint_no,
        engineer_id=row.engineer_id,
        role_id=row.role_id,
        hours=Decimal(row.hours).quantize(Decimal("0.01")),
        home_team_id=row.home_team_id,
        serving_team_id=row.serving_team_id,
        work_hours=(row.work_hours.quantize(Decimal("0.0001"))
                    if row.work_hours is not None else None),
    )


def _assemble(
    inputs: Inputs,
    as_of_sprint: int,
    schedule: list[ScheduleRow],
    assignments: list[Assignment],
    baseline_starts: dict[str, int],
    modes: dict[str, Any] | None = None,
    *,
    sp_shares: tuple[tuple[str, int, Decimal], ...] = (),
    lower_bounds: dict[str, int] | None = None,
) -> Plan:
    """Собирает `Plan`: алерты, KPI, базовая линия, слепок состояния, params.

    `modes` — режимы прогона (ADR-013/014): уезжают в `plan_runs.params`, чтобы
    у каждого результата было объяснение, по каким правилам он получен.
    """
    by_id = {task.task_id: task for task in inputs.tasks}
    in_quarter = [row for row in schedule if row.decision == "in_quarter"]
    deferred = [row for row in schedule if row.decision != "in_quarter"]

    alerts = _build_alerts(
        inputs, schedule, baseline_starts,
        assignments=assignments, lower_bounds=lower_bounds or {}, as_of_sprint=as_of_sprint,
        dependency_mode=(modes or {}).get("dependency_mode", DEPENDENCY_MODE_START_START),
    )
    kpis = _build_kpis(inputs, schedule, baseline_starts, as_of_sprint=as_of_sprint)
    states = _build_states(inputs, schedule, as_of_sprint)
    baseline = (
        [
            BaselineRow(
                task_id=task.task_id,
                planned_sp=task.estimation_sp,
                committed=task.task_id in {row.task_id for row in in_quarter},
            )
            for task in inputs.tasks
        ]
        if as_of_sprint == 0
        else []
    )

    in_quarter_hh = sum((by_id[row.task_id].demand_hh for row in in_quarter), Decimal("0"))
    deferred_hh = sum((by_id[row.task_id].demand_hh for row in deferred), Decimal("0"))
    loan_hh = sum(
        (row.hours for row in assignments if row.home_team_id != row.serving_team_id), Decimal("0")
    )

    # Видимость цены целевой функции (ADR-015): сколько инициатив закрыто целиком,
    # сколько осталось частично. В `greedy`-режиме частичные — норма, но заказчик
    # должен видеть их число, а не только агрегат KPI.
    by_initiative: dict[str, list[str]] = defaultdict(list)
    for task in inputs.tasks:
        by_initiative[task.prodf_id].append(task.task_id)
    in_quarter_ids = {row.task_id for row in in_quarter}
    complete_initiatives = [
        prodf_id for prodf_id, ids in by_initiative.items() if set(ids) <= in_quarter_ids
    ]
    partial_initiatives = sorted(
        prodf_id
        for prodf_id, ids in by_initiative.items()
        if 0 < len(set(ids) & in_quarter_ids) < len(ids)
    )

    # Календарь уезжает в `plan_runs.params`: прогон без границ PI невозможно
    # сопоставить с PI, а фонд 480 ЧЧ — объяснить календарём из шести
    # двухнедельных спринтов (ADR-025).
    pi_start = min((pair[0] for pair in inputs.sprints.values()), default=None)
    pi_end = max((pair[1] for pair in inputs.sprints.values()), default=None)
    short_sprints = {
        str(no): str(factor)
        for no, factor in sorted(inputs.sprint_factors.items())
        if factor < 1
    }
    active_role_pairs = {
        (task.task_id, role_id) for task in inputs.tasks for role_id in task.needed
    }
    unreviewed_skills = sorted(active_role_pairs - inputs.skill_reviews)

    params: dict[str, Any] = {
        "algorithm": ALGORITHM,
        "estimate_source": ESTIMATE_SOURCE,
        "skill_validation": {
            "confirmed_roles": len(active_role_pairs) - len(unreviewed_skills),
            "total_roles": len(active_role_pairs),
            "unreviewed": [{"task_id": task_id, "role_id": role_id}
                           for task_id, role_id in unreviewed_skills],
            "status": "confirmed" if not unreviewed_skills else "unverified",
            "note": "Отсутствие подтверждённых требований не доказывает соответствие стеку",
        },
        "calendar": {
            "pi_start": str(pi_start) if pi_start else None,
            "pi_end": str(pi_end) if pi_end else None,
            "sprint_count": inputs.sprint_count,
            "pi_days": inputs.pi_days,
            "fund_factor": str(inputs.fund_factor),
            "fund_hh_per_fte": str(inputs.fund_hours_per_fte),
            "short_sprints": short_sprints,
        },
        "estimate_validated": inputs.estimate_validated,
        "role_demand_snapshot_version": 1,
        "formula_version": FORMULA_VERSION,
        "baseline_run_id": inputs.baseline_run_id,
        "estimate_conflicts": inputs.estimate_conflicts,
        "estimate_conflicts_note": (
            "три источника часов расходятся; авторитетен столбец матрицы сметы "
            "(ADR-002, ответ организаторов №4), расхождения — в dq_issues"
        ),
        "substitution_mode": SUBSTITUTION_MODE,
        "active_substitutions": inputs.active_substitutions,
        "live_tasks": len(inputs.tasks),
        "in_quarter": len(in_quarter),
        "deferred": len(deferred),
        "in_quarter_hh": str(in_quarter_hh),
        "deferred_hh": str(deferred_hh),
        "loan_hh": str(loan_hh),
        "baseline_starts_used": bool(baseline_starts),
        "objective": OBJECTIVE,
        "objective_note": OBJECTIVE_NOTE,
        "efficiency_note": EFFICIENCY_NOTE,
        "initiatives_planned": len(by_initiative),
        "initiatives_complete": len(complete_initiatives),
        "initiatives_partial": partial_initiatives,
        "cancelled": sum(1 for row in schedule if row.decision == "cancelled"),
        "reasons": dict(sorted(Counter(row.reason_code for row in schedule if row.reason_code).items())),
        "actuals_upload_id": inputs.actuals_upload_id,
        "last_reported_sprint": inputs.last_reported_sprint,
    }
    params.update(modes or {})
    # Статус прогона описывает успешность расчёта. Результат для бизнеса живёт
    # отдельно: пустой план может означать и завершённый PI, и полный перенос.
    if not inputs.tasks:
        params["business_outcome"] = "completed"
    elif not in_quarter:
        params["business_outcome"] = "nothing_scheduled"
    elif deferred:
        params["business_outcome"] = "partial"
    else:
        params["business_outcome"] = "planned"
    reason_summary = ", ".join(
        f"{code} {count}" for code, count in params["reasons"].items() if code != "PLANNED"
    )
    note = (
        f"{len(in_quarter)} из {len(inputs.tasks)} живых задач в квартале, "
        f"{len(deferred)} не в квартале ({reason_summary or 'нет'}); инициатив целиком "
        f"{len(complete_initiatives)} из {len(by_initiative)}"
        f"{f', частично {len(partial_initiatives)}' if partial_initiatives else ''}; "
        f"алертов {len(alerts)}; займов {loan_hh} ЧЧ; замещения отклонены (ответ №2, ADR-010)"
    )
    return Plan(
        pi_id=inputs.pi_id,
        as_of_sprint=as_of_sprint,
        status="ok",
        note=note,
        params=params,
        schedule=tuple(schedule),
        assignments=tuple(assignments),
        alerts=tuple(alerts),
        kpis=tuple(kpis),
        baseline=tuple(baseline),
        states=tuple(states),
        sp_shares=sp_shares,
        actuals_upload_id=inputs.actuals_upload_id,
        role_demands=tuple(
            (task.task_id, role_id, hours)
            for task in inputs.tasks
            for role_id, hours in sorted(task.needed.items())
        ),
        graph_bounds=tuple((task.task_id, task.earliest_start_sprint) for task in inputs.tasks),
    )
