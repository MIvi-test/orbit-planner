"""Immutable advice with freshness derived from context and published runs."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app import auth, db
from app.assistant import conversations
from app.planner.constants import ALGORITHM, FORMULA_VERSION


def list_for_conversation(principal: auth.Principal, conversation_id: str) -> dict[str, Any]:
    cid = conversations._uuid(conversation_id)
    with db.connection(read_only=True) as conn, conn.cursor() as cur:
        context = conversations._joined(cur, cid, principal.owner_key)
        cur.execute("SELECT r.recommendation_id, r.text, r.basis_status, r.freshness, "
                    "r.supersedes, r.scenario_result_id, r.context_revision, r.created_at, "
                    "cr.generation_id, cr.run_id, g.active AS generation_active, "
                    "s.engine_version "
                    "FROM public.assistant_recommendations r "
                    "JOIN public.assistant_context_revisions cr ON cr.conversation_id = r.conversation_id "
                    "AND cr.revision = r.context_revision "
                    "LEFT JOIN public.assistant_dataset_generations g ON g.generation_id = cr.generation_id "
                    "LEFT JOIN public.assistant_scenario_results s ON s.scenario_result_id = r.scenario_result_id "
                    "WHERE r.conversation_id = %s ORDER BY r.created_at DESC, r.recommendation_id DESC",
                    (cid,))
        rows = cur.fetchall()
        items = []
        for row in rows:
            reasons: list[str] = []
            freshness = row["freshness"]
            if freshness != "superseded":
                if row["context_revision"] != context["revision"]:
                    reasons.append("context_revision_changed")
                if row["generation_id"] and not row["generation_active"]:
                    reasons.append("dataset_generation_changed")
                if (row["engine_version"] and
                        row["engine_version"] != ALGORITHM + "/" + FORMULA_VERSION):
                    reasons.append("planner_rules_changed")
                if row["generation_id"] and row["run_id"] is not None:
                    cur.execute("SELECT EXISTS(SELECT 1 FROM public.assistant_input_snapshots "
                                "WHERE generation_id = %s AND run_id > %s) AS newer",
                                (row["generation_id"], row["run_id"]))
                    if cur.fetchone()["newer"]:
                        reasons.append("newer_run_available")
                if reasons:
                    freshness = "stale"
            cur.execute("SELECT evidence_id FROM public.assistant_evidence "
                        "WHERE conversation_id = %s AND source_type = 'scenario' AND source_ref = %s "
                        "ORDER BY created_at", (cid, str(row["scenario_result_id"])))
            evidence_ids = [str(item["evidence_id"]) for item in cur.fetchall()]
            items.append({"recommendation_id": str(row["recommendation_id"]),
                          "text": row["text"], "basis_status": row["basis_status"],
                          "freshness": freshness, "stale_reasons": reasons,
                          "evidence_ids": evidence_ids,
                          "scenario_result_id": str(row["scenario_result_id"]) if row["scenario_result_id"] else None,
                          "supersedes": str(row["supersedes"]) if row["supersedes"] else None,
                          "context_revision": row["context_revision"],
                          "created_at": row["created_at"].isoformat()})
    return {"recommendations": items}


def validate_supersedes(cur: Any, cid: UUID, alternatives: list[dict[str, Any]]) -> None:
    for item in alternatives:
        if "supersedes" not in item:
            continue
        prior = conversations._uuid(item["supersedes"])
        cur.execute("SELECT 1 FROM public.assistant_recommendations "
                    "WHERE recommendation_id = %s AND conversation_id = %s", (prior, cid))
        if cur.fetchone() is None:
            raise conversations.ChatError("recommendation_not_found", 404)
