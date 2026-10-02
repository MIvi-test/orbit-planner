"""Один снимок и один commit на приём факта и публикацию плана."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app import db, ingest


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_atomic_transaction_hides_intermediate_state_and_rolls_back_failure(monkeypatch) -> None:
    dsn = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setattr(db, "load_config", lambda: {
        "dsn": dsn, "read_only": True, "statement_timeout_ms": 15_000,
    })
    schema = f"da40_{uuid4().hex}"
    with psycopg.connect(dsn) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(f"CREATE TABLE {schema}.state (value int NOT NULL)")

    insert = f"INSERT INTO {schema}.state (value) VALUES (1)"
    count = f"SELECT COUNT(*) FROM {schema}.state"
    with pytest.raises(RuntimeError, match="планирование упало"):
        with db.atomic_transaction():
            with db.transaction() as cursor:
                cursor.execute(insert)
            assert db.scalar(count) == 1  # планировщик видит факт в той же транзакции
            with psycopg.connect(dsn) as reader:
                assert reader.execute(count).fetchone()[0] == 0  # читатель видит старую версию
            raise RuntimeError("планирование упало")

    assert db.scalar(count) == 0
    with db.atomic_transaction():
        with db.transaction() as cursor:
            cursor.execute(insert)
        assert db.scalar(count) == 1
    assert db.scalar(count) == 1


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_failed_replan_restores_previous_upload_and_plan(monkeypatch) -> None:
    dsn = os.environ["TEST_DATABASE_URL"]
    schema = f"da40_ingest_{uuid4().hex}"
    root = Path(__file__).resolve().parents[1]
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA {schema}")
            cursor.execute(f"SET search_path TO {schema}")
            for name in ("01_schema.sql", "02_contract.sql"):
                cursor.execute((root / "db" / name).read_text())
            cursor.execute("""
                INSERT INTO pi_periods (pi_id, start_date, end_date, sprint_count)
                VALUES ('PI', '2026-07-01', '2026-07-28', 2);
                INSERT INTO sprints (pi_id, sprint_no, start_date, end_date)
                VALUES ('PI', 1, '2026-07-01', '2026-07-14'),
                       ('PI', 2, '2026-07-15', '2026-07-28');
                INSERT INTO teams (team_id) VALUES ('T');
                INSERT INTO initiatives (prodf_id, br_id) VALUES ('P', 'BR');
                INSERT INTO tasks
                    (task_id, prodf_id, team_id, status, estimated_hh_effective)
                VALUES ('A', 'P', 'T', 'ToDo', 10);
                INSERT INTO tasks_seed_state (task_id, status) VALUES ('A', 'ToDo');
                INSERT INTO plan_runs (run_id, pi_id, as_of_sprint, algorithm, status)
                VALUES (1, 'PI', 0, 'old', 'ok');
                INSERT INTO actual_uploads
                    (upload_id, pi_id, sprint_no, source_file, source_sha256)
                VALUES (1, 'PI', 1, 'old.csv', 'old');
                INSERT INTO task_actuals (upload_id, task_id, status)
                VALUES (1, 'A', 'InProgress');
                INSERT INTO plan_runs
                    (run_id, pi_id, as_of_sprint, algorithm, status, actuals_upload_id)
                VALUES (2, 'PI', 2, 'old', 'ok', 1);
                SELECT apply_actuals();
            """)

    monkeypatch.setattr(db, "load_config", lambda: {
        "dsn": dsn, "read_only": True, "statement_timeout_ms": 15_000,
    })
    original_atomic = db.atomic_transaction

    @contextmanager
    def in_schema():
        with original_atomic() as connection:
            connection.execute(f"SET LOCAL search_path TO {schema}")
            yield connection

    monkeypatch.setattr(db, "atomic_transaction", in_schema)
    monkeypatch.setattr(ingest, "run_plan", lambda _sprint: (_ for _ in ()).throw(
        RuntimeError("планирование упало")
    ))

    with pytest.raises(RuntimeError, match="планирование упало"):
        ingest.load_actuals(b"task_id,status\nA,Done\n", "new.csv", 1)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SET search_path TO {schema}")
            cursor.execute("SELECT upload_id, source_file FROM actual_uploads")
            assert cursor.fetchall() == [(1, "old.csv")]
            cursor.execute("SELECT run_id FROM plan_runs ORDER BY run_id")
            assert cursor.fetchall() == [(1,), (2,)]
            cursor.execute("SELECT status FROM tasks WHERE task_id = 'A'")
            assert cursor.fetchone() == ("InProgress",)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_failed_dataset_plan_restores_previous_dataset(monkeypatch, tmp_path) -> None:
    from etl import load as etl_load

    dsn = os.environ["TEST_DATABASE_URL"]
    schema = f"da40_dataset_{uuid4().hex}"
    with psycopg.connect(dsn) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(f"CREATE TABLE {schema}.state (status text NOT NULL)")
        conn.execute(f"INSERT INTO {schema}.state VALUES ('old')")

    monkeypatch.setattr(db, "load_config", lambda: {
        "dsn": dsn, "read_only": True, "statement_timeout_ms": 15_000,
    })
    monkeypatch.setattr(etl_load, "build_seed_sql", lambda _path: (
        f"UPDATE {schema}.state SET status = 'new'", {}, {},
    ))
    substitution_sql = tmp_path / "substitutions.sql"
    substitution_sql.write_text("BEGIN;\nCOMMIT;\n")
    monkeypatch.setattr(ingest, "SUBSTITUTIONS_SQL", substitution_sql)
    monkeypatch.setattr(ingest, "run_plan", lambda _sprint: (_ for _ in ()).throw(
        RuntimeError("планирование упало")
    ))

    with pytest.raises(RuntimeError, match="планирование упало"):
        ingest.load_dataset(b"fake xlsx", "dataset.xlsx")

    with psycopg.connect(dsn) as conn:
        assert conn.execute(f"SELECT status FROM {schema}.state").fetchone() == ("old",)
