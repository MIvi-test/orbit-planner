"""Metadata-filtered PostgreSQL FTS + exact pgvector search with RRF fusion."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app import __version__ as APP_VERSION, db
from app.assistant.knowledge import KnowledgeError, LocalEmbedder, _vector_literal
from app.planner.constants import ALGORITHM, FORMULA_VERSION

RRF_K = 60
CANDIDATES = 30


@dataclass(frozen=True)
class Hit:
    chunk_id: UUID
    document_id: UUID
    path: str
    version: str
    heading: str
    content: str
    score: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SearchResult:
    revision: UUID | None
    hits: tuple[Hit, ...]
    vector_status: str


_BASE = """FROM public.assistant_kb_revisions r
JOIN public.assistant_kb_revision_documents rd ON rd.revision_id = r.revision_id
JOIN public.assistant_kb_documents d ON d.document_id = rd.document_id
JOIN public.assistant_kb_chunks c ON c.document_id = d.document_id
WHERE r.revision_id = %s AND rd.metadata->>'access' = 'viewer'
  AND (%s = 'planning' OR rd.metadata->>'app_version' = %s)
  AND ((rd.metadata->>'compatibility' = 'current_app' AND %s = 'knowledge')
       OR (rd.metadata->>'compatibility' = 'current_formula'
           AND rd.metadata->>'formula_version' = %s
           AND rd.metadata->>'algorithm' = %s))
"""


def _row(row: dict[str, Any], score: float) -> Hit:
    return Hit(row["chunk_id"], row["document_id"], row["path"], row["version"],
               row["heading_path"], row["content"], score, row["metadata"])


def _fuse(lexical: list[dict[str, Any]], vector: list[dict[str, Any]], limit: int) -> tuple[Hit, ...]:
    scores: dict[UUID, float] = {}
    rows: dict[UUID, dict[str, Any]] = {}
    for ranked in (lexical, vector):
        for rank, row in enumerate(ranked, 1):
            chunk_id = row["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            rows[chunk_id] = row
    ordered = sorted(scores, key=lambda item: (-scores[item], rows[item]["path"],
                                                 rows[item]["heading_path"], str(item)))
    return tuple(_row(rows[item], scores[item]) for item in ordered[:limit])


def search(question: str, revision: UUID | None, *, scope: str,
           formula_version: str | None = None, algorithm: str | None = None,
           limit: int = 8) -> SearchResult:
    if revision is None:
        return SearchResult(None, (), "kb_not_indexed")
    if not isinstance(question, str) or not question.strip() or not 1 <= limit <= 10:
        raise ValueError("invalid_knowledge_query")
    if scope not in {"knowledge", "planning"}:
        raise ValueError("invalid_knowledge_scope")
    formula = formula_version if scope == "planning" else FORMULA_VERSION
    algo = algorithm if scope == "planning" else ALGORITHM
    if not formula or not algo:
        return SearchResult(revision, (), "incompatible_plan_version")
    common = (revision, scope, APP_VERSION, scope, formula, algo)
    lexical_sql = ("WITH q AS (SELECT websearch_to_tsquery('russian', %s) | "
                   "plainto_tsquery('simple', %s) AS query) "
                   "SELECT c.chunk_id, d.document_id, d.path, d.version, c.heading_path, c.content, "
                   "rd.metadata, ts_rank_cd(c.search_tsv, q.query) AS rank " + _BASE +
                   "AND c.search_tsv @@ q.query ORDER BY rank DESC, d.path, c.chunk_no LIMIT %s")
    lexical_sql = lexical_sql.replace("WHERE r.revision_id", "CROSS JOIN q WHERE r.revision_id", 1)
    with db.connection(read_only=True) as conn, conn.cursor() as cur:
        cur.execute(lexical_sql, (question, question, *common, CANDIDATES))
        lexical = cur.fetchall()
        cur.execute("SELECT s.model, s.model_digest, s.dimensions FROM public.assistant_kb_revisions r "
                    "JOIN public.assistant_kb_embedding_spaces s USING (space_id) WHERE r.revision_id = %s",
                    (revision,))
        space = cur.fetchone()
    if space is None:
        raise KnowledgeError("knowledge_revision_missing")
    vector: list[dict[str, Any]] = []
    vector_status = "ready"
    try:
        embedder = LocalEmbedder()
        if embedder.model != space["model"] or embedder.digest() != space["model_digest"]:
            vector_status = "embedding_space_changed"
        else:
            embedded = embedder.embed([question])[0]
            if len(embedded) != space["dimensions"]:
                vector_status = "embedding_space_changed"
            else:
                vector_sql = ("SELECT c.chunk_id, d.document_id, d.path, d.version, "
                              "c.heading_path, c.content, rd.metadata, "
                              "e.embedding OPERATOR(public.<=>) %s::public.vector AS distance " + _BASE +
                              "AND e.space_id = r.space_id "
                              "ORDER BY distance ASC, d.path, c.chunk_no LIMIT %s")
                # e is joined before WHERE so filters apply before ranking.
                vector_sql = vector_sql.replace(
                    "WHERE r.revision_id", "JOIN public.assistant_kb_chunk_embeddings e ON e.chunk_id = c.chunk_id "
                    "WHERE r.revision_id", 1)
                with db.connection(read_only=True) as conn, conn.cursor() as cur:
                    cur.execute(vector_sql, (_vector_literal(embedded), *common, CANDIDATES))
                    vector = cur.fetchall()
    except KnowledgeError:
        vector_status = "local_embedding_unavailable"
    return SearchResult(revision, _fuse(lexical, vector, limit), vector_status)


def context_text(result: SearchResult, *, max_chars: int = 18000) -> str:
    if not result.hits:
        return "Документные фрагменты не найдены. Не утверждай, что правило подтверждено базой знаний."
    parts = []
    used = 0
    for hit in result.hits:
        part = (f"[kb:{hit.chunk_id}] {hit.path} · {hit.heading} · версия {hit.version}\n"
                f"{hit.content}")
        if used + len(part) > max_chars:
            break
        parts.append(part)
        used += len(part)
    return "\n\n".join(parts)
