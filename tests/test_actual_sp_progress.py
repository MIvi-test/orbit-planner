"""Подтверждённые SP — отдельный факт, а не функция потраченных часов."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app import ingest, planner
from tests.test_planner import T1, engineer, inputs, task


def test_replan_uses_confirmed_sp_remainder() -> None:
    original = task("A", sp=12, roles={1: 480})
    baseline = planner.build_plan(
        inputs([original], [engineer("E")], team_sp={T1: 2})
    )
    assert baseline.schedule[0].end_sprint == 6

    after_sprint_one = replace(original, remaining={1: Decimal(400)}, remaining_sp=Decimal(10))
    revised = planner.build_plan(
        inputs([after_sprint_one], [engineer("E")], team_sp={T1: 2}),
        as_of_sprint=2,
    )

    assert revised.schedule[0].decision == "in_quarter"
    assert (revised.schedule[0].start_sprint, revised.schedule[0].end_sprint) == (2, 6)
    assert sum((share for _, _, share in revised.sp_shares), Decimal(0)) == Decimal(10)


def test_report_parses_explicit_progress_without_using_hours(monkeypatch) -> None:
    def rows(sql, _params=None):
        if "SELECT task_id FROM tasks" in sql:
            return [{"task_id": "A"}]
        return []

    monkeypatch.setattr(ingest.db, "query_dicts", rows)
    data = b"task_id,status,completed_sp\nA,InProgress,2.00\n"
    parsed, errors, _ = ingest.parse_actuals(data, "actuals.csv")
    assert errors == []
    assert parsed[0].completed_sp == Decimal("2.00")
    assert parsed[0].hours == {}


def test_report_rejects_invalid_progress(monkeypatch) -> None:
    monkeypatch.setattr(
        ingest.db, "query_dicts",
        lambda sql, _params=None: [{"task_id": "A"}] if "SELECT task_id FROM tasks" in sql else [],
    )
    for value in ("-1", "NaN", "Infinity", "0.001"):
        parsed, errors, _ = ingest.parse_actuals(
            f"task_id,status,completed_sp\nA,InProgress,{value}\n".encode(), "actuals.csv"
        )
        assert parsed == []
        assert errors


def test_progress_is_bounded_by_original_size_across_sprints() -> None:
    row = ingest.ParsedRow("A", "InProgress", None, None, None, completed_sp=Decimal(3))
    assert ingest.validate_completed_sp([row], {"A": Decimal(12)}, {"A": Decimal(10)})
    row.completed_sp = Decimal(2)
    assert ingest.validate_completed_sp([row], {"A": Decimal(12)}, {"A": Decimal(10)}) == []
