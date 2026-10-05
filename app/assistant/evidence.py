"""Evidence records bound to an answer and readable only by its owner."""
from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app import auth, db
from app.assistant import facts, retrieval, snapshots

MAX_MODEL_FACT_CHARS = 18000


def prepare(snapshot_id: UUID | None, question: str,
            focus: tuple[str, str] | None,
            found: retrieval.SearchResult,
            document_context: str) -> tuple[list[dict[str, Any]], str]:
    records: list[dict[str, Any]] = []
    context = ""
    if snapshot_id is not None:
        _inputs, plan, _baseline, _options = snapshots.load(snapshot_id)
        codes = {row.kpi_code for row in plan.kpis}
        mentioned = [code for code in sorted(codes, key=len, reverse=True)
                     if re.search(r"(?<![\w])" + re.escape(code) + r"(?![\w])", question, re.I)]
        if focus and focus[0] == "task":
            payload = facts.get_task_trace(snapshot_id, focus[1])
        elif focus and focus[0] == "team":
            payload = facts.get_team(snapshot_id, focus[1])
        elif len(mentioned) == 1:
            payload = facts.get_metric(snapshot_id, mentioned[0])
        else:
            payload = facts.get_overview(snapshot_id)
        evidence_id = uuid4()
        records.append({"evidence_id": evidence_id, "source_type": "snapshot",
                        "source_ref": str(snapshot_id), "payload": payload})
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(text) > MAX_MODEL_FACT_CHARS:
            context = (f"[evidence:{evidence_id}] Полный факт сохранён отдельно; "
                       "объём данных превышает контекст модели. Уточните задачу, команду или KPI.")
        else:
            context = f"[evidence:{evidence_id}] {text}"
    for hit in found.hits:
        if f"[kb:{hit.chunk_id}]" not in document_context:
            continue
        records.append({"evidence_id": uuid4(), "source_type": "document",
                        "source_ref": str(hit.chunk_id),
                        "payload": {"revision": str(found.revision), "chunk_id": str(hit.chunk_id),
                                    "document_id": str(hit.document_id), "path": hit.path,
                                    "heading": hit.heading, "version": hit.version,
                                    "content": hit.content, "metadata": hit.metadata}})
    return records, context


def check_citations(answer: dict[str, Any], records: list[dict[str, Any]]) -> None:
    allowed = {str(record["evidence_id"]) for record in records}
    allowed_kb = {record["source_ref"] for record in records
                  if record["source_type"] == "document"}
    content = answer["summary"] + "\n" + answer["explanation"]
    cited = set(re.findall(r"\[evidence:([^\]]+)\]", content))
    cited_kb = set(re.findall(r"\[kb:([^\]]+)\]", content))
    if not cited <= allowed or not cited_kb <= allowed_kb:
        raise ValueError("unverified_evidence_reference")


def save(cur: Any, *, conversation_id: UUID, message_id: UUID,
         records: list[dict[str, Any]]) -> None:
    for record in records:
        cur.execute("INSERT INTO public.assistant_evidence "
                    "(evidence_id, conversation_id, message_id, source_type, source_ref, payload) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (record["evidence_id"], conversation_id, message_id,
                     record["source_type"], record["source_ref"], Jsonb(record["payload"])))


def get(principal: auth.Principal, evidence_id: str) -> dict[str, Any]:
    from app.assistant.conversations import ChatError

    try:
        identifier = UUID(evidence_id)
    except (ValueError, TypeError) as exc:
        raise ChatError("evidence_not_found", 404) from exc
    row = db.query_one("SELECT e.evidence_id, e.source_type, e.source_ref, e.payload, e.created_at "
                       "FROM public.assistant_evidence e "
                       "JOIN public.assistant_conversations c USING (conversation_id) "
                       "WHERE e.evidence_id = %s AND c.owner_key = %s",
                       (identifier, principal.owner_key))
    if row is None:
        raise ChatError("evidence_not_found", 404)
    return {"evidence_id": str(row["evidence_id"]), "source_type": row["source_type"],
            "source_ref": row["source_ref"], "payload": row["payload"],
            "created_at": row["created_at"].isoformat()}
