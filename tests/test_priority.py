"""Стратегии приоритета инициативы и явный бизнес-приоритет (DA-11, ADR-032)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app import planner
from test_planner import engineer, inputs, task


def item(task_id: str, prodf: str, *, own: int | None, initiative: int | None, sp: int = 5,
         hours: int = 40, topo: int = 1, business: int | None = None):
    return replace(
        task(task_id, prodf=prodf, sp=sp, rung=initiative or 0, topo=topo, roles={1: hours}),
        priority_rung=initiative, own_rung=own, business_priority=business,
    )


def order(tasks, strategy):
    return [t.task_id for t in planner.order_tasks(tuple(tasks), strategy)]


def mixed():
    # Инициатива A: rung задач 90 и 10 (MAX = 90); инициатива B: 70 и 70 (MAX = 70).
    return [
        item("A1", "A", own=90, initiative=90, topo=1),
        item("A2", "A", own=10, initiative=90, topo=2),
        item("B1", "B", own=70, initiative=70, topo=1),
        item("B2", "B", own=70, initiative=70, topo=2),
    ]


def test_max_strategy_keeps_initiatives_together_by_their_best_rung() -> None:
    assert order(mixed(), planner.PRIORITY_MAX) == ["A1", "A2", "B1", "B2"]


def test_task_strategy_orders_by_the_tasks_own_rung_and_interleaves_initiatives() -> None:
    assert order(mixed(), planner.PRIORITY_TASK) == ["A1", "B1", "B2", "A2"]


def test_weighted_strategy_does_not_let_one_urgent_task_lift_the_whole_initiative() -> None:
    # A: (90·5 + 10·5) / 10 = 50 < B: 70 — B раньше, хотя MAX(rung) у A выше.
    assert order(mixed(), planner.PRIORITY_WEIGHTED) == ["B1", "B2", "A1", "A2"]


def test_completion_first_prefers_the_cheaper_initiative_on_equal_priority() -> None:
    tasks = [
        item("BIG", "BIGP", own=80, initiative=80, hours=300),
        item("SMALL", "SMALLP", own=80, initiative=80, hours=20),
    ]
    assert order(tasks, planner.PRIORITY_MAX) == ["BIG", "SMALL"]           # ничья по топологии и id
    assert order(tasks, planner.PRIORITY_COMPLETION_FIRST) == ["SMALL", "BIG"]


def test_business_priority_beats_every_strategy() -> None:
    tasks = mixed()
    tasks = [replace(t, business_priority=99) if t.prodf_id == "B" else t for t in tasks]
    for strategy in planner.PRIORITY_STRATEGIES:
        assert order(tasks, strategy)[:2] == ["B1", "B2"], strategy


def test_tasks_without_rung_go_last_and_ties_are_deterministic() -> None:
    tasks = [item("Z", "Z", own=None, initiative=None), item("Y", "Y", own=50, initiative=50),
             item("X", "X", own=50, initiative=50)]
    for strategy in planner.PRIORITY_STRATEGIES:
        assert order(tasks, strategy) == ["X", "Y", "Z"], strategy
        assert order(list(reversed(tasks)), strategy) == ["X", "Y", "Z"], strategy


def test_unknown_strategy_is_rejected() -> None:
    with pytest.raises(ValueError):
        planner.build_plan(inputs([task("A")], [engineer("ENG-1")]), priority_strategy="by_mood")


def test_strategy_and_overrides_are_recorded_in_the_run_and_the_explanation() -> None:
    source = inputs(
        [item("A1", "A", own=90, initiative=90), item("B1", "B", own=70, initiative=70, business=95)],
        [engineer("ENG-1")],
    )
    plan = planner.build_plan(source, priority_strategy=planner.PRIORITY_WEIGHTED)
    assert plan.params["priority_strategy"] == planner.PRIORITY_WEIGHTED
    assert plan.params["business_priorities"] == ["B"]
    rows = {row.task_id: row for row in plan.in_quarter}
    assert "задан бизнесом" in rows["B1"].reason_text
    assert rows["B1"].reason_details["priority_source"] == "business"
    assert rows["A1"].reason_details["priority_source"] == "dataset"
    assert "стратегия «weighted»" in rows["A1"].reason_text


def test_default_strategy_reproduces_the_previous_order_and_text() -> None:
    source = inputs([item("A1", "A", own=90, initiative=90)], [engineer("ENG-1")])
    plan = planner.build_plan(source)
    assert plan.params["priority_strategy"] == planner.DEFAULT_PRIORITY_STRATEGY == planner.PRIORITY_MAX
    assert "приоритет инициативы 90" in plan.in_quarter[0].reason_text


def test_the_strategy_changes_who_gets_scarce_hours() -> None:
    """Один инженер на 480 ч: задачи по 300 ч — влезает одна. Стратегия решает, какая."""
    tasks = [item("A1", "A", own=90, initiative=90, hours=300, sp=2),
             item("A2", "A", own=10, initiative=90, hours=300, topo=2, sp=2),
             item("B1", "B", own=70, initiative=70, hours=300, sp=2)]
    source = inputs(tasks, [engineer("ENG-1")], team_sp={"Team-1": 100})
    by_max = {r.task_id for r in planner.build_plan(source, priority_strategy="max", simulate_next_pi=False).in_quarter}
    by_weighted = {r.task_id for r in planner.build_plan(source, priority_strategy="weighted",
                                                          simulate_next_pi=False).in_quarter}
    assert by_max == {"A1"} and by_weighted == {"B1"}


def test_business_priority_validation_happens_before_touching_the_database(monkeypatch) -> None:
    from app import ingest

    monkeypatch.setattr(ingest.db, "query_one", lambda *a, **k: (_ for _ in ()).throw(AssertionError("db touched")))
    with pytest.raises(ingest.UploadError, match="от 0 до 1000"):
        ingest.set_initiative_priority("P", 5000, "основание")
    with pytest.raises(ingest.UploadError, match="основание"):
        ingest.set_initiative_priority("P", 90, "   ")

