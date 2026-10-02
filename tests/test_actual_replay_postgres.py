"""Проверка SQL-воспроизведения на PostgreSQL (TEST_DATABASE_URL)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import psycopg
import pytest


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_date_events_survive_replay_and_allow_corrections() -> None:
    connection = psycopg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA da18_replay_test")
            cursor.execute("SET search_path TO da18_replay_test")
            cursor.execute("""
                CREATE TABLE tasks (
                    task_id text PRIMARY KEY, status text NOT NULL,
                    actual_start date, actual_end date
                );
                CREATE TABLE tasks_seed_state (
                    task_id text PRIMARY KEY, status text NOT NULL,
                    actual_start date, actual_end date
                );
                CREATE TABLE task_role_spent (
                    task_id text, role_id int, hours numeric,
                    PRIMARY KEY (task_id, role_id)
                );
                CREATE TABLE task_role_spent_seed (
                    task_id text, role_id int, hours numeric
                );
                CREATE TABLE actual_uploads (
                    upload_id int PRIMARY KEY, sprint_no int NOT NULL
                );
                CREATE TABLE task_actuals (
                    upload_id int, task_id text, status text NOT NULL,
                    actual_start date, actual_end date,
                    PRIMARY KEY (upload_id, task_id)
                );
                CREATE TABLE task_actual_spent (
                    task_id text, role_id int, hours numeric
                );
            """)
            migration = Path(__file__).resolve().parents[1] / "db/migrations/0002_actual_date_events.sql"
            cursor.execute(migration.read_text())
            cursor.execute("INSERT INTO tasks VALUES ('A', 'ToDo', NULL, NULL)")
            cursor.execute("INSERT INTO tasks_seed_state VALUES ('A', 'ToDo', NULL, NULL)")
            cursor.execute("INSERT INTO actual_uploads VALUES (1, 1), (2, 2)")
            cursor.execute("""
                INSERT INTO task_actuals
                    (upload_id, task_id, status, actual_start, actual_end)
                VALUES (1, 'A', 'Done', '2026-07-01', '2026-07-14'),
                       (2, 'A', 'Done', NULL, NULL)
            """)

            def replay() -> tuple[date | None, date | None]:
                cursor.execute("SELECT apply_actuals()")
                cursor.execute("SELECT actual_start, actual_end FROM tasks WHERE task_id = 'A'")
                return cursor.fetchone()

            assert replay() == (date(2026, 7, 1), date(2026, 7, 14))

            cursor.execute("""
                UPDATE task_actuals SET actual_start = '2026-07-02'
                WHERE upload_id = 2 AND task_id = 'A'
            """)
            assert replay() == (date(2026, 7, 2), date(2026, 7, 14))

            cursor.execute("""
                UPDATE task_actuals SET actual_start = NULL, clear_actual_start = TRUE
                WHERE upload_id = 2 AND task_id = 'A'
            """)
            assert replay() == (None, date(2026, 7, 14))
    finally:
        connection.rollback()
        connection.close()
