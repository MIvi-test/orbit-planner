"""Порядок обхода задач: стратегии приоритета инициативы (DA-11, ADR-032)."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.planner.constants import (
    DEFAULT_PRIORITY_STRATEGY,
    PRIORITY_COMPLETION_FIRST,
    PRIORITY_MAX,
    PRIORITY_STRATEGIES,
    PRIORITY_TASK,
    PRIORITY_WEIGHTED,
)
from app.planner.model import TaskInput


def check_strategy(strategy: str) -> str:
    if strategy not in PRIORITY_STRATEGIES:
        raise ValueError(f"priority_strategy={strategy!r} не из {PRIORITY_STRATEGIES}")
    return strategy


def _weighted_rung(tasks: list[TaskInput]) -> Decimal | None:
    """Средневзвешенный по SP rung живых задач инициативы (задачи без rung не участвуют)."""
    pairs = [(Decimal(task.own_rung), task.estimation_sp or Decimal(1))
             for task in tasks if task.own_rung is not None]
    if not pairs:
        return None
    total = sum((weight for _value, weight in pairs), Decimal(0))
    return sum((value * weight for value, weight in pairs), Decimal(0)) / total


def effective_priority(task: TaskInput, strategy: str, groups: dict[str, list[TaskInput]]) -> Decimal | None:
    """Число, по которому сортируется задача. Больше — раньше. `None` — в конец.

    Явный бизнес-приоритет инициативы (`initiatives.business_priority`) главнее любой
    агрегации: его задал человек, и стратегия его не пересматривает.
    """
    if task.business_priority is not None:
        return Decimal(task.business_priority)
    if strategy == PRIORITY_TASK:
        return Decimal(task.own_rung) if task.own_rung is not None else None
    if strategy == PRIORITY_WEIGHTED:
        return _weighted_rung(groups[task.prodf_id])
    # max и completion_first: приоритет инициативы из датасета (MAX(rung), ADR-005).
    return Decimal(task.priority_rung) if task.priority_rung is not None else None


def order_tasks(tasks: tuple[TaskInput, ...], strategy: str) -> list[TaskInput]:
    """Задачи в порядке обхода жадного размещения.

    * `max` — как раньше: приоритет инициативы = MAX(rung) её задач, внутри — топология;
    * `task` — каждая задача по собственному rung (инициативы могут чередоваться);
    * `weighted` — приоритет инициативы = средневзвешенный по SP rung живых задач;
    * `completion_first` — как `max`, но при равном приоритете раньше инициатива, которую
      дешевле завершить (меньше остаток часов): ресурс уходит туда, где цель реально закроется.

    Ничья всегда разрешается детерминированно: по топологии и `task_id`.
    """
    check_strategy(strategy)
    groups: dict[str, list[TaskInput]] = defaultdict(list)
    remaining_hh: dict[str, Decimal] = defaultdict(Decimal)
    for task in tasks:
        groups[task.prodf_id].append(task)
        remaining_hh[task.prodf_id] += task.demand_hh

    def key(task: TaskInput) -> tuple:
        value = effective_priority(task, strategy, groups)
        base = (value is None, -(value or Decimal(0)))
        if strategy == PRIORITY_COMPLETION_FIRST:
            return (*base, remaining_hh[task.prodf_id], task.prodf_id, task.topo_order, task.task_id)
        return (*base, task.topo_order, task.task_id)

    return sorted(tasks, key=key)


__all__ = ["DEFAULT_PRIORITY_STRATEGY", "PRIORITY_MAX", "check_strategy", "effective_priority", "order_tasks"]
