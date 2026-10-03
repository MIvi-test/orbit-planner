"""Отметки миграций в базовой схеме актуальны (B-1): иначе migrate на чистой базе упадёт."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("gen_migration_stamps", ROOT / "tools/gen_migration_stamps.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stamps_file_matches_migrations_dir() -> None:
    tool = _tool()
    assert (ROOT / "db/06_migration_stamps.sql").read_text(encoding="utf-8") == tool.render(), (
        "db/06_migration_stamps.sql устарел: python tools/gen_migration_stamps.py"
    )


def test_migration_numbers_are_unique_and_ordered() -> None:
    names = sorted(p.name for p in (ROOT / "db/migrations").glob("*.sql"))
    numbers = [name[:4] for name in names]
    assert numbers == sorted(set(numbers)), "номера миграций должны быть уникальны"
