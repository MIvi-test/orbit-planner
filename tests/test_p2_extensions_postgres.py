"""Full-schema checks for editable skills, sprint availability and upload revisions."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app import availability, db, ingest, planner, skill_review


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="нужен PostgreSQL")
def test_p2_changes_share_the_live_plan_and_keep_upload_history(monkeypatch) -> None:
    dsn = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setattr(db, "load_config", lambda: {
        "dsn": dsn, "read_only": True, "statement_timeout_ms": 15_000,
    })
    root = Path(__file__).resolve().parents[1]
    schema = f"p2_extensions_{uuid4().hex}"
    with psycopg.connect(dsn) as connection:
        connection.execute(f"CREATE SCHEMA {schema}")
        connection.execute(f"SET search_path TO {schema}")
        for file in ("db/01_schema.sql", "db/02_contract.sql", "build/seed.sql",
                     "db/03_substitutions.sql", "db/04_views.sql", "db/05_invariants.sql"):
            connection.execute((root / file).read_text(encoding="utf-8"))
    try:
        with db.use_schema(schema):
            ingest.run_plan(0)
            first_orbit = db.query_one(
                "SELECT engineer_id, team_id FROM engineer_orbits ORDER BY engineer_id LIMIT 1"
            )
            changed = availability.set_rate(first_orbit["engineer_id"], first_orbit["team_id"],
                                            1, Decimal(0), "подтверждённый отпуск")
            assert changed["plan"]["run_id"] > 0
            capacity = db.query_dicts(
                "SELECT sprint_no, hours_own FROM v_satellite_capacity "
                "WHERE engineer_id = %s AND team_id = %s AND sprint_no IN (1, 2) ORDER BY sprint_no",
                (first_orbit["engineer_id"], first_orbit["team_id"]),
            )
            assert capacity[0]["hours_own"] == 0
            assert capacity[1]["hours_own"] > 0
            assert planner.load_inputs().sprint_orbit_rates[
                (first_orbit["engineer_id"], first_orbit["team_id"], 1)] == 0

            role = db.query_one("SELECT task_id, role_id FROM task_role_estimates ORDER BY task_id LIMIT 1")
            reviewed = skill_review.save_review(role["task_id"], role["role_id"], [],
                                                "карточка задачи: ограничений нет",
                                                confirmed=True, actor="reviewer")
            assert reviewed["plan"]["run_id"] > changed["plan"]["run_id"]
            assert db.query_one("SELECT status FROM task_role_skill_reviews WHERE task_id = %s AND role_id = %s",
                                (role["task_id"], role["role_id"]))["status"] == "confirmed"
            review_row = next(item for item in skill_review.list_reviews()["roles"]
                              if item["task_id"] == role["task_id"] and item["role_id"] == role["role_id"])
            assert review_row["status"] == "confirmed"
            assert review_row["skill_ids"] == []

            data = (root / "demo/actuals_sprint_1.csv").read_bytes()
            first = ingest.load_actuals(data, "actuals_sprint_1.csv", 1,
                                        confirm_complete=True, idempotency_key="p2-sprint-1")
            repeated = ingest.load_actuals(data, "actuals_sprint_1.csv", 1,
                                           confirm_complete=True, idempotency_key="p2-sprint-1")
            assert repeated["replayed"] is True
            assert repeated["upload_id"] == first["upload_id"]
            assert db.scalar("SELECT COUNT(*) FROM actual_uploads") == 1
            replacement = ingest.load_actuals(data, "actuals_sprint_1.csv", 1,
                                              confirm_complete=True, idempotency_key="p2-sprint-1-replace")
            revisions = db.query_dicts(
                "SELECT revision_id, superseded_by, plan_snapshot FROM upload_revisions "
                "WHERE kind = 'actuals' ORDER BY revision_id"
            )
            assert len(revisions) == 2
            assert revisions[0]["superseded_by"] == replacement["revision_id"]
            assert revisions[0]["plan_snapshot"]["kpis"]
            assert revisions[1]["superseded_by"] is None
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(f"DROP SCHEMA {schema} CASCADE")
