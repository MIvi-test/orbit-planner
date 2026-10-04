"""Review task technology requirements and recalculate the published plan."""
from __future__ import annotations

from typing import Any

from app import db, ingest


def list_reviews() -> dict[str, Any]:
    return {
        "roles": db.query_dicts(
            """SELECT e.task_id, e.role_id, r.canonical_name AS role_name,
                      COALESCE(v.status, 'unknown') AS status, v.source_text,
                      v.reviewed_by, v.reviewed_at,
                      COALESCE(array_agg(q.skill_id ORDER BY q.skill_id)
                               FILTER (WHERE q.skill_id IS NOT NULL), ARRAY[]::int[]) AS skill_ids
               FROM task_role_estimates e JOIN roles r USING (role_id)
               LEFT JOIN task_role_skill_reviews v USING (task_id, role_id)
               LEFT JOIN task_role_skill_requirements q USING (task_id, role_id)
               GROUP BY e.task_id, e.role_id, r.canonical_name, v.status,
                        v.source_text, v.reviewed_by, v.reviewed_at
               ORDER BY e.task_id, e.role_id"""
        ),
        "skills": db.query_dicts("SELECT skill_id, name AS skill_name FROM skills ORDER BY name, skill_id"),
    }


def save_review(task_id: str, role_id: int, skill_ids: list[int], source_text: str,
                *, confirmed: bool, actor: str) -> dict[str, Any]:
    task_id, source_text, actor = task_id.strip(), source_text.strip(), actor.strip()
    if not task_id or role_id <= 0 or not source_text or len(source_text) > 2000:
        raise ingest.UploadError("укажите задачу, роль и источник требований")
    if not actor or len(actor) > 120:
        raise ingest.UploadError("укажите проверившего")
    if len(skill_ids) != len(set(skill_ids)) or any(x <= 0 for x in skill_ids):
        raise ingest.UploadError("список навыков содержит повтор или неверный идентификатор")
    with ingest.WRITE_LOCK, db.atomic_transaction():
        with db.transaction() as cur:
            cur.execute("SELECT 1 FROM task_role_estimates WHERE task_id = %s AND role_id = %s",
                        (task_id, role_id))
            if cur.fetchone() is None:
                raise ingest.UploadError("у задачи нет такой роли в смете")
            if skill_ids:
                cur.execute("SELECT skill_id FROM skills WHERE skill_id = ANY(%s)", (skill_ids,))
                if len(cur.fetchall()) != len(skill_ids):
                    raise ingest.UploadError("один из навыков не найден")
            cur.execute(
                """INSERT INTO task_role_skill_reviews
                       (task_id, role_id, status, source_text, reviewed_by, reviewed_at)
                   VALUES (%s, %s, %s, %s, %s, CASE WHEN %s THEN now() ELSE NULL END)
                   ON CONFLICT (task_id, role_id) DO UPDATE SET
                       status = EXCLUDED.status, source_text = EXCLUDED.source_text,
                       reviewed_by = EXCLUDED.reviewed_by, reviewed_at = EXCLUDED.reviewed_at""",
                (task_id, role_id, "confirmed" if confirmed else "proposed", source_text,
                 actor if confirmed else None, confirmed),
            )
            cur.execute("DELETE FROM task_role_skill_requirements WHERE task_id = %s AND role_id = %s",
                        (task_id, role_id))
            for skill_id in skill_ids:
                cur.execute(
                    """INSERT INTO task_role_skill_requirements
                           (task_id, role_id, skill_id, source_text) VALUES (%s, %s, %s, %s)""",
                    (task_id, role_id, skill_id, source_text),
                )
        pi = ingest._pi()
        plan = ingest.run_plan(min(ingest._last_sprint(pi["pi_id"]) + 1, int(pi["sprint_count"]) + 1))
    return {"task_id": task_id, "role_id": role_id, "status": "confirmed" if confirmed else "proposed", "plan": plan}
