"""ETC отделён от накопленного факта в SQL-витрине."""
from __future__ import annotations

import os
from uuid import uuid4
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from pg_support import load_base_file


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_etc_overrides_exhausted_estimate() -> None:
    root = Path(__file__).resolve().parents[1]
    connection = psycopg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        with connection.cursor() as cursor:
            schema = psycopg.sql.Identifier(f"da05_{uuid4().hex}")
            cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(schema))
            cursor.execute(psycopg.sql.SQL("SET search_path TO {}").format(schema))
            for name in ("01_schema.sql", "02_contract.sql", "03_substitutions.sql", "04_views.sql"):
                load_base_file(cursor, root / "db" / name)
            cursor.execute((root / "db/migrations/0005_task_role_etc.sql").read_text())
            cursor.execute("""
                INSERT INTO teams (team_id) VALUES ('T');
                INSERT INTO initiatives (prodf_id, br_id) VALUES ('P', 'BR');
                INSERT INTO roles (role_id, canonical_name) VALUES (1, 'Developer');
                INSERT INTO tasks
                    (task_id, prodf_id, team_id, status, estimated_hh_effective)
                VALUES ('A', 'P', 'T', 'InProgress', 100);
                INSERT INTO task_role_estimates (task_id, role_id, hours) VALUES ('A', 1, 100);
                INSERT INTO task_role_spent (task_id, role_id, hours) VALUES ('A', 1, 120);
            """)

            def state() -> tuple[Decimal, Decimal, Decimal, bool, str | None]:
                cursor.execute("""
                    SELECT estimated_hours, spent_hours, remaining_hours,
                           remaining_unknown, etc_reason
                    FROM v_task_remaining_hh WHERE task_id = 'A' AND role_id = 1
                """)
                return cursor.fetchone()

            assert state() == (Decimal(100), Decimal(120), Decimal(0), True, None)
            cursor.execute("UPDATE task_role_spent SET hours = 20 WHERE task_id = 'A'")
            assert state() == (Decimal(100), Decimal(20), Decimal(0), True, None)
            cursor.execute("UPDATE task_role_spent SET hours = 120 WHERE task_id = 'A'")
            cursor.execute("""
                INSERT INTO task_role_etc (task_id, role_id, remaining_hours, reason)
                VALUES ('A', 1, 40, 'оценка после ревью')
            """)
            assert state() == (Decimal(100), Decimal(120), Decimal(40), False, "оценка после ревью")
            cursor.execute("""
                INSERT INTO task_role_etc (task_id, role_id, remaining_hours, reason)
                VALUES ('A', 1, 35, 'уточнение объёма')
            """)
            assert state() == (Decimal(100), Decimal(120), Decimal(35), False, "уточнение объёма")
    finally:
        connection.rollback()
        connection.close()
