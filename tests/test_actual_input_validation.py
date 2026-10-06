"""Ошибки формата факта обнаруживаются до записи в базу."""
from decimal import Decimal

import pytest

from app import ingest


@pytest.fixture(autouse=True)
def known_task_and_role(monkeypatch):
    def query(sql, _params=None):
        if "FROM role_aliases" in sql:
            return [{"alias": "Разработка", "role_id": 1}]
        if "FROM roles" in sql:
            return [{"canonical_name": "Developer", "role_id": 1}]
        if "SELECT task_id FROM tasks" in sql:
            return [{"task_id": "A"}]
        raise AssertionError(sql)

    monkeypatch.setattr(ingest.db, "query_dicts", query)


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity", "0.001", "1000000"])
def test_invalid_hours_are_addressed_and_rejected(value):
    data = f"task_id,status,Developer\nA,InProgress,{value}\n".encode()
    rows, errors, _ = ingest.parse_actuals(data, "actuals.csv")
    assert rows == []
    assert "строка 2, A" in errors[0]
    assert "Developer" in errors[0]


def test_two_decimal_precision_accepts_trailing_zeroes():
    rows, errors, _ = ingest.parse_actuals(
        b"task_id,status,Developer,completed_sp\nA,InProgress,1.000,2.000\n", "actuals.csv"
    )
    assert errors == []
    assert rows[0].hours == {1: Decimal("1.000")}
    assert rows[0].completed_sp == Decimal("2.000")


@pytest.mark.parametrize("header", [
    "task_id,status,статус",
    "task_id,status,Developer,Разработка",
])
def test_duplicate_canonical_headers_are_rejected(header):
    with pytest.raises(ingest.UploadError, match="повторяются колонки") as exc:
        ingest.parse_actuals(f"{header}\nA,InProgress,1,2\n".encode(), "actuals.csv")
    assert "колонки" in exc.value.problems[0]


def test_unknown_column_with_data_is_error_even_if_task_id_is_blank():
    rows, errors, _ = ingest.parse_actuals(
        b"task_id,status,Other\nA,InProgress,3\n,ToDo,5\n", "actuals.csv"
    )
    assert len(rows) == 1
    assert len(errors) == 2
    assert all("неизвестной колонке" in error for error in errors)


def test_unknown_empty_column_is_only_warning():
    rows, errors, warnings = ingest.parse_actuals(
        b"task_id,status,Other\nA,InProgress,\n", "actuals.csv"
    )
    assert len(rows) == 1
    assert errors == []
    assert "Other" in warnings[0]


def test_invalid_utf8_is_rejected_without_replacement():
    with pytest.raises(ingest.UploadError, match="UTF-8"):
        ingest.parse_actuals(b"task_id,status,\xff\nA,InProgress,1\n", "actuals.csv")
