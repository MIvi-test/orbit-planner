"""Dated, confirmed additional engineer qualifications.

These records describe people; they do not authorize cross-role assignment.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app import db, ingest


def list_for_engineer(engineer_id: str) -> dict[str, Any]:
    return {
        "roles": db.query_dicts("SELECT role_id, canonical_name FROM roles ORDER BY canonical_name"),
        "qualifications": db.query_dicts(
            """SELECT q.engineer_id, q.role_id, r.canonical_name AS role_name,
                      q.valid_from, q.valid_until, q.source_text, q.confirmed_by
               FROM engineer_role_qualifications q JOIN roles r USING (role_id)
               WHERE q.engineer_id = %s ORDER BY q.valid_from DESC, q.role_id""", (engineer_id,),
        ),
    }


def confirm(engineer_id: str, role_id: int, valid_from: date, valid_until: date | None,
            source_text: str, actor: str) -> dict[str, Any]:
    engineer_id, source_text, actor = engineer_id.strip(), source_text.strip(), actor.strip()
    if not engineer_id or role_id <= 0 or not source_text or not actor:
        raise ingest.UploadError("укажите инженера, роль, источник и проверившего")
    if valid_until is not None and valid_until < valid_from:
        raise ingest.UploadError("конец квалификации раньше её начала")
    if len(source_text) > 2000 or len(actor) > 120:
        raise ingest.UploadError("слишком длинный источник или имя проверившего")
    with db.atomic_transaction():
        with db.transaction() as cur:
            cur.execute("SELECT 1 FROM engineers WHERE engineer_id = %s", (engineer_id,))
            if cur.fetchone() is None:
                raise ingest.UploadError("инженер не найден")
            cur.execute("SELECT 1 FROM roles WHERE role_id = %s", (role_id,))
            if cur.fetchone() is None:
                raise ingest.UploadError("роль не найдена")
            cur.execute(
                """INSERT INTO engineer_role_qualifications
                       (engineer_id, role_id, valid_from, valid_until, source_text, confirmed_by)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (engineer_id, role_id, valid_from) DO UPDATE SET
                       valid_until = EXCLUDED.valid_until,
                       source_text = EXCLUDED.source_text,
                       confirmed_by = EXCLUDED.confirmed_by""",
                (engineer_id, role_id, valid_from, valid_until, source_text, actor),
            )
    return {"engineer_id": engineer_id, "role_id": role_id, "valid_from": valid_from.isoformat()}
