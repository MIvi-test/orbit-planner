"""Review history for individual ETL findings."""
from __future__ import annotations

from app import db
from app.ingest import UploadError

DECISIONS = frozenset({"acknowledged", "resolved", "reopened"})


def review_issue(issue_id: int, decision: str, reviewer: str, note: str) -> dict[str, int | str]:
    if issue_id <= 0 or decision not in DECISIONS:
        raise UploadError("неверный номер находки или решение")
    reviewer, note = reviewer.strip(), note.strip()
    if not reviewer or not note or len(reviewer) > 120 or len(note) > 2000:
        raise UploadError("укажите автора и пояснение решения")
    with db.atomic_transaction():
        with db.transaction() as cur:
            cur.execute("SELECT issue_id FROM dq_issues WHERE issue_id = %s", (issue_id,))
            if cur.fetchone() is None:
                raise UploadError(f"находка {issue_id} не найдена")
            cur.execute(
                "INSERT INTO dq_issue_reviews (issue_id, decision, reviewer, note) "
                "VALUES (%s, %s, %s, %s) RETURNING review_id",
                (issue_id, decision, reviewer, note),
            )
            review_id = int(cur.fetchone()["review_id"])
    return {"issue_id": issue_id, "review_id": review_id, "decision": decision}
