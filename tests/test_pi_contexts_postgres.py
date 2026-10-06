"""Two PI scenarios retain independent plans, calendars and KPI snapshots."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app import contexts, db, ingest


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_pi_contexts_are_isolated(monkeypatch) -> None:
    dsn = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setattr(db, "load_config", lambda: {
        "dsn": dsn, "read_only": True, "statement_timeout_ms": 15_000,
    })
    with psycopg.connect(dsn) as conn:
        had_registry = conn.execute("SELECT to_regclass('public.pi_contexts')").fetchone()[0] is not None
        if not had_registry:
            conn.execute("""CREATE TABLE public.pi_contexts (
                pi_id TEXT NOT NULL, scenario_id TEXT NOT NULL,
                schema_name TEXT NOT NULL UNIQUE, dataset_version TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (pi_id, scenario_id))""")

    source = Path(__file__).resolve().parents[1] / "Хакатон_датасетс_правками_по_списку_вопросов_1.xlsx"
    data = source.read_bytes()
    pi_id = f"PI-{uuid4().hex[:10]}"
    made: list[str] = []
    try:
        first = contexts.create(data, source.name, pi_id, "main", "2027-01-01")
        made.append(first["schema_name"])
        second = contexts.create(data, source.name, pi_id, "stress", "2027-04-01")
        made.append(second["schema_name"])
        assert first["schema_name"] != second["schema_name"]

        with db.use_pi_context(pi_id, "main"):
            ingest.load_dataset(data, source.name)
            main = db.query_one("SELECT start_date FROM pi_periods")
            main_fund = db.query_one("SELECT factor FROM v_pi_fund_factor")
            main_kpi = db.query_one("SELECT count(*) AS n FROM kpi_snapshots")
            db.execute_write("UPDATE pi_periods SET sprint_length_days = 28")
            assert db.query_one("SELECT factor FROM v_pi_fund_factor")["factor"] != main_fund["factor"]

        with db.use_pi_context(pi_id, "stress"):
            assert str(db.query_one("SELECT start_date FROM pi_periods")["start_date"]) == "2027-04-01"
            assert db.query_one("SELECT factor FROM v_pi_fund_factor")["factor"] == main_fund["factor"]
            assert db.query_one("SELECT count(*) AS n FROM kpi_snapshots") == main_kpi
            assert db.query_one("SELECT count(*) AS n FROM plan_runs")["n"] == 1

        assert str(main["start_date"]) == "2027-01-01"
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            for schema in made:
                conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            conn.execute("DELETE FROM public.pi_contexts WHERE pi_id = %s", (pi_id,))
            if not had_registry:
                conn.execute("DROP TABLE public.pi_contexts")
