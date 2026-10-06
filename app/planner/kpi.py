"""KPI по формулам ТЗ и слепок состояния задач."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.planner.constants import DONE_STATUS, KPI_TARGETS
from app.planner.model import Inputs, KpiRow, ScheduleRow, StateRow


def _build_kpis(
    inputs: Inputs,
    schedule: list[ScheduleRow],
    baseline_starts: dict[str, int],
    *,
    as_of_sprint: int = 0,
    sp_budget: dict[int, Decimal] | None = None,
) -> list[KpiRow]:
    """KPI по формулам ТЗ (ADR-023). Прогноз и факт — разные строки (`kind`).

    * «Процент выполнения квартального плана» = инициативы, завершённые в
      течение 12 недель / инициативы, включённые в первоначальный план × 100%.
      Включена в план = ВСЕ её живые задачи Недели 0 стоят в квартале: только
      такую инициативу план обещал завершить. Прогноз — по текущему прогону,
      факт — по загруженным результатам спринтов.
    * «Выполнение плана спринта» = фактически выполненные SP / первоначально
      запланированные SP × 100%. Запланировано на спринт = SP задач, которые
      первоначальный план закрывает в этом спринте. Для спринтов с загруженным
      фактом — факт, для остальных — прогноз текущего прогона.
    * Bus Factor — по компетенциям (ТЗ): минимум носителей по навыкам,
      чья роль нужна бэклогу. Это состояние, а не прогноз: kind = actual.

    Первоначальный план — канонический базовый прогон; пересчёт его не меняет.
    """
    current = {row.task_id: row for row in schedule}
    sp_of: dict[str, Decimal] = {task_id: sp for task_id, _st, sp, _rem in inputs.all_tasks}
    sp_of.update({task.task_id: task.estimation_sp for task in inputs.tasks})
    promised_sp = dict(sp_of)
    promised_sp.update(inputs.baseline_sp)
    status_of = {task_id: status for task_id, status, _sp, _rem in inputs.all_tasks}
    done_in_pi = set().union(*inputs.done_in_sprint.values()) if inputs.done_in_sprint else set()
    prodf_of = dict(inputs.task_prodf)
    prodf_of.update({task.task_id: task.prodf_id for task in inputs.tasks})

    if inputs.baseline_schedule:
        base = dict(inputs.baseline_schedule)
        base_source = "канонический базовый прогон"
    else:
        base = {row.task_id: (row.decision, row.start_sprint, row.end_sprint) for row in schedule}
        base_source = "этот прогон" if as_of_sprint == 0 else "этот прогон (базового ещё нет)"

    def pct(numerator: Decimal | int, denominator: Decimal | int) -> Decimal | None:
        if not denominator:
            return None
        return (Decimal(numerator) / Decimal(denominator) * 100).quantize(Decimal("0.01"))

    # --- процент выполнения квартального плана ----------------------------
    tasks_of: dict[str, list[str]] = defaultdict(list)
    for task_id in base:
        tasks_of[prodf_of.get(task_id, "?")].append(task_id)
    committed = sorted(
        prodf_id for prodf_id, ids in tasks_of.items() if all(base[t][0] == "in_quarter" for t in ids)
    )
    partial = sorted(
        prodf_id for prodf_id, ids in tasks_of.items()
        if prodf_id not in committed and any(base[t][0] == "in_quarter" for t in ids)
    )

    def done(task_id: str) -> bool:
        return status_of.get(task_id) == DONE_STATUS and task_id in done_in_pi

    on_track = sorted(
        prodf_id for prodf_id in committed
        if all(done(t) or (t in current and current[t].decision == "in_quarter") for t in tasks_of[prodf_id])
    )
    completed = sorted(prodf_id for prodf_id in committed if all(done(t) for t in tasks_of[prodf_id]))
    low, high = KPI_TARGETS["pi_predictability"]

    # Охват обязательств (DA-29): «2 из 2 обещанных» без знания, что всего инициатив 15 и что
    # план обещал лишь малую часть, выглядит как успех. Рядом всегда показываем знаменатель мира.
    initiatives_total = len(tasks_of)
    not_promised = sorted(set(tasks_of) - set(committed) - set(partial))
    beyond_promise = sorted(
        prodf_id for prodf_id in tasks_of
        if prodf_id not in committed and all(done(t) for t in tasks_of[prodf_id])
    )
    # Плановое накопление (DA-30): сколько обещанных инициатив база сравнения велит закрыть к
    # концу каждого спринта (конец инициативы = конец её последней задачи).
    initiative_end = {
        prodf_id: max((base[t][2] or 0) for t in tasks_of[prodf_id]) for prodf_id in committed
    }
    planned_by_sprint = {
        sprint_no: sum(1 for end in initiative_end.values() if end <= sprint_no)
        for sprint_no in range(1, inputs.sprint_count + 1)
    }
    common = {
        "formula": "инициативы, завершённые в течение 12 недель / инициативы, включённые в "
        "первоначальный план × 100%",
        "committed_initiatives": committed,
        "committed_n": len(committed),
        "partial_initiatives": partial,
        "baseline_source": base_source,
        "coverage": {
            "initiatives_total": initiatives_total,
            "committed": len(committed),
            "partial": len(partial),
            "not_promised": len(not_promised),
            "not_promised_initiatives": not_promised,
            "beyond_promise_done": beyond_promise,
            "text": f"обещано {len(committed)} из {initiatives_total} инициатив; частично в плане "
                    f"{len(partial)}; не обещано {len(not_promised)}",
        },
        "planned_completed_by_sprint": {str(no): count for no, count in planned_by_sprint.items()},
    }
    kpis: list[KpiRow] = [
        KpiRow(
            sprint_no=inputs.sprint_count,
            kpi_code="pi_predictability",
            value=pct(len(on_track), len(committed)),
            target_min=low,
            target_max=high,
            details={
                **common,
                "on_track_initiatives": on_track,
                "note": "прогноз: все задачи инициативы выполнены или стоят в квартале в этом "
                "прогоне. Частично включённые в план инициативы в знаменатель не входят — "
                "план не обещал их завершить",
            },
            kind="forecast",
            calculation_status="calculated" if committed else "no_commitment",
        )
    ]
    if inputs.last_reported_sprint > 0:
        kpis.append(
            KpiRow(
                sprint_no=inputs.sprint_count,
                kpi_code="pi_predictability",
                value=pct(len(completed), len(committed)),
                target_min=low,
                target_max=high,
                details={
                    **common,
                    "completed_initiatives": completed,
                    "reported_through_sprint": inputs.last_reported_sprint,
                    # Промежуточный срез сравнивается с плановым накоплением, а не с итоговой
                    # нормой квартала: ход строго по плану в 1-м спринте не провал (DA-30).
                    "final": inputs.last_reported_sprint >= inputs.sprint_count,
                    "expected_completed_by_now": planned_by_sprint.get(inputs.last_reported_sprint, 0),
                    "completed_n": len(completed),
                    "progress_vs_plan": (
                        "ahead" if len(completed) > planned_by_sprint.get(inputs.last_reported_sprint, 0)
                        else "on_plan" if len(completed) == planned_by_sprint.get(inputs.last_reported_sprint, 0)
                        else "behind"
                    ),
                    "note": f"факт по загруженным спринтам 1–{inputs.last_reported_sprint}: "
                    f"выполнены все задачи инициативы. До конца квартала значение промежуточное",
                },
                kind="actual",
                calculation_status="calculated" if committed else "no_commitment",
            )
        )

    # --- выполнение плана спринта ----------------------------------------
    planned_sp: dict[int, Decimal] = defaultdict(Decimal)
    planned_ids: dict[int, list[str]] = defaultdict(list)
    for task_id, (decision, _start, end) in base.items():
        if decision == "in_quarter" and end is not None:
            planned_sp[end] += promised_sp.get(task_id, Decimal("0"))
            planned_ids[end].append(task_id)
    low, high = KPI_TARGETS["say_do_ratio"]
    for sprint_no in range(1, inputs.sprint_count + 1):
        need = planned_sp.get(sprint_no, Decimal("0"))
        if sprint_no <= inputs.last_reported_sprint:
            ids = sorted(inputs.done_in_sprint.get(sprint_no, frozenset()))
            kind, note = "actual", "факт: SP задач с датой завершения в этом спринте, включая поздние отчёты"
        else:
            ids = sorted(
                task_id for task_id, row in current.items()
                if row.decision == "in_quarter" and row.end_sprint == sprint_no
            )
            kind, note = "forecast", "прогноз: SP задач, которые этот прогон закрывает в этом спринте"
        got = sum((sp_of.get(task_id, Decimal("0")) for task_id in ids), Decimal("0"))
        if need <= 0:
            note += "; на спринт первоначально ничего не планировали — отношение не определено"
        kpis.append(
            KpiRow(
                sprint_no=sprint_no,
                kpi_code="say_do_ratio",
                value=pct(got, need),
                target_min=low,
                target_max=high,
                details={
                    "formula": "фактически выполненные SP / первоначально запланированные SP × 100%",
                    "planned_sp": str(need),
                    "done_sp": str(got),
                    "unplanned_sp": str(got) if need <= 0 else "0",
                    "planned_tasks": sorted(planned_ids.get(sprint_no, [])),
                    "done_tasks": ids,
                    # Две величины с разными именами (DA-32): «план завершений» — SP задач, которые
                    # база сравнения закрывает в этом спринте (planned_sp); «бюджет работ» — доли SP,
                    # которые текущий план тратит в этом спринте (длинная задача распределена по
                    # спринтам). В закрытых спринтах бюджета текущего плана нет — смотри
                    # v_sprint_forecast_accuracy: там прогноз, сделанный перед спринтом.
                    "work_budget_sp": str((sp_budget or {}).get(sprint_no, Decimal("0")))
                    if sprint_no > inputs.last_reported_sprint else None,
                    "note": note,
                },
                kind=kind,
                calculation_status="calculated" if need > 0 else "no_plan",
            )
        )

    # --- Bus Factor по компетенциям ---------------------------------------
    in_demand = [(name, bf) for name, bf, used, _sole in inputs.skill_bus_factor if used]
    low, high = KPI_TARGETS["bus_factor"]
    kpis.append(
        KpiRow(
            sprint_no=inputs.sprint_count,
            kpi_code="bus_factor",
            value=Decimal(min(bf for _name, bf in in_demand)) if in_demand else None,
            target_min=low,
            target_max=high,
            details={
                "method": "по компетенциям: для каждого заявленного навыка — число инженеров, "
                "которые им владеют; значение — минимум по навыкам, чья роль нужна бэклогу",
                "competencies_n": len(inputs.skill_bus_factor),
                "single_holder_n": sum(1 for _n, bf, _u, _s in inputs.skill_bus_factor if bf == 1),
                "critical_n": sum(1 for _n, _bf, used, critical in inputs.skill_bus_factor
                                  if used and critical),
                "critical": sorted(name for name, _bf, used, critical in inputs.skill_bus_factor
                                   if used and critical),
                "roles_without_staff": [name for name, bf, _demand in inputs.bus_factor if bf == 0],
                "note": "«критично» — единственный носитель востребованного навыка, "
                "даже если коллеги той же роли не владеют им. Для непроверенных задач "
                "спрос оценён через роль и помечен как приближение в звёздной карте. "
                "Роли без людей в штате — отдельная проблема найма",
            },
            kind="actual",
            calculation_status="calculated" if in_demand else "no_relevant_skills",
        )
    )
    return kpis


def _build_states(
    inputs: Inputs, schedule: list[ScheduleRow], as_of_sprint: int
) -> list[StateRow]:
    """Слепок ВСЕХ задач (и Done тоже): это временно́й саттелит, а не план."""
    decisions = {row.task_id: row for row in schedule}
    sp_remaining = {task.task_id: task.sp_to_plan for task in inputs.tasks}
    states: list[StateRow] = []
    for task_id, status, sp, remaining in inputs.all_tasks:
        if status == DONE_STATUS:
            states.append(
                StateRow(task_id, as_of_sprint, DONE_STATUS, Decimal("0"), Decimal("0"), None)
            )
            continue
        row = decisions.get(task_id)
        sp = sp_remaining.get(task_id, sp)
        if row is None:
            states.append(StateRow(task_id, as_of_sprint, status, remaining, sp, None))
        elif row.decision == "in_quarter":
            states.append(StateRow(task_id, as_of_sprint, status, remaining, sp, row.end_sprint))
        elif row.decision == "cancelled":
            states.append(StateRow(task_id, as_of_sprint, "Cancelled", remaining, sp, None))
        else:
            states.append(StateRow(task_id, as_of_sprint, "Deferred", remaining, sp, None))
    return states
