"""Ошибки графа останавливают ETL до генерации плана."""
from pathlib import Path

import pytest

from app import ingest
from etl import load


def test_cycle_reports_edges_and_excel_rows():
    tasks = [{"task_id": key, "status": "ToDo"} for key in ("A", "B", "C")]
    deps = [("A", "B", "depends on", 1), ("B", "A", "depends on", 1)]

    with pytest.raises(load.DependencyGraphError) as exc:
        load.build_sequence(tasks, deps, {("A", "B"): 12, ("B", "A"): 14})

    assert "A → B → A" in str(exc.value)
    assert "12, 14" in str(exc.value)


def test_cycle_through_done_task_is_still_rejected():
    tasks = [{"task_id": "A", "status": "ToDo"}, {"task_id": "B", "status": "Done"}]
    deps = [("A", "B", "depends on", 1), ("B", "A", "depends on", 1)]
    with pytest.raises(load.DependencyGraphError, match="цикл зависимостей"):
        load.build_sequence(tasks, deps)


@pytest.mark.parametrize(("edge", "previous", "message"), [
    (("A", "A", "depends on"), {}, "зависит от самой себя"),
    (("A", "B", "depends on"), {("A", "B"): 5}, "впервые в строке 5"),
    (("A", "C", "depends on"), {}, "неизвестную задачу"),
    (("A", "B", "unknown"), {}, "неизвестный тип зависимости"),
])
def test_invalid_edges_are_not_silently_dropped(edge, previous, message):
    with pytest.raises(load.DependencyGraphError, match=message) as exc:
        load.validate_dependency_edge(*edge, 10, {"A", "B"}, previous)
    assert "строка Excel 10" in str(exc.value)


def test_upload_reports_graph_error_without_entering_database(monkeypatch):
    def invalid_graph(_path: Path):
        raise load.DependencyGraphError("цикл зависимостей: A → B → A; строки Excel: 12, 14")

    monkeypatch.setattr(load, "build_seed_sql", invalid_graph)
    monkeypatch.setattr(ingest.db, "atomic_transaction", lambda: pytest.fail("database touched"))
    with pytest.raises(ingest.UploadError, match="ошибка графа зависимостей") as exc:
        ingest.load_dataset(b"example", "dataset.xlsx")
    assert "12, 14" in exc.value.problems[0]
