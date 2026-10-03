"""Ёмкость команд по истории и закрытым спринтам текущего PI (DA-27, ADR-030)."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app import planner
from test_planner import T1, engineer, inputs, task


def with_history(source: planner.Inputs, *, total: str, points: int, observed=(), focus: str = "0.8"):
    """Вход с историей скорости: сумма и число точек + наблюдения (команда, спринт, SP)."""
    history_total = Decimal(total)
    capacity = (history_total / points * Decimal(focus)).quantize(Decimal("0.01"))
    return replace(
        source,
        team_sp_per_sprint={T1: capacity},
        velocity_history={T1: (history_total, points)},
        velocity_observed=tuple((T1, sprint, Decimal(value)) for sprint, value in observed),
        focus_factors={T1: Decimal(focus)},
    )


def base():
    return inputs([task("A")], [engineer("ENG-1")])


def test_baseline_capacity_equals_history_view_value() -> None:
    source = with_history(base(), total="20", points=2)  # среднее 10 × 0.8 = 8.00
    capacity, rows = planner.effective_capacity(source, as_of_sprint=0)
    assert capacity == {T1: Decimal("8.00")}
    assert rows[0].history_points == 2 and rows[0].observed_points == 0
    assert rows[0].available_sp_per_sprint == Decimal("8.00")


def test_replan_adds_closed_sprints_of_the_current_pi() -> None:
    source = with_history(base(), total="20", points=2, observed=[(1, "4"), (2, "6")])
    capacity, rows = planner.effective_capacity(source, as_of_sprint=3)
    # (20 + 4 + 6) / 4 = 7.5; × 0.8 = 6.00
    assert capacity[T1] == Decimal("6.00")
    assert rows[0].observed_points == 2 and rows[0].observed_through_sprint == 2
    assert rows[0].avg_velocity == Decimal("7.50")


def test_future_and_current_sprints_are_never_used() -> None:
    source = with_history(base(), total="20", points=2, observed=[(1, "4"), (3, "99"), (4, "99")])
    capacity, rows = planner.effective_capacity(source, as_of_sprint=3)  # закрыты 1..2
    assert rows[0].observed_points == 1
    assert capacity[T1] == ((Decimal(20) + 4) / 3 * Decimal("0.8")).quantize(Decimal("0.01"))
    # Тот же срез, посчитанный позже, не меняется от будущего факта.
    again, _ = planner.effective_capacity(replace(source, velocity_observed=source.velocity_observed[:1]), 3)
    assert again == capacity


def test_zero_delivery_lowers_capacity_instead_of_being_ignored() -> None:
    source = with_history(base(), total="20", points=2, observed=[(1, "0")])
    capacity, _ = planner.effective_capacity(source, as_of_sprint=2)
    assert capacity[T1] < Decimal("8.00")


def test_inputs_without_history_are_returned_as_is() -> None:
    source = inputs([task("A")], [engineer("ENG-1")], team_sp={T1: 5})
    capacity, rows = planner.effective_capacity(source, as_of_sprint=3)
    assert capacity == source.team_sp_per_sprint and rows == ()


def test_build_plan_records_the_capacity_it_used() -> None:
    source = with_history(base(), total="20", points=2, observed=[(1, "2")])
    plan = planner.build_plan(source, as_of_sprint=2)
    assert plan.team_capacity and plan.team_capacity[0].observed_points == 1
    model = plan.params["capacity_model"]
    assert model["teams"][T1]["observed_points"] == 1
    assert Decimal(model["teams"][T1]["available_sp_per_sprint"]) == plan.team_capacity[0].available_sp_per_sprint


def test_lower_observed_velocity_shrinks_what_fits_into_the_quarter() -> None:
    """Команда, которая проседает, не получает прежнюю ёмкость: часть работы не влезает."""
    tasks = [task(f"T{i}", sp=20, topo=i, roles={1: 20}) for i in range(1, 7)]
    healthy = with_history(inputs(tasks, [engineer("ENG-1"), engineer("ENG-2")]), total="60", points=2)
    slipping = replace(healthy, velocity_observed=((T1, 1, Decimal("0")), (T1, 2, Decimal("0"))))
    fits_healthy = len(planner.build_plan(healthy, as_of_sprint=3).in_quarter)
    fits_slipping = len(planner.build_plan(slipping, as_of_sprint=3).in_quarter)
    assert fits_slipping < fits_healthy


def test_capacity_is_never_planned_beyond() -> None:
    """SP команды в спринте не превышают записанную в прогоне ёмкость."""
    source = with_history(
        inputs([task(f"T{i}", sp=4, topo=i, roles={1: 30}) for i in range(1, 5)],
               [engineer("ENG-1"), engineer("ENG-2")]),
        total="16", points=2, observed=[(1, "2")],
    )
    plan = planner.build_plan(source, as_of_sprint=2)
    limit = plan.team_capacity[0].available_sp_per_sprint
    for sprint in range(1, 7):
        used = sum((sp for _t, n, sp in plan.sp_shares if n == sprint), Decimal(0))
        assert used <= limit
