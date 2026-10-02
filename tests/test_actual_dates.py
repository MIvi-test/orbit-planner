"""Дата завершения задаёт спринт факта и должна проходить проверку до записи."""
from __future__ import annotations

from contextlib import nullcontext
from datetime import date
from decimal import Decimal

import pytest

from app import ingest, planner
from tests.test_planner import inputs


PI_START = date(2026, 7, 1)
PI_END = date(2026, 9, 22)


def row(start: date | None, end: date | None, status: str = "Done") -> ingest.ParsedRow:
    return ingest.ParsedRow("A", status, start, end, None)


def test_reversed_dates_are_rejected_during_parse(monkeypatch) -> None:
    def query(sql, _params=None):
        if "FROM tasks" in sql:
            return [{"task_id": "A"}]
        return []

    monkeypatch.setattr(ingest.db, "query_dicts", query)
    data = b"task_id,status,actual_start,actual_end\nA,Done,2026-09-02,2026-07-02\n"

    rows, errors, _ = ingest.parse_actuals(data, "actuals.csv")

    assert rows == []
    assert any("позже даты окончания" in error for error in errors)


@pytest.mark.parametrize("end", [date(2026, 7, 15), date(2026, 10, 1)])
def test_future_or_out_of_pi_completion_is_rejected(end: date) -> None:
    errors, _ = ingest.normalize_actual_dates(
        [row(PI_START, end)], sprint_end=date(2026, 7, 14),
        pi_start=PI_START, pi_end=PI_END, today=date(2026, 10, 2),
    )
    assert errors


def test_invalid_completion_blocks_upload_before_database_write(monkeypatch) -> None:
    monkeypatch.setattr(ingest.db, "atomic_transaction", nullcontext)
    monkeypatch.setattr(ingest, "_pi", lambda: {"pi_id": "PI-TEST", "sprint_count": 6})
    monkeypatch.setattr(ingest, "_last_sprint", lambda _pi: 0)
    monkeypatch.setattr(ingest, "parse_actuals", lambda _data, _name: (
        [row(PI_START, date(2026, 10, 1))], [], [],
    ))
    monkeypatch.setattr(ingest.db, "query_dicts", lambda _sql, _params=None: [
        {"task_id": "A", "status": "ToDo"}
    ])
    monkeypatch.setattr(ingest.db, "query_one", lambda _sql, _params=None: {
        "sprint_start": PI_START, "sprint_end": date(2026, 7, 14),
        "pi_start": PI_START, "pi_end": PI_END,
    })

    def unexpected_write(*_args, **_kwargs):
        raise AssertionError("неверный факт не должен попасть в транзакцию")

    monkeypatch.setattr(ingest.db, "transaction", unexpected_write)
    monkeypatch.setattr(ingest, "_has_baseline", unexpected_write)

    with pytest.raises(ingest.UploadError, match="не принят") as caught:
        ingest.load_actuals(b"x", "actuals.csv", 1)
    assert any("вне PI" in problem for problem in caught.value.problems)


def test_late_report_keeps_the_actual_completion_date() -> None:
    actual = row(PI_START, date(2026, 7, 7))

    errors, warnings = ingest.normalize_actual_dates(
        [actual], sprint_end=date(2026, 9, 8),
        pi_start=PI_START, pi_end=PI_END, today=date(2026, 10, 2),
    )

    assert errors == warnings == []
    assert actual.actual_end == date(2026, 7, 7)


def test_future_event_is_rejected_even_if_sprint_calendar_allows_it() -> None:
    errors, _ = ingest.normalize_actual_dates(
        [row(PI_START, date(2026, 7, 7))], sprint_end=date(2026, 7, 14),
        pi_start=PI_START, pi_end=PI_END, today=date(2026, 7, 5),
    )
    assert any("ещё не наступила" in error for error in errors)


def test_done_without_date_uses_reporting_sprint_end() -> None:
    actual = row(PI_START, None)
    errors, warnings = ingest.normalize_actual_dates(
        [actual], sprint_end=date(2026, 7, 14),
        pi_start=PI_START, pi_end=PI_END, today=date(2026, 10, 2),
    )
    assert errors == []
    assert actual.actual_end == date(2026, 7, 14)
    assert warnings


def test_late_completion_counts_in_event_sprint_and_pi() -> None:
    source = inputs(
        [], [], all_tasks=(("A", "Done", Decimal("5"), Decimal("0")),),
        baseline_schedule={"A": ("in_quarter", 1, 1)},
        done_in_sprint={1: frozenset({"A"})}, last_reported_sprint=5,
    )
    plan = planner.build_plan(source, as_of_sprint=6)
    say_do = {k.sprint_no: k for k in plan.kpis if k.kpi_code == "say_do_ratio"}
    pi_actual = next(k for k in plan.kpis if k.kpi_code == "pi_predictability" and k.kind == "actual")

    assert say_do[1].details["done_tasks"] == ["A"]
    assert say_do[5].details["done_tasks"] == []
    assert pi_actual.value == Decimal("100.00")


def test_done_without_in_pi_completion_does_not_raise_predictability() -> None:
    source = inputs(
        [], [], all_tasks=(("A", "Done", Decimal("5"), Decimal("0")),),
        baseline_schedule={"A": ("in_quarter", 1, 1)}, last_reported_sprint=6,
    )
    plan = planner.build_plan(source, as_of_sprint=7)
    pi_actual = next(k for k in plan.kpis if k.kpi_code == "pi_predictability" and k.kind == "actual")
    assert pi_actual.value == Decimal("0.00")
