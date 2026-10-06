"""Ошибки качества Excel не доходят до записи seed и публикации плана."""
from pathlib import Path

import pytest

from app import ingest
from etl import load


def test_build_seed_stops_after_full_parse_before_emit(monkeypatch, tmp_path):
    def invalid_parse(_path):
        load.dq.add("engineers", "E-1", "PARTTIME_ATTRS_DIFFER", "error",
                    "Строки Excel 10 и 20: различаются роль или грейд")
        load.dq.add("tasks", "A", "ESTIMATE_SOURCES_DISAGREE", "warning", "оценки расходятся")
        return {}

    monkeypatch.setattr(load, "parse", invalid_parse)
    monkeypatch.setattr(load, "emit", lambda *_: pytest.fail("seed must not be generated"))
    with pytest.raises(load.DataQualityError) as exc:
        load.build_seed_sql(tmp_path / "changed.xlsx")
    assert len(exc.value.problems) == 1
    assert "Строки Excel 10 и 20" in exc.value.problems[0]


def test_warnings_do_not_block_seed(monkeypatch, tmp_path):
    def warning_parse(_path):
        load.dq.add("tasks", "A", "ESTIMATE_SOURCES_DISAGREE", "warning", "оценки расходятся")
        return {}

    monkeypatch.setattr(load, "parse", warning_parse)
    monkeypatch.setattr(load, "emit", lambda *_: ("seed", {"tasks": 1}))
    sql, _, quality = load.build_seed_sql(tmp_path / "changed.xlsx")
    assert sql == "seed"
    assert quality == {"error": 0, "warning": 1, "info": 0}


def test_rejected_upload_keeps_database_untouched(monkeypatch):
    def invalid_seed(_path: Path):
        raise load.DataQualityError(["engineers [E-1], PARTTIME_ATTRS_DIFFER: строки Excel 10 и 20"])

    monkeypatch.setattr(load, "build_seed_sql", invalid_seed)
    monkeypatch.setattr(ingest.db, "atomic_transaction", lambda: pytest.fail("database touched"))
    with pytest.raises(ingest.UploadError, match="блокирующие ошибки Excel") as exc:
        ingest.load_dataset(b"example", "changed.xlsx")
    assert "E-1" in exc.value.problems[0]
