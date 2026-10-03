"""NEW scenario APIs share the product planner and a published run."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app import db, ingest, plan_quality, planner, sensitivity, trace, workforce


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_new_scenarios_and_trace_on_product_plan(monkeypatch) -> None:
    dsn = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setattr(db, "load_config", lambda: {
        "dsn": dsn, "read_only": True, "statement_timeout_ms": 15_000,
    })
    root = Path(__file__).resolve().parents[1]
    schema = f"new_features_{uuid4().hex}"
    with psycopg.connect(dsn) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(f"SET search_path TO {schema}")
        for file in ("db/01_schema.sql", "db/02_contract.sql", "build/seed.sql",
                     "db/03_substitutions.sql", "db/04_views.sql", "db/05_invariants.sql"):
            conn.execute((root / file).read_text(encoding="utf-8"))
    try:
        with db.use_schema(schema):
            run_id = ingest.run_plan(0)["run_id"]
            inputs = planner.load_inputs()
            task = next(item for item in inputs.tasks if item.needed)
            role_id = next(iter(task.needed))

            scenarios = sensitivity.evaluate(run_id)
            assert len(scenarios["scenarios"]) == 3
            assert {row["kind"] for row in scenarios["scenarios"]} == {
                "availability_80", "etc_120", "velocity_80",
            }

            measures = workforce.evaluate(run_id, role_id, task.team_id, 1)
            assert measures["ranked_measures"]
            assert measures["ranked_measures"][0]["kind"] in {"hire", "train", "loan"}

            quality = plan_quality.evaluate(run_id)
            assert quality["run_id"] == run_id

            traced = trace.task_trace(run_id, task.task_id)
            assert traced["source_available"]
            assert traced["source_records"]
            assert traced["role_demands"]
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA {schema} CASCADE")
