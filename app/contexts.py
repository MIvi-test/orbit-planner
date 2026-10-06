"""Isolated PostgreSQL schemas for PI and scenario datasets."""
from __future__ import annotations

import hashlib
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from app import db, ingest
from app.assistant import generations

ROOT = Path(__file__).resolve().parent.parent
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
BOOTSTRAP_SQL = (
    "db/01_schema.sql", "db/02_contract.sql", "db/03_substitutions.sql",
    "db/04_views.sql", "db/05_invariants.sql",
)


def list_contexts() -> dict[str, Any]:
    rows = db.query_dicts(
        "SELECT pi_id, scenario_id, schema_name, dataset_version, created_at "
        "FROM public.pi_contexts ORDER BY pi_id, scenario_id"
    )
    if not any(row["schema_name"] == "public" for row in rows):
        with db.use_schema("public"):
            seed = db.query_one(
                "SELECT p.pi_id, COALESCE(b.source_sha256, 'unloaded') AS dataset_version "
                "FROM pi_periods p LEFT JOIN LATERAL "
                "(SELECT source_sha256 FROM load_batches ORDER BY batch_id DESC LIMIT 1) b ON TRUE "
                "ORDER BY p.pi_id LIMIT 1"
            )
        if seed:
            rows.insert(0, {**seed, "scenario_id": "main", "schema_name": "public", "created_at": None})
    return {"contexts": rows}


def create(data: bytes, filename: str, pi_id: str, scenario_id: str,
           start_date: str, *, actor: str | None = None) -> dict[str, Any]:
    if not IDENTIFIER.fullmatch(pi_id) or not IDENTIFIER.fullmatch(scenario_id):
        raise ingest.UploadError("PI и сценарий: до 40 букв, цифр, дефисов или подчёркиваний")
    try:
        start = date.fromisoformat(start_date)
    except ValueError:
        raise ingest.UploadError("дата начала должна быть в формате YYYY-MM-DD") from None
    if not filename.lower().endswith((".xlsx", ".xlsm")) or not data:
        raise ingest.UploadError("загрузите непустой датасет .xlsx")
    if len(data) > ingest.MAX_UPLOAD_BYTES:
        raise ingest.UploadError("файл слишком большой")
    schema = "pi_" + hashlib.sha256(f"{pi_id}|{scenario_id}".encode()).hexdigest()[:20]
    from etl import load as etl_load

    with ingest.WRITE_LOCK, tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / ingest._safe_name(filename, "dataset.xlsx")
        source.write_bytes(data)
        try:
            seed_sql, counts, dq = etl_load.build_seed_sql(source, pi_id=pi_id, pi_start=start)
        except etl_load.DataQualityError as exc:
            raise ingest.UploadError(str(exc), exc.problems) from None
        except etl_load.DependencyGraphError as exc:
            raise ingest.UploadError("ошибка графа зависимостей", [str(exc)]) from None
        except SystemExit as exc:
            raise ingest.UploadError("структура листа не распознана", [str(exc)]) from None
        except Exception as exc:  # noqa: BLE001
            raise ingest.UploadError("датасет не прочитан", [str(exc)]) from None

        with db.atomic_transaction() as conn:
            existing = conn.execute(
                "SELECT 1 FROM public.pi_contexts WHERE pi_id = %s AND scenario_id = %s",
                (pi_id, scenario_id),
            ).fetchone()
            if existing:
                raise ingest.UploadError(f"PI {pi_id} / {scenario_id} уже существует")
            conn.execute(f"CREATE SCHEMA {schema}")
            with db.use_schema(schema):
                for file in BOOTSTRAP_SQL[:2]:
                    conn.execute(ingest._strip_transaction((ROOT / file).read_text(encoding="utf-8")))
                conn.execute(ingest._strip_transaction(seed_sql))
                conn.execute(
                    "UPDATE load_batches SET loaded_by = %s WHERE batch_id = "
                    "(SELECT MAX(batch_id) FROM load_batches)", (actor,),
                )
                digest = hashlib.sha256(data).hexdigest()
                generations.activate(pi_id, digest, scenario_id=scenario_id)
                for file in BOOTSTRAP_SQL[2:]:
                    conn.execute(ingest._strip_transaction((ROOT / file).read_text(encoding="utf-8")))
                plan = ingest.run_plan(0)
                conn.execute(
                    "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, "
                    "checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                )
                for file in sorted((ROOT / "db" / "migrations").glob("*.sql")):
                    conn.execute(
                        "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                        (file.stem, hashlib.sha256(file.read_bytes()).hexdigest()),
                    )
            conn.execute(
                "INSERT INTO public.pi_contexts "
                "(pi_id, scenario_id, schema_name, dataset_version) VALUES (%s, %s, %s, %s)",
                (pi_id, scenario_id, schema, digest),
            )
    return {"pi_id": pi_id, "scenario_id": scenario_id, "schema_name": schema,
            "dataset_version": digest, "rows": counts, "data_quality": dq, "plan": plan}
