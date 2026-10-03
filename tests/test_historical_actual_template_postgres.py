"""Шаблон исправления прошлого спринта читает историю до этого спринта."""
import csv
import io
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from app import ingest


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_past_template_includes_task_done_later_and_prior_date(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            schema = psycopg.sql.Identifier(f"da49_{uuid4().hex}")
            cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(schema))
            cursor.execute(psycopg.sql.SQL("SET search_path TO {}").format(schema))
            for name in ("01_schema.sql", "02_contract.sql"):
                cursor.execute((root / "db" / name).read_text())
            cursor.execute("""
                INSERT INTO pi_periods (pi_id, start_date, end_date, sprint_count)
                VALUES ('PI', '2026-07-01', '2026-08-11', 3);
                INSERT INTO teams (team_id) VALUES ('T');
                INSERT INTO initiatives (prodf_id, br_id) VALUES ('P', 'BR');
                INSERT INTO roles (role_id, canonical_name) VALUES (1, 'Developer');
                INSERT INTO tasks (task_id, prodf_id, team_id, status, estimated_hh_effective)
                VALUES ('A', 'P', 'T', 'Done', 10);
                INSERT INTO tasks_seed_state (task_id, status) VALUES ('A', 'ToDo');
                INSERT INTO task_role_estimates (task_id, role_id, hours) VALUES ('A', 1, 10);
                INSERT INTO actual_uploads (upload_id, pi_id, sprint_no, source_file, source_sha256)
                VALUES (1, 'PI', 1, 'one.csv', '1'), (2, 'PI', 2, 'two.csv', '2'),
                       (3, 'PI', 3, 'three.csv', '3');
                INSERT INTO task_actuals (upload_id, task_id, status, actual_start)
                VALUES (1, 'A', 'InProgress', '2026-07-03'),
                       (2, 'A', 'Done', NULL);
            """)

            def query_dicts(sql, params=None):
                cursor.execute(sql, params)
                return cursor.fetchall()

            def query_one(sql, params=None):
                cursor.execute(sql, params)
                return cursor.fetchone()

            def scalar(sql, params=None):
                cursor.execute(sql, params)
                return next(iter(cursor.fetchone().values()))

            monkeypatch.setattr(ingest.db, "query_dicts", query_dicts)
            monkeypatch.setattr(ingest.db, "query_one", query_one)
            monkeypatch.setattr(ingest.db, "scalar", scalar)

            def contents(sprint):
                name, data = ingest.actuals_template(sprint)
                return name, list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))

            name, rows = contents(1)
            assert name == "actuals_sprint_1.csv"
            assert rows[1][:3] == ["A", "ToDo", ""]
            _, rows = contents(2)
            assert rows[1][:3] == ["A", "InProgress", "2026-07-03"]
            _, rows = contents(3)
            assert len(rows) == 1  # до третьего спринта задача уже Done
            with pytest.raises(ingest.UploadError, match="шаблон доступен"):
                contents(4)
        connection.rollback()
