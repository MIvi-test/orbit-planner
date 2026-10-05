"""Stable dataset generations outside the ETL-reset PI schema."""
from __future__ import annotations

from uuid import UUID, uuid4

from app import db


def activate(pi_id: str, source_sha256: str, *, scenario_id: str | None = None) -> UUID:
    """Switch generation within the caller's dataset upload transaction."""
    schema = db.current_schema()
    if scenario_id is None:
        row = db.query_one(
            "SELECT scenario_id FROM public.pi_contexts WHERE schema_name = %s", (schema,)
        )
        scenario_id = str(row["scenario_id"]) if row else "main"
    generation_id = uuid4()
    with db.transaction(operation="assistant_generation_activate") as cur:
        cur.execute(
            "UPDATE public.assistant_dataset_generations SET active = false "
            "WHERE schema_name = %s AND active", (schema,),
        )
        cur.execute(
            "INSERT INTO public.assistant_dataset_generations "
            "(generation_id, schema_name, pi_id, scenario_id, source_sha256) "
            "VALUES (%s, %s, %s, %s, %s)",
            (generation_id, schema, pi_id, scenario_id, source_sha256),
        )
    return generation_id
