"""SQL-приёмка различает старт и завершение блокирующей задачи."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_long_blocker_is_checked_by_declared_mode():
    root = Path(__file__).resolve().parents[1]
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            schema = psycopg.sql.Identifier(f"da09_{uuid4().hex}")
            cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(schema))
            cursor.execute(psycopg.sql.SQL("SET search_path TO {}").format(schema))
            for name in ("01_schema.sql", "02_contract.sql", "03_substitutions.sql",
                         "04_views.sql", "05_invariants.sql"):
                cursor.execute((root / "db" / name).read_text())
            cursor.execute((root / "db/migrations/0048_dependency_mode_invariants.sql").read_text())
            cursor.execute("""
                INSERT INTO pi_periods (pi_id, start_date, end_date, sprint_count)
                VALUES ('PI', '2026-07-01', '2026-08-25', 4);
                INSERT INTO sprints (pi_id, sprint_no, start_date, end_date)
                VALUES ('PI', 1, '2026-07-01', '2026-07-14'),
                       ('PI', 2, '2026-07-15', '2026-07-28'),
                       ('PI', 3, '2026-07-29', '2026-08-11'),
                       ('PI', 4, '2026-08-12', '2026-08-25');
                INSERT INTO teams (team_id) VALUES ('T');
                INSERT INTO initiatives (prodf_id, br_id) VALUES ('P', 'BR');
                INSERT INTO tasks (task_id, prodf_id, team_id, status, estimated_hh_effective)
                VALUES ('A', 'P', 'T', 'ToDo', 10), ('B', 'P', 'T', 'ToDo', 10);
                INSERT INTO task_dependencies (blocking_task_id, blocked_task_id, raw_type)
                VALUES ('A', 'B', 'depends on');
                INSERT INTO plan_runs (run_id, pi_id, as_of_sprint, algorithm, params)
                VALUES (1, 'PI', 0, 'test', '{"dependency_mode":"start_start"}'),
                       (2, 'PI', 0, 'test', '{"dependency_mode":"finish_start"}'),
                       (3, 'PI', 0, 'test', '{"dependency_mode":"other"}');
                INSERT INTO plan_task_schedule (run_id, task_id, start_sprint, end_sprint, decision)
                VALUES (1, 'A', 1, 3, 'in_quarter'), (1, 'B', 2, 2, 'in_quarter'),
                       (2, 'A', 1, 3, 'in_quarter'), (2, 'B', 2, 2, 'in_quarter');
            """)
            cursor.execute("""SELECT run_id, check_code FROM v_plan_violations
                              WHERE check_code IN ('DEPENDENCY_VIOLATED', 'DEPENDENCY_MODE_UNKNOWN')
                              ORDER BY run_id, check_code""")
            assert cursor.fetchall() == [(2, "DEPENDENCY_VIOLATED"),
                                         (3, "DEPENDENCY_MODE_UNKNOWN")]
            cursor.execute("""UPDATE plan_task_schedule SET start_sprint = 4, end_sprint = 4
                              WHERE run_id = 2 AND task_id = 'B'""")
            cursor.execute("""SELECT check_code FROM v_plan_violations
                              WHERE run_id = 2 AND check_code = 'DEPENDENCY_VIOLATED'""")
            assert cursor.fetchall() == []
        connection.rollback()
