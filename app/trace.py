"""Read a decision together with the source and capacity snapshot behind it."""
from __future__ import annotations

from typing import Any

from app import db


class TraceUnavailable(ValueError):
    pass


def task_trace(run_id: int, task_id: str) -> dict[str, Any]:
    with db.connection(read_only=True) as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")

        def one(sql: str, params: tuple) -> dict | None:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

        def many(sql: str, params: tuple) -> list[dict]:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

        run = one(
            "SELECT run_id, pi_id, as_of_sprint, algorithm, params, actuals_upload_id, created_at "
            "FROM plan_runs WHERE run_id = %s", (run_id,),
        )
        if run is None:
            raise TraceUnavailable(f"прогон {run_id} не найден")
        state = one("SELECT * FROM task_state WHERE run_id = %s AND task_id = %s",
                    (run_id, task_id))
        if state is None:
            raise TraceUnavailable(f"задача {task_id} отсутствует в снимке прогона {run_id}")
        decision = one(
            "SELECT * FROM plan_task_schedule WHERE run_id = %s AND task_id = %s",
            (run_id, task_id),
        )
        role_demands = many(
            "SELECT d.role_id, r.canonical_name AS role_name, d.needed_hours "
            "FROM plan_role_demand_snapshot d JOIN roles r USING (role_id) "
            "WHERE d.run_id = %s AND d.task_id = %s ORDER BY d.role_id",
            (run_id, task_id),
        )
        assignments = many(
            "SELECT a.sprint_no, a.role_id, a.engineer_id, a.home_team_id, "
            "a.serving_team_id, a.hours, a.work_hours, c.available_hours "
            "FROM plan_assignments a LEFT JOIN plan_capacity_snapshot c "
            "ON c.run_id = a.run_id AND c.engineer_id = a.engineer_id "
            "AND c.team_id = a.home_team_id AND c.sprint_no = a.sprint_no "
            "WHERE a.run_id = %s AND a.task_id = %s "
            "ORDER BY a.sprint_no, a.role_id, a.engineer_id",
            (run_id, task_id),
        )
        bound = one(
            "SELECT earliest_start_sprint FROM plan_dependency_bounds "
            "WHERE run_id = %s AND task_id = %s", (run_id, task_id),
        )
        source_sha = (run["params"] or {}).get("source_sha256")
        batch = one(
            "SELECT batch_id, source_file, source_sha256, config_sha256, etl_version "
            "FROM load_batches WHERE source_sha256 = %s ORDER BY batch_id DESC LIMIT 1",
            (source_sha,),
        ) if source_sha else None
        sources: list[dict] = []
        if batch:
            sources = many(
                "SELECT entity, entity_id, field_name, source_sheet, source_cell, "
                "raw_value, normalized_value, rule_version FROM source_provenance "
                "WHERE batch_id = %s AND ((entity = 'tasks' AND entity_id = %s) "
                "OR (entity = 'task_role_estimates' AND entity_id LIKE %s) "
                "OR (entity = 'engineers' AND entity_id = ANY(%s))) "
                "ORDER BY entity, entity_id, field_name, source_cell",
                (batch["batch_id"], task_id, task_id + ":%",
                 [row["engineer_id"] for row in assignments]),
            )
        return {
            "run": run, "state": state, "decision": decision,
            "role_demands": role_demands, "assignments": assignments,
            "dependency_bound": bound,
            "source_batch": batch,
            "source_available": batch is not None,
            "source_records": sources,
        }
