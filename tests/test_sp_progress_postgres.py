"""Подтверждённый объём SP и инвариант остаточного плана в PostgreSQL."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from pg_support import load_base_file

from app import planner


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_remaining_sp_and_share_invariant_use_confirmed_progress() -> None:
    root = Path(__file__).resolve().parents[1]
    connection = psycopg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        with connection.cursor() as cursor:
            schema = psycopg.sql.Identifier(f"da06_{uuid4().hex}")
            cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(schema))
            cursor.execute(psycopg.sql.SQL("SET search_path TO {}").format(schema))
            for name in ("01_schema.sql", "02_contract.sql", "03_substitutions.sql",
                         "04_views.sql", "05_invariants.sql"):
                load_base_file(cursor, root / "db" / name)
            cursor.execute((root / "db/migrations/0006_completed_sp.sql").read_text())
            cursor.execute("""
                INSERT INTO pi_periods (pi_id, start_date, end_date, sprint_count)
                VALUES ('PI', '2026-07-01', '2026-09-22', 6);
                INSERT INTO sprints (pi_id, sprint_no, start_date, end_date)
                SELECT 'PI', n, DATE '2026-07-01' + (n-1)*14,
                       DATE '2026-07-14' + (n-1)*14
                FROM generate_series(1, 6) n;
                INSERT INTO teams (team_id) VALUES ('T');
                INSERT INTO initiatives (prodf_id, br_id) VALUES ('P', 'BR');
                INSERT INTO tasks
                    (task_id, prodf_id, team_id, status, estimation_sp, estimated_hh_effective)
                VALUES ('A', 'P', 'T', 'InProgress', 12, 480);
                INSERT INTO actual_uploads (upload_id, pi_id, sprint_no, source_file, source_sha256)
                VALUES (1, 'PI', 1, 'one.csv', 'one');
                INSERT INTO task_actuals (upload_id, task_id, status, completed_sp)
                VALUES (1, 'A', 'InProgress', 2);
                INSERT INTO plan_runs (run_id, pi_id, as_of_sprint, algorithm, status)
                VALUES (1, 'PI', 2, 'test', 'ok');
                INSERT INTO task_state
                    (run_id, task_id, as_of_sprint, status, remaining_hh, remaining_sp)
                VALUES (1, 'A', 2, 'InProgress', 400, 10);
                INSERT INTO plan_task_schedule
                    (run_id, task_id, start_sprint, end_sprint, decision)
                VALUES (1, 'A', 2, 6, 'in_quarter');
                INSERT INTO plan_task_sp (run_id, task_id, sprint_no, sp)
                SELECT 1, 'A', n, 2 FROM generate_series(2, 6) n;
            """)
            cursor.execute(planner.LIVE_TASKS_SQL)
            columns = [column.name for column in cursor.description]
            assert cursor.fetchone()[columns.index("remaining_sp")] == Decimal(10)
            cursor.execute("""
                SELECT check_code FROM v_plan_violations
                WHERE run_id = 1 AND check_code = 'SP_SHARES_MISMATCH'
            """)
            assert cursor.fetchall() == []
            cursor.execute("""
                UPDATE plan_task_sp SET sp = 3
                WHERE run_id = 1 AND task_id = 'A' AND sprint_no = 6
            """)
            cursor.execute("""
                SELECT check_code FROM v_plan_violations
                WHERE run_id = 1 AND check_code = 'SP_SHARES_MISMATCH'
            """)
            assert cursor.fetchall() == [("SP_SHARES_MISMATCH",)]
    finally:
        connection.rollback()
        connection.close()
