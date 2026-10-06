"""Пользователи и журнал в PostgreSQL: схема, ограничения, переживание загрузки датасета (S-2)."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app import auth, ingest
from pg_support import load_base_file

ROOT = Path(__file__).resolve().parents[1]


def _schema(cursor) -> None:
    schema = psycopg.sql.Identifier(f"s2_{uuid4().hex}")
    cursor.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(schema))
    cursor.execute(psycopg.sql.SQL("SET search_path TO {}").format(schema))
    for name in ("01_schema.sql", "02_contract.sql"):
        load_base_file(cursor, ROOT / "db" / name)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_user_table_constraints_and_audit_roundtrip() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            _schema(cursor)
            digest = auth.hash_token("planner-token-012345678")
            cursor.execute(
                "INSERT INTO app_users (name, role, token_sha256) VALUES ('pavel', 'planner', %s)", (digest,)
            )
            cursor.execute("SELECT name, role FROM app_users WHERE token_sha256 = %s AND active", (digest,))
            assert cursor.fetchone() == ("pavel", "planner")
            for bad in (
                ("x", "superuser", digest.replace("a", "b")),   # неизвестная роль
                ("y", "viewer", "not-a-sha"),                    # не SHA-256
            ):
                with pytest.raises(psycopg.errors.CheckViolation):
                    with connection.transaction():
                        cursor.execute(
                            "INSERT INTO app_users (name, role, token_sha256) VALUES (%s, %s, %s)", bad
                        )
            with pytest.raises(psycopg.errors.UniqueViolation):
                with connection.transaction():
                    cursor.execute(
                        "INSERT INTO app_users (name, role, token_sha256) VALUES ('dup', 'viewer', %s)", (digest,)
                    )
            cursor.execute(
                "INSERT INTO audit_log (actor, role, action, outcome) VALUES ('pavel', 'planner', 'POST /api/actuals', 'ok')"
            )
            with pytest.raises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    cursor.execute(
                        "INSERT INTO audit_log (actor, role, action, outcome) VALUES ('a', 'viewer', 'x', 'maybe')"
                    )
        connection.rollback()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_dataset_reload_keeps_users_and_audit_log() -> None:
    """Загрузка датасета начинает новый цикл (TRUNCATE), но не должна стирать доступ и журнал."""
    seed = ingest._strip_transaction((ROOT / "build/seed.sql").read_text(encoding="utf-8"))
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            _schema(cursor)
            cursor.execute(
                "INSERT INTO app_users (name, role, token_sha256) VALUES ('alla', 'admin', %s)",
                (auth.hash_token("admin-token-0123456789ab"),),
            )
            cursor.execute(
                "INSERT INTO audit_log (actor, role, action, outcome) VALUES ('alla', 'admin', 'POST /api/dataset', 'ok')"
            )
            cursor.execute(seed)
            cursor.execute(seed)  # повторная загрузка — тоже
            cursor.execute("SELECT count(*) FROM app_users")
            assert cursor.fetchone() == (1,)
            cursor.execute("SELECT count(*) FROM audit_log")
            assert cursor.fetchone() == (1,)
            cursor.execute("SELECT count(*) FROM tasks")
            assert cursor.fetchone()[0] > 0  # датасет действительно загружен
        connection.rollback()
