"""Исторический отчёт не зависит от сегодняшнего статуса и поздних прогонов."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_historical_deviation_is_pinned_to_report_and_plan() -> None:
    root = Path(__file__).resolve().parents[1]
    connection = psycopg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        with connection.cursor() as cursor:
            schema = psycopg.sql.Identifier(f"da37_{uuid4().hex}")
            cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(schema))
            cursor.execute(psycopg.sql.SQL("SET search_path TO {}").format(schema))
            for name in ("01_schema.sql", "02_contract.sql", "03_substitutions.sql", "04_views.sql"):
                cursor.execute((root / "db" / name).read_text())
            cursor.execute((root / "db/migrations/0037_historical_deviations.sql").read_text())
            cursor.execute("""
                INSERT INTO pi_periods (pi_id, start_date, end_date, sprint_count)
                VALUES ('PI', '2026-07-01', '2026-07-28', 2);
                INSERT INTO sprints (pi_id, sprint_no, start_date, end_date)
                VALUES ('PI', 1, '2026-07-01', '2026-07-14'),
                       ('PI', 2, '2026-07-15', '2026-07-28');
                INSERT INTO teams (team_id) VALUES ('T');
                INSERT INTO initiatives (prodf_id, br_id) VALUES ('P', 'BR');
                INSERT INTO tasks
                    (task_id, prodf_id, team_id, status, estimation_sp, estimated_hh_effective)
                VALUES ('A', 'P', 'T', 'ToDo', 5, 40),
                       ('B', 'P', 'T', 'ToDo', 3, 20);
                INSERT INTO tasks_seed_state (task_id, status)
                VALUES ('A', 'ToDo'), ('B', 'ToDo');
                INSERT INTO plan_runs (run_id, pi_id, as_of_sprint, algorithm, status)
                VALUES (1, 'PI', 0, 'test', 'ok');
                INSERT INTO plan_task_schedule (run_id, task_id, start_sprint, end_sprint, decision)
                VALUES (1, 'A', 1, 1, 'in_quarter');
                INSERT INTO actual_uploads
                    (upload_id, pi_id, sprint_no, plan_run_id, source_file, source_sha256)
                VALUES (1, 'PI', 1, 1, 'one.csv', 'one'),
                       (2, 'PI', 2, 1, 'two.csv', 'two');
                INSERT INTO task_actuals (upload_id, task_id, status, actual_end)
                VALUES (1, 'B', 'Done', '2026-07-10'),
                       (2, 'A', 'Done', '2026-07-20');
            """)

            def read_rows() -> dict[tuple[int, str], tuple[int, str]]:
                cursor.execute("""
                    SELECT sprint_no, task_id, plan_run_id, deviation
                    FROM v_sprint_deviation ORDER BY sprint_no, task_id
                """)
                return {(sprint, task): (run, deviation) for sprint, task, run, deviation in cursor}

            expected = {
                (1, "A"): (1, "не закрыта в срок"),
                (1, "B"): (1, "вне плана"),
                (2, "A"): (1, "завершена с опозданием"),
            }
            assert read_rows() == expected
            cursor.execute("UPDATE tasks SET status = 'Done' WHERE task_id = 'A'")
            cursor.execute("""
                INSERT INTO plan_runs (run_id, pi_id, as_of_sprint, algorithm, status)
                VALUES (2, 'PI', 2, 'later', 'ok')
            """)
            assert read_rows() == expected
    finally:
        connection.rollback()
        connection.close()
