"""Доска отмечает конфликт и с итоговой строкой матрицы."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from pg_support import load_base_file


@pytest.mark.xfail(
    strict=True,
    reason="B-1: тест накатывает миграцию 0024 на уже новую базовую схему, где "
    "on_critical_path переименован (0060). Исправляется вместе со штампом "
    "миграций на чистой установке (IMPLEMENTATION_PLAN.md, волна 1).",
)
@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_third_estimate_dispute_survives_migration():
    root = Path(__file__).resolve().parents[1]
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            schema = psycopg.sql.Identifier(f"da24_{uuid4().hex}")
            cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(schema))
            cursor.execute(psycopg.sql.SQL("SET search_path TO {}").format(schema))
            for name in ("01_schema.sql", "02_contract.sql", "03_substitutions.sql", "04_views.sql"):
                load_base_file(cursor, root / "db" / name)
            cursor.execute((root / "db/migrations/0024_authoritative_estimate.sql").read_text())
            cursor.execute("""
                INSERT INTO teams (team_id) VALUES ('T');
                INSERT INTO initiatives (prodf_id, br_id) VALUES ('P', 'BR');
                INSERT INTO roles (role_id, canonical_name) VALUES (1, 'Developer');
                INSERT INTO tasks
                    (task_id, prodf_id, team_id, status, estimated_hh_effective,
                     estimated_hh_declared, estimated_hh_matrix_total)
                VALUES ('A', 'P', 'T', 'ToDo', 100, 100, 120);
                INSERT INTO task_role_estimates (task_id, role_id, hours) VALUES ('A', 1, 100);
            """)
            cursor.execute("SELECT estimate_disputed FROM v_task_board WHERE task_id = 'A'")
            assert cursor.fetchone() == (True,)
            cursor.execute("UPDATE tasks SET estimated_hh_matrix_total = 100 WHERE task_id = 'A'")
            cursor.execute("SELECT estimate_disputed FROM v_task_board WHERE task_id = 'A'")
            assert cursor.fetchone() == (False,)
        connection.rollback()
