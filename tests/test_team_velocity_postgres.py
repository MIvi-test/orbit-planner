"""Наблюдаемая скорость команд и снимок ёмкости прогона в PostgreSQL (DA-27)."""
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from pg_support import load_base_file

ROOT = Path(__file__).resolve().parents[1]
FILES = ("01_schema.sql", "02_contract.sql", "03_substitutions.sql", "04_views.sql", "05_invariants.sql")


def _schema(cursor) -> None:
    schema = psycopg.sql.Identifier(f"da27_{uuid4().hex}")
    cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(schema))
    cursor.execute(psycopg.sql.SQL("SET search_path TO {}").format(schema))
    for name in FILES:
        load_base_file(cursor, ROOT / "db" / name)
    cursor.execute("""
        INSERT INTO pi_periods (pi_id, start_date, end_date, sprint_count)
        VALUES ('PI', '2026-07-01', '2026-07-28', 2);
        INSERT INTO sprints (pi_id, sprint_no, start_date, end_date)
        VALUES ('PI', 1, '2026-07-01', '2026-07-14'), ('PI', 2, '2026-07-15', '2026-07-28');
        INSERT INTO teams (team_id) VALUES ('A'), ('B');
        INSERT INTO initiatives (prodf_id, br_id) VALUES ('P', 'BR');
        INSERT INTO tasks (task_id, prodf_id, team_id, status, estimation_sp, estimated_hh_effective)
        VALUES ('t1', 'P', 'A', 'ToDo', 8, 10), ('t2', 'P', 'A', 'ToDo', 3, 10),
               ('tb', 'P', 'B', 'Done', 5, 10);
        INSERT INTO tasks_seed_state (task_id, status)
        VALUES ('t1', 'ToDo'), ('t2', 'ToDo'), ('tb', 'Done');
    """)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_observed_velocity_counts_progress_completion_and_zero_sprints() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            _schema(cursor)
            cursor.execute("""
                INSERT INTO actual_uploads (upload_id, pi_id, sprint_no, source_file, source_sha256, coverage_status)
                VALUES (1, 'PI', 1, 'a', 'a', 'complete'), (2, 'PI', 2, 'b', 'b', 'complete'),
                       (3, 'PI', 3, 'c', 'c', 'draft');
                -- спринт 1: t1 — подтверждённый прогресс 3 SP; t2 завершена (прогресс не сообщали)
                INSERT INTO task_actuals (upload_id, task_id, status, actual_end, completed_sp)
                VALUES (1, 't1', 'InProgress', NULL, 3), (1, 't2', 'Done', '2026-07-10', NULL),
                -- спринт 2: t1 завершена с ещё 2 SP прогресса
                       (2, 't1', 'Done', '2026-07-20', 2);
            """)
            cursor.execute(
                "SELECT sprint_no, team_id, delivered_sp FROM v_team_velocity_observed ORDER BY sprint_no, team_id"
            )
            rows = {(sprint, team): value for sprint, team, value in cursor.fetchall()}
            # Спринт 1: 3 (прогресс t1) + 3 (остаток SP завершённой t2) = 6.
            assert rows[(1, "A")] == Decimal("6.00")
            # Спринт 2: 2 (прогресс) + (8 − 3 − 2) = 3 остатка завершённой t1 = 5.
            assert rows[(2, "A")] == Decimal("5.00")
            # У команды B нет невыполненного бэклога: нулевая поставка ёмкость не опровергает.
            assert not any(team == "B" for _sprint, team in rows)
            # Черновик (draft) наблюдением не является.
            assert not any(sprint == 3 for sprint, _team in rows)
        connection.rollback()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_sp_overflow_uses_the_run_capacity_snapshot_and_missing_snapshot_is_an_error() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            _schema(cursor)
            cursor.execute("""
                INSERT INTO team_history (team_id, snapshot_date, velocity_achieved, planned_sp)
                VALUES ('A', '2026-06-01', 10, 10), ('A', '2026-06-15', 10, 10);  -- ёмкость по истории 8.00
                INSERT INTO plan_runs (run_id, pi_id, as_of_sprint, algorithm, params)
                VALUES (1, 'PI', 2, 'test', '{"capacity_model": {"version": 1}}');
                INSERT INTO plan_task_schedule (run_id, task_id, start_sprint, end_sprint, decision)
                VALUES (1, 't1', 2, 2, 'in_quarter');
                INSERT INTO task_state (run_id, task_id, as_of_sprint, status, remaining_hh, remaining_sp)
                VALUES (1, 't1', 2, 'ToDo', 10, 8);
                INSERT INTO plan_task_sp (run_id, task_id, sprint_no, sp) VALUES (1, 't1', 2, 8);
            """)

            def codes():
                cursor.execute("""SELECT check_code FROM v_plan_violations WHERE run_id = 1
                                  AND check_code IN ('SP_OVERFLOW', 'CAPACITY_SNAPSHOT_MISSING')
                                  ORDER BY check_code""")
                return [row[0] for row in cursor.fetchall()]

            # Прогон заявил модель ёмкости, а снимка нет — ошибка (8 SP при ёмкости 8.00 по истории).
            assert codes() == ["CAPACITY_SNAPSHOT_MISSING"]
            # Снимок со сниженной ёмкостью 5.00: 8 SP в спринте — перегрузка по ЕГО ёмкости,
            # хотя сегодняшняя витрина (8.00) её бы не заметила.
            cursor.execute("""
                INSERT INTO plan_team_capacity (run_id, team_id, history_points, observed_points, avg_velocity,
                                                focus_factor, available_sp_per_sprint, observed_through_sprint)
                VALUES (1, 'A', 2, 1, 6.25, 0.80, 5.00, 1)
            """)
            assert codes() == ["SP_OVERFLOW"]
            cursor.execute("UPDATE plan_team_capacity SET available_sp_per_sprint = 8.00 WHERE run_id = 1")
            assert codes() == []
        connection.rollback()
