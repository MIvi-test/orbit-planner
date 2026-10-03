"""Живой граф зависимостей на дату прогона (DA-10)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date

from app.planner.constants import DEPENDENCY_MODE_FINISH_START
from app.planner.model import Inputs


# ---------------------------------------------------------------------------
#  ЧИСТАЯ ЛОГИКА: вход → план
# ---------------------------------------------------------------------------
def _refresh_live_graph(inputs: Inputs, as_of_sprint: int,
                        dependency_mode: str) -> tuple[Inputs, list[str]]:
    """Recalculate live lower bounds using completion dates, not ETL-era status."""
    if not inputs.all_deps:
        return inputs, []
    live = {task.task_id: task for task in inputs.tasks}
    predecessors: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for blocking, blocked, gap in inputs.all_deps:
        if blocked in live:
            predecessors[blocked].append((blocking, gap))

    def sprint_of(when: date) -> int:
        for no, (start, end) in sorted(inputs.sprints.items()):
            if when < start:
                return no - 1
            if start <= when <= end:
                return no
        return inputs.sprint_count + 1

    lower: dict[str, int] = {}
    issues: list[str] = []
    for task in sorted(inputs.tasks, key=lambda item: item.topo_order):
        bound = 1
        for blocking, gap in predecessors.get(task.task_id, ()):
            if blocking in live:
                if blocking not in lower:
                    raise ValueError(f"живой граф не топологичен: {blocking} → {task.task_id}")
                bound = max(bound, lower[blocking] + gap)
                continue
            dates = inputs.done_task_dates.get(blocking)
            if dates is None:
                continue
            anchor = (dates[1] if dependency_mode == DEPENDENCY_MODE_FINISH_START
                      else dates[0] or dates[1])
            if anchor is None:
                issues.append(f"{blocking} → {task.task_id}: у завершённой задачи нет даты события")
                bound = max(bound, max(1, inputs.last_reported_sprint + gap))
                continue
            anchor_sprint = sprint_of(anchor)
            if anchor_sprint >= as_of_sprint and anchor_sprint > 0:
                issues.append(f"{blocking} → {task.task_id}: фактическая дата {anchor} позже среза прогона")
                bound = inputs.sprint_count + 1
                continue
            bound = max(bound, anchor_sprint + gap)
            actual_start = inputs.task_actual_starts.get(task.task_id)
            if actual_start is not None and sprint_of(actual_start) < anchor_sprint + gap:
                issues.append(f"{blocking} → {task.task_id}: фактический старт нарушил зазор зависимости")
        lower[task.task_id] = bound
    return replace(inputs, tasks=tuple(replace(task, earliest_start_sprint=lower[task.task_id])
                                       for task in inputs.tasks)), issues
