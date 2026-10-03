"""Apply checked, transactional PostgreSQL migrations.

Run in deployment after the database is healthy:
    docker compose run --rm migrate

The initial schema and seed remain Docker-init files for a fresh demo volume.
All changes made after that bootstrap belong in db/migrations/NNNN_description.sql.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "db" / "migrations"
MIGRATION_NAME = re.compile(r"^(\d{4}_[a-z0-9_]+)\.sql$")
LOCK_KEY = 5_427_001


def discover() -> list[tuple[str, Path]]:
    migrations: list[tuple[str, Path]] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        match = MIGRATION_NAME.fullmatch(path.name)
        if not match:
            raise RuntimeError(f"invalid migration name: {path.name}")
        migrations.append((match.group(1), path))
    if not migrations:
        raise RuntimeError(f"no migrations found in {MIGRATIONS}")
    return migrations


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    dsn = os.environ.get("PI_PLANNER_DSN", "").strip()
    if not dsn:
        raise RuntimeError("PI_PLANNER_DSN is required for migrations")

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
            try:
                migrations = discover()
                cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
                has_history = cur.fetchone()[0]
                cur.execute("SELECT to_regclass('public.pi_contexts') IS NOT NULL")
                fresh_snapshot = not has_history and cur.fetchone()[0]

                def apply_schema(schema: str) -> None:
                    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
                        raise RuntimeError(f"invalid PI schema: {schema}")
                    cur.execute(f"SET search_path TO {schema}")
                    cur.execute(
                        """CREATE TABLE IF NOT EXISTS schema_migrations (
                            version TEXT PRIMARY KEY,
                            checksum TEXT NOT NULL,
                            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        )"""
                    )
                    if schema == "public" and fresh_snapshot:
                        # Docker init uses the current schema snapshot. Historical
                        # deltas belong to older databases and may no longer match it.
                        for version, path in migrations:
                            if version >= "0065_pi_contexts":
                                break
                            cur.execute(
                                "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                                (version, checksum(path)),
                            )
                    for version, path in migrations:
                        digest = checksum(path)
                        cur.execute(
                            "SELECT checksum FROM schema_migrations WHERE version = %s", (version,)
                        )
                        applied = cur.fetchone()
                        if applied:
                            if applied[0] != digest:
                                raise RuntimeError(
                                    f"migration {version} in {schema} changed after application; "
                                    "create a new migration instead"
                                )
                            continue
                        with conn.transaction():
                            cur.execute(path.read_text(encoding="utf-8"))
                            cur.execute(
                                "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                                (version, digest),
                            )
                        print(f"[migrate] {schema}: applied {version}")

                apply_schema("public")
                cur.execute(
                    "SELECT schema_name FROM public.pi_contexts "
                    "WHERE schema_name <> 'public' ORDER BY schema_name"
                )
                for (schema,) in cur.fetchall():
                    apply_schema(schema)
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # deployment logs need one actionable error line
        print(f"[migrate] FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
