"""Approved Markdown knowledge corpus with atomic, reusable revisions."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app import __version__ as APP_VERSION, auth, db
from app.planner.constants import ALGORITHM, FORMULA_VERSION

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "assistant_kb_manifest.json"
MAX_SOURCE_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
CHUNK_TARGET = 2800
CHUNK_MAX = 4000
CHUNKER_VERSION = 1


class KnowledgeError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    path: str
    text: str
    sha256: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class Chunk:
    heading: str
    text: str


def _approved_sources() -> list[Source]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("manifest_version") != 1 or not isinstance(data.get("documents"), list):
        raise KnowledgeError("invalid_knowledge_manifest")
    sources: list[Source] = []
    seen: set[str] = set()
    for item in data["documents"]:
        path = item.get("path")
        if (not isinstance(path, str) or not path.startswith("docs/") or ".." in Path(path).parts
                or path in seen or item.get("access") != "viewer"
                or item.get("compatibility") not in {"current_app", "current_formula"}):
            raise KnowledgeError("unapproved_knowledge_source")
        seen.add(path)
        file = ROOT / path
        if (file.is_symlink() or not file.resolve().is_relative_to(ROOT.resolve())
                or not file.is_file() or file.stat().st_size > MAX_SOURCE_BYTES):
            raise KnowledgeError("knowledge_source_unavailable")
        text = file.read_text(encoding="utf-8")
        selected = _selected_sections(text, item.get("sections"))
        if not selected.strip():
            raise KnowledgeError("empty_knowledge_source")
        metadata = {"kind": str(item["kind"]), "access": "viewer",
                    "compatibility": item["compatibility"], "app_version": APP_VERSION,
                    "formula_version": FORMULA_VERSION if item["compatibility"] == "current_formula" else "",
                    "algorithm": ALGORITHM if item["compatibility"] == "current_formula" else ""}
        sources.append(Source(path, selected, hashlib.sha256(selected.encode()).hexdigest(), metadata))
    if not sources:
        raise KnowledgeError("empty_knowledge_manifest")
    return sources


def _selected_sections(text: str, sections: Any) -> str:
    if sections is None:
        return text
    if not isinstance(sections, list) or not sections or any(not isinstance(s, str) for s in sections):
        raise KnowledgeError("invalid_knowledge_sections")
    requested = set(sections)
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines(keepends=True):
        match = re.match(r"^##\s+(ADR-\d+)\b", line)
        if match:
            current = match.group(1)
            if current in requested:
                found[current] = []
        if current in requested:
            found[current].append(line)
    if set(found) != requested:
        raise KnowledgeError("knowledge_section_missing")
    return "\n".join("".join(found[section]).strip() for section in sections) + "\n"


def chunk_markdown(text: str, *, target: int = CHUNK_TARGET, maximum: int = CHUNK_MAX) -> list[Chunk]:
    """Split at headings and paragraphs; keep small tables and formula blocks whole."""
    if target < 200 or maximum < target:
        raise ValueError("invalid_chunk_limits")
    headings: list[str] = []
    sections: list[tuple[str, str]] = []
    current: list[str] = []

    def flush_section() -> None:
        if current and "".join(current).strip():
            sections.append((" / ".join(headings), "".join(current).strip()))

    for line in text.splitlines(keepends=True):
        match = re.match(r"^(#{1,4})\s+(.+)", line)
        if match:
            flush_section()
            level = len(match.group(1))
            headings[:] = headings[:level - 1] + [match.group(2).strip()]
            current = [line]
        else:
            current.append(line)
    flush_section()
    chunks: list[Chunk] = []
    for heading, section in sections:
        blocks = re.split(r"\n\s*\n", section)
        pending = ""
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            if pending and len(pending) + len(block) + 2 > maximum:
                chunks.append(Chunk(heading, pending))
                pending = ""
            if len(block) > maximum:
                if pending:
                    chunks.append(Chunk(heading, pending))
                    pending = ""
                for start in range(0, len(block), maximum):
                    chunks.append(Chunk(heading, block[start:start + maximum]))
            else:
                pending = (pending + "\n\n" + block).strip()
                if len(pending) >= target:
                    chunks.append(Chunk(heading, pending))
                    pending = ""
        if pending:
            chunks.append(Chunk(heading, pending))
    return chunks


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


class LocalEmbedder:
    def __init__(self, *, timeout: float = 60) -> None:
        self.base_url = os.environ.get("PI_PLANNER_KB_EMBED_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.environ.get("PI_PLANNER_KB_EMBED_MODEL", "embeddinggemma").strip()
        parsed = urllib.parse.urlsplit(self.base_url)
        allowed = {"127.0.0.1", "localhost", "::1", "ollama"}
        allowed.update(x.strip().lower() for x in
                       os.environ.get("PI_PLANNER_INTERNAL_LLM_HOSTS", "").split(",") if x.strip())
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.hostname.lower() not in allowed
                or parsed.username or parsed.password or parsed.query or parsed.fragment or not self.model):
            raise KnowledgeError("invalid_local_embedding_endpoint")
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _json(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        request = urllib.request.Request(self.base_url + path, body,
                                         {"Content-Type": "application/json"},
                                         method="POST" if payload is not None else "GET")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise KnowledgeError("local_embedding_unavailable") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise KnowledgeError("embedding_response_too_large")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise KnowledgeError("invalid_embedding_response") from exc
        if not isinstance(value, dict):
            raise KnowledgeError("invalid_embedding_response")
        return value

    def digest(self) -> str:
        models = self._json("/api/tags").get("models", [])
        digest = next((item.get("digest") for item in models
                       if item.get("name") in {self.model, self.model + ":latest"}), None)
        if not isinstance(digest, str) or not digest:
            raise KnowledgeError("embedding_model_not_installed")
        return digest

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or len(texts) > 8:
            raise KnowledgeError("invalid_embedding_batch")
        value = self._json("/api/embed", {"model": self.model, "input": texts, "truncate": False})
        vectors = value.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise KnowledgeError("invalid_embedding_response")
        dimensions = len(vectors[0]) if isinstance(vectors[0], list) else 0
        if not 1 <= dimensions <= 2000:
            raise KnowledgeError("invalid_embedding_dimensions")
        for vector in vectors:
            if (not isinstance(vector, list) or len(vector) != dimensions
                    or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector)):
                raise KnowledgeError("invalid_embedding_response")
        return [[float(x) for x in vector] for vector in vectors]


def active_revision() -> UUID | None:
    row = db.query_one("SELECT revision_id FROM public.assistant_kb_revisions WHERE active")
    return row["revision_id"] if row else None


def status() -> dict[str, Any]:
    row = db.query_one("SELECT r.revision_id, s.model, s.model_digest, s.dimensions, "
                       "(SELECT COUNT(*) FROM public.assistant_kb_revision_documents d "
                       "WHERE d.revision_id = r.revision_id) AS documents "
                       "FROM public.assistant_kb_revisions r "
                       "JOIN public.assistant_kb_embedding_spaces s USING (space_id) WHERE r.active")
    return {"revision": str(row["revision_id"]) if row else None,
            "documents": row["documents"] if row else 0,
            "embedding_model": row["model"] if row else None,
            "embedding_digest": row["model_digest"] if row else None,
            "dimensions": row["dimensions"] if row else None}


def enqueue(principal: auth.Principal) -> dict[str, str]:
    if not principal.allows("admin"):
        raise KnowledgeError("admin_required")
    job_id = uuid4()
    with db.transaction(operation="assistant_kb_enqueue") as cur:
        cur.execute("SELECT pg_advisory_xact_lock(90340214)")
        cur.execute("SELECT job_id, status, owner_key FROM public.assistant_jobs WHERE kind = 'kb_reindex' "
                    "AND status IN ('queued', 'running') ORDER BY created_at LIMIT 1")
        existing = cur.fetchone()
        if existing:
            if existing["owner_key"] != principal.owner_key:
                raise KnowledgeError("knowledge_reindex_busy")
            return {"job_id": str(existing["job_id"]), "status": existing["status"]}
        cur.execute("INSERT INTO public.assistant_jobs "
                    "(job_id, owner_key, kind, status, idempotency_key, request_sha256, input_payload, deadline_at) "
                    "VALUES (%s, %s, 'kb_reindex', 'queued', %s, %s, %s, now() + interval '30 minutes')",
                    (job_id, principal.owner_key, "kb:" + str(job_id), "kb-reindex",
                     Jsonb({"principal": {"name": principal.name, "role": principal.role,
                                           "source": principal.source, "user_id": principal.user_id}})))
    return {"job_id": str(job_id), "status": "queued"}


def reindex(*, job_id: UUID | None = None, attempt_count: int | None = None) -> dict[str, Any]:
    """Prepare all network-dependent work before the publication transaction."""
    sources = _approved_sources()
    try:
        chunk_target = int(os.environ.get("PI_PLANNER_KB_CHUNK_TARGET", str(CHUNK_TARGET)))
        chunk_max = int(os.environ.get("PI_PLANNER_KB_CHUNK_MAX", str(CHUNK_MAX)))
    except ValueError as exc:
        raise KnowledgeError("invalid_chunk_limits") from exc
    if not 200 <= chunk_target <= chunk_max <= 8000:
        raise KnowledgeError("invalid_chunk_limits")
    embedder = LocalEmbedder()
    digest = embedder.digest()
    prepared: list[tuple[Source, list[Chunk], list[list[float]]]] = []
    dimensions: int | None = None
    for source in sources:
        chunks = chunk_markdown(source.text, target=chunk_target, maximum=chunk_max)
        if not chunks:
            raise KnowledgeError("empty_knowledge_chunks")
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), 8):
            batch = chunks[start:start + 8]
            vectors.extend(embedder.embed([source.path + " / " + chunk.heading + "\n" + chunk.text
                                           for chunk in batch]))
        if dimensions is None:
            dimensions = len(vectors[0])
        if any(len(vector) != dimensions for vector in vectors):
            raise KnowledgeError("embedding_dimensions_changed")
        prepared.append((source, chunks, vectors))
    if embedder.digest() != digest:
        raise KnowledgeError("embedding_model_changed_during_indexing")
    manifest_payload = [{"path": source.path, "sha256": source.sha256,
                         "metadata": source.metadata} for source in sources]
    manifest_payload.append({"chunker": CHUNKER_VERSION, "chunk_target": chunk_target,
                             "chunk_max": chunk_max, "model": embedder.model,
                             "digest": digest, "dimensions": dimensions})
    manifest_hash = hashlib.sha256(json.dumps(manifest_payload, sort_keys=True).encode()).hexdigest()
    with db.transaction(operation="assistant_kb_publish") as cur:
        cur.execute("SELECT pg_advisory_xact_lock(90340213)")
        if job_id is not None:
            cur.execute("SELECT 1 FROM public.assistant_jobs WHERE job_id = %s AND status = 'running' "
                        "AND attempt_count = %s AND lease_until > now() AND deadline_at > now()",
                        (job_id, attempt_count))
            if cur.fetchone() is None:
                raise KnowledgeError("index_job_no_longer_active")
        cur.execute("INSERT INTO public.assistant_kb_embedding_spaces "
                    "(space_id, model, model_digest, dimensions) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (model, model_digest, dimensions) DO NOTHING",
                    (uuid4(), embedder.model, digest, dimensions))
        cur.execute("SELECT space_id FROM public.assistant_kb_embedding_spaces "
                    "WHERE model = %s AND model_digest = %s AND dimensions = %s",
                    (embedder.model, digest, dimensions))
        space_id = cur.fetchone()["space_id"]
        cur.execute("SELECT revision_id FROM public.assistant_kb_revisions "
                    "WHERE manifest_sha256 = %s AND space_id = %s", (manifest_hash, space_id))
        old = cur.fetchone()
        if old is not None:
            revision_id = old["revision_id"]
        else:
            revision_id = uuid4()
            cur.execute("INSERT INTO public.assistant_kb_revisions "
                        "(revision_id, manifest_sha256, space_id, app_version) VALUES (%s, %s, %s, %s)",
                        (revision_id, manifest_hash, space_id, APP_VERSION))
            for source, chunks, vectors in prepared:
                document_version = f"chunker-{CHUNKER_VERSION}-{chunk_target}-{chunk_max}:{source.sha256[:12]}"
                cur.execute("INSERT INTO public.assistant_kb_documents "
                            "(document_id, path, content_sha256, version, status, metadata) "
                            "VALUES (%s, %s, %s, %s, 'active', %s) "
                            "ON CONFLICT (path, content_sha256, version) DO NOTHING",
                            (uuid4(), source.path, source.sha256, document_version,
                             Jsonb({"kind": source.metadata["kind"]})))
                cur.execute("SELECT document_id FROM public.assistant_kb_documents "
                            "WHERE path = %s AND content_sha256 = %s AND version = %s",
                            (source.path, source.sha256, document_version))
                document_id = cur.fetchone()["document_id"]
                for number, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                    cur.execute("INSERT INTO public.assistant_kb_chunks "
                                "(chunk_id, document_id, chunk_no, heading_path, content, embedding_model) "
                                "VALUES (%s, %s, %s, %s, %s, %s) "
                                "ON CONFLICT (document_id, chunk_no) DO NOTHING",
                                (uuid4(), document_id, number, chunk.heading, chunk.text, embedder.model))
                    cur.execute("SELECT chunk_id, heading_path, content FROM public.assistant_kb_chunks "
                                "WHERE document_id = %s AND chunk_no = %s", (document_id, number))
                    stored = cur.fetchone()
                    if stored["heading_path"] != chunk.heading or stored["content"] != chunk.text:
                        raise KnowledgeError("chunker_version_conflict")
                    cur.execute("INSERT INTO public.assistant_kb_chunk_embeddings "
                                "(chunk_id, space_id, embedding) VALUES (%s, %s, %s::public.vector) "
                                "ON CONFLICT (chunk_id, space_id) DO NOTHING",
                                (stored["chunk_id"], space_id, _vector_literal(vector)))
                cur.execute("INSERT INTO public.assistant_kb_revision_documents "
                            "(revision_id, document_id, metadata) VALUES (%s, %s, %s)",
                            (revision_id, document_id, Jsonb(source.metadata)))
        cur.execute("UPDATE public.assistant_kb_revisions SET active = FALSE WHERE active")
        cur.execute("UPDATE public.assistant_kb_revisions SET active = TRUE WHERE revision_id = %s", (revision_id,))
        cur.execute("UPDATE public.assistant_kb_documents SET status = 'retired' "
                    "WHERE document_id NOT IN (SELECT document_id FROM public.assistant_kb_revision_documents "
                    "WHERE revision_id = %s)", (revision_id,))
        cur.execute("UPDATE public.assistant_kb_documents SET status = 'active' "
                    "WHERE document_id IN (SELECT document_id FROM public.assistant_kb_revision_documents "
                    "WHERE revision_id = %s)", (revision_id,))
        result = {"revision": str(revision_id), "documents": len(sources),
                  "embedding_model": embedder.model, "dimensions": dimensions}
        if job_id is not None:
            cur.execute("UPDATE public.assistant_jobs SET status = 'completed', "
                        "result_payload = %s, lease_until = NULL, updated_at = now() "
                        "WHERE job_id = %s AND status = 'running' AND attempt_count = %s "
                        "AND lease_until > now() AND deadline_at > now() RETURNING job_id",
                        (Jsonb(result), job_id, attempt_count))
            if cur.fetchone() is None:
                raise KnowledgeError("index_job_no_longer_active")
    return result


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"
