"""Ёмкость команд в SP на момент прогона (DA-27, ADR-030)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.planner.model import CapacityRow, Inputs

CENT = Decimal("0.01")
DEFAULT_FOCUS_FACTOR = Decimal("0.8")


def effective_capacity(
    inputs: Inputs, as_of_sprint: int
) -> tuple[dict[str, Decimal], tuple[CapacityRow, ...]]:
    """Ёмкость в SP за полный спринт и её основание по каждой команде.

    ТЗ: ресурс команды — «средняя фактическая производительность × 0.8». Базовый план
    (Неделя 0) берёт историю `team_history`, и результат совпадает с `v_team_capacity_sp`.
    Пересчёт на начало спринта `k` добавляет наблюдения закрытых спринтов 1..k-1 текущего
    PI: команда, которая проседает, в пересчёте получает меньшую ёмкость, а не прежнюю.
    Будущий факт (спринты >= k) сюда не попадает, поэтому старый срез не меняется.

    Без данных об истории (`Inputs` собран вручную в тесте) возвращает ёмкость как есть и
    пустой снимок.
    """
    capacity = dict(inputs.team_sp_per_sprint)
    if not inputs.velocity_history:
        return capacity, ()
    closed = max(as_of_sprint - 1, 0)
    rows: list[CapacityRow] = []
    for team_id, (total, points) in sorted(inputs.velocity_history.items()):
        observed = [value for team, sprint, value in inputs.velocity_observed
                    if team == team_id and sprint <= closed]
        count = points + len(observed)
        if count == 0:
            continue
        focus = inputs.focus_factors.get(team_id, DEFAULT_FOCUS_FACTOR)
        average = (total + sum(observed, Decimal(0))) / count
        if not observed and team_id in inputs.team_sp_per_sprint:
            available = inputs.team_sp_per_sprint[team_id]  # ровно значение витрины
        else:
            available = (average * focus).quantize(CENT, rounding=ROUND_HALF_UP)
        capacity[team_id] = available
        rows.append(CapacityRow(
            team_id=team_id, history_points=points, observed_points=len(observed),
            avg_velocity=average.quantize(CENT, rounding=ROUND_HALF_UP), focus_factor=focus,
            available_sp_per_sprint=available, observed_through_sprint=closed if observed else 0,
        ))
    return capacity, tuple(rows)
