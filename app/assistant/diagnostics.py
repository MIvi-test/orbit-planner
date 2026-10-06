"""Bounded diagnostic codes; only the emergency admin token may read them."""
from __future__ import annotations

from typing import Any
from app import auth

REASONS = frozenset({
    "invalid_model_json", "invalid_model_answer", "invalid_fact_refs",
    "missing_clarification", "unverified_evidence_reference", "invalid_fact_reference",
    "non_numeric_fact_reference", "untyped_numeric_claim", "unverified_entity_reference", "message_deadline_exceeded",
    "kb_not_indexed", "local_embedding_unavailable", "embedding_space_changed",
    "incompatible_plan_version", "invalid_answer_or_context",
})


def reason(error: Any) -> str:
    value = str(error)
    return value if value in REASONS else "invalid_answer_or_context"


def public_payload(value: Any, principal: auth.Principal) -> Any:
    if isinstance(value, list):
        return [public_payload(item, principal) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: public_payload(item, principal) for key, item in value.items()
              if key not in {"_diagnostics", "diagnostics"}}
    if principal.source == "env" and principal.role == "admin" and value.get("_diagnostics"):
        result["diagnostics"] = value["_diagnostics"]
    if isinstance(result.get("limitations"), list):
        result["limitations"] = ["Поиск по документации недоступен или ограничен."
                                 if isinstance(item, str) and item.startswith("Векторный поиск:") else item
                                 for item in result["limitations"]]
    return result
