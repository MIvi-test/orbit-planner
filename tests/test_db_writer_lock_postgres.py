"""HTTP и CLI писатели получают последовательные снимки базы."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import psycopg
import pytest

from app import db


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_second_writer_waits_then_reads_committed_first_writer(monkeypatch) -> None:
    dsn = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setattr(db, "load_config", lambda: {
        "dsn": dsn, "read_only": True, "statement_timeout_ms": 15_000,
    })
    schema = f"da41_{uuid4().hex}"
    with psycopg.connect(dsn) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(f"CREATE TABLE {schema}.state (value int NOT NULL)")

    first_ready = Event()
    release_first = Event()
    second_started = Event()
    second_entered = Event()
    count = f"SELECT COUNT(*) FROM {schema}.state"

    def first() -> None:
        with db.atomic_transaction():
            with db.transaction() as cursor:
                cursor.execute(f"INSERT INTO {schema}.state VALUES (1)")
            first_ready.set()
            assert release_first.wait(5)

    def second() -> int:
        second_started.set()
        with db.atomic_transaction():
            second_entered.set()
            seen = db.scalar(count)
            with db.transaction() as cursor:
                cursor.execute(f"INSERT INTO {schema}.state VALUES (2)")
            return seen

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(first)
        assert first_ready.wait(5)
        second_future = pool.submit(second)
        assert second_started.wait(5)
        try:
            assert not second_entered.wait(0.2)
        finally:
            release_first.set()
        first_future.result(timeout=5)
        assert second_future.result(timeout=5) == 1

    assert db.scalar(count) == 2
