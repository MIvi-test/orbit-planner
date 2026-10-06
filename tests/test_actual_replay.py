"""Семантика событий дат в отчёте и защита повторного Done."""
from __future__ import annotations

from datetime import date

from app import ingest


def parse(monkeypatch, start: str, end: str, status: str = "InProgress"):
    def rows(sql, _params=None):
        if "SELECT task_id FROM tasks" in sql:
            return [{"task_id": "A"}]
        return []

    monkeypatch.setattr(ingest.db, "query_dicts", rows)
    csv = f"task_id,status,actual_start,actual_end\nA,{status},{start},{end}\n".encode()
    return ingest.parse_actuals(csv, "actuals.csv")


def test_blank_date_means_no_event(monkeypatch) -> None:
    rows, errors, _ = parse(monkeypatch, "", "")
    assert errors == []
    assert rows[0].actual_start is None
    assert rows[0].clear_actual_start is False


def test_explicit_clear_is_distinct_from_blank(monkeypatch) -> None:
    rows, errors, _ = parse(monkeypatch, "CLEAR", "очистить")
    assert errors == []
    assert rows[0].actual_start is None and rows[0].clear_actual_start
    assert rows[0].actual_end is None and rows[0].clear_actual_end


def test_explicit_date_is_a_correction_event(monkeypatch) -> None:
    rows, errors, _ = parse(monkeypatch, "2026-07-04", "")
    assert errors == []
    assert rows[0].actual_start == date(2026, 7, 4)
    assert rows[0].clear_actual_start is False


def test_done_cannot_clear_completion_date(monkeypatch) -> None:
    rows, errors, _ = parse(monkeypatch, "", "CLEAR", "Done")
    assert rows == []
    assert any("нельзя очистить" in error for error in errors)


def test_repeated_done_without_date_keeps_first_completion() -> None:
    repeated = ingest.ParsedRow("A", "Done", None, None, None)
    first = ingest.ParsedRow("B", "Done", None, None, None)

    warnings = ingest.normalize_done_dates(
        [repeated, first], {"A": "Done", "B": "InProgress"}, date(2026, 7, 28)
    )

    assert repeated.actual_end is None  # SQL воспроизведения сохранит прежнее событие
    assert first.actual_end == date(2026, 7, 28)
    assert len(warnings) == 1 and warnings[0].startswith("B:")
