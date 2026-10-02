"""Публикация прогона зависит от результата независимой SQL-приёмки."""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from app import planner


class Cursor:
    def __init__(self, violations: list[dict[str, str]]) -> None:
        self.violations = violations
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql, params=None) -> None:
        self.calls.append((" ".join(sql.split()), params))

    def executemany(self, sql, params) -> None:
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return {"run_id": 42}

    def fetchall(self):
        return self.violations


def empty_plan() -> planner.Plan:
    return planner.Plan(
        pi_id="PI-TEST", as_of_sprint=0, status="ok", note="test", params={},
        schedule=(), assignments=(), alerts=(), kpis=(), baseline=(), states=(),
    )


@pytest.mark.parametrize("violations", [[], [
    {"check_code": "UNDER_ALLOCATED", "entity": "A / QA", "detail": "нужно 40, назначено 0"},
]])
def test_only_validated_plan_becomes_active(monkeypatch, violations) -> None:
    cur = Cursor(violations)
    committed = False

    @contextmanager
    def transaction(*, operation):
        nonlocal committed
        assert operation == "planner_write"
        yield cur
        committed = True

    monkeypatch.setattr(planner.db, "transaction", transaction)

    if violations:
        with pytest.raises(planner.PlanValidationError) as caught:
            planner.write_plan(empty_plan())
        assert caught.value.run_id == 42
        assert caught.value.errors == 1
    else:
        assert planner.write_plan(empty_plan()) == 42

    assert committed  # диагностическая строка должна остаться после отказа
    insert = next(params for sql, params in cur.calls if sql.startswith("INSERT INTO plan_runs"))
    assert insert[4] == "failed"  # до проверки успешного прогона не существует
    validation_index = next(i for i, (sql, _) in enumerate(cur.calls)
                            if "FROM v_plan_violations" in sql)
    status_updates = [(i, params) for i, (sql, params) in enumerate(cur.calls)
                      if sql.startswith("UPDATE plan_runs SET status")]
    if violations:
        assert status_updates == []
        assert any("'{validation}'" in sql for sql, _ in cur.calls)
    else:
        assert status_updates == [(validation_index + 1, ("ok", 42))]


def test_validation_query_failure_rolls_back_instead_of_publishing(monkeypatch) -> None:
    class BrokenCursor(Cursor):
        def execute(self, sql, params=None) -> None:
            super().execute(sql, params)
            if "FROM v_plan_violations" in sql:
                raise RuntimeError("validation view unavailable")

    cur = BrokenCursor([])
    committed = False

    @contextmanager
    def transaction(*, operation):
        nonlocal committed
        yield cur
        committed = True

    monkeypatch.setattr(planner.db, "transaction", transaction)
    with pytest.raises(RuntimeError, match="validation view unavailable"):
        planner.write_plan(empty_plan())

    assert not committed
    assert not any(sql.startswith("UPDATE plan_runs SET status") for sql, _ in cur.calls)
