"""Приёмка ролевых часов использует снимок прогона, а не сегодняшний факт."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_role_demand_validation_is_stable_and_uses_equivalent_work():
    root = Path(__file__).resolve().parents[1]
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            schema = psycopg.sql.Identifier(f"da45_snapshot_{uuid4().hex}")
            cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(schema))
            cursor.execute(psycopg.sql.SQL("SET search_path TO {}").format(schema))
            for name in ("01_schema.sql", "02_contract.sql", "03_substitutions.sql",
                         "04_views.sql", "05_invariants.sql"):
                cursor.execute((root / "db" / name).read_text())
            for name in ("0045_plan_role_demand_snapshot.sql", "0046_refresh_plan_invariants.sql"):
                cursor.execute((root / "db/migrations" / name).read_text())
            cursor.execute("""
                INSERT INTO pi_periods (pi_id, start_date, end_date, sprint_count)
                VALUES ('PI', '2026-07-01', '2026-07-14', 1);
                INSERT INTO sprints (pi_id, sprint_no, start_date, end_date)
                VALUES ('PI', 1, '2026-07-01', '2026-07-14');
                INSERT INTO teams (team_id) VALUES ('T');
                INSERT INTO initiatives (prodf_id, br_id) VALUES ('P', 'BR');
                INSERT INTO roles (role_id, canonical_name) VALUES (1, 'Developer'), (2, 'QA');
                INSERT INTO engineers (engineer_id, role_id, grade, total_capacity_rate)
                VALUES ('E', 1, 'Senior', 1);
                INSERT INTO engineer_orbits (engineer_id, team_id, capacity_rate)
                VALUES ('E', 'T', 1);
                INSERT INTO tasks (task_id, prodf_id, team_id, status,
                                   estimation_sp, estimated_hh_effective)
                VALUES ('A', 'P', 'T', 'ToDo', 1, 10);
                INSERT INTO task_role_estimates (task_id, role_id, hours)
                VALUES ('A', 1, 10);
                INSERT INTO plan_runs (run_id, pi_id, as_of_sprint, algorithm, params)
                VALUES (1, 'PI', 0, 'test', '{"role_demand_snapshot_version":1}');
                INSERT INTO plan_task_schedule (run_id, task_id, start_sprint, end_sprint, decision)
                VALUES (1, 'A', 1, 1, 'in_quarter');
                INSERT INTO task_state (run_id, task_id, as_of_sprint, status,
                                        remaining_hh, remaining_sp)
                VALUES (1, 'A', 0, 'ToDo', 10, 1);
                INSERT INTO plan_role_demand_snapshot (run_id, task_id, role_id, needed_hours)
                VALUES (1, 'A', 1, 10);
                INSERT INTO plan_assignments (run_id, task_id, sprint_no, engineer_id,
                                              role_id, hours, work_hours,
                                              home_team_id, serving_team_id)
                VALUES (1, 'A', 1, 'E', 1, 20, 10, 'T', 'T');
            """)

            def role_errors():
                cursor.execute("""SELECT check_code FROM v_plan_violations
                                  WHERE run_id = 1 AND check_code IN
                                    ('UNDER_ALLOCATED', 'OVER_ALLOCATED',
                                     'ASSIGNMENT_ROLE_NOT_NEEDED') ORDER BY check_code""")
                return [row[0] for row in cursor.fetchall()]

            assert role_errors() == []  # 20 ч исполнителя = 10 ч сметной работы
            cursor.execute("INSERT INTO task_role_spent (task_id, role_id, hours) VALUES ('A', 1, 5)")
            assert role_errors() == []  # текущий остаток уже другой
            cursor.execute("UPDATE plan_assignments SET work_hours = 8 WHERE run_id = 1")
            assert role_errors() == ["UNDER_ALLOCATED"]
            cursor.execute("UPDATE plan_assignments SET work_hours = 12 WHERE run_id = 1")
            assert role_errors() == ["OVER_ALLOCATED"]
        connection.rollback()
