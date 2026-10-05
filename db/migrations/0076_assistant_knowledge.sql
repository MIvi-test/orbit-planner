-- RAG-06. Shared, versioned knowledge corpus and separate embedding spaces.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

ALTER TABLE public.assistant_kb_documents
    DROP CONSTRAINT IF EXISTS assistant_kb_documents_path_content_sha256_key;
CREATE UNIQUE INDEX IF NOT EXISTS assistant_kb_document_chunker_version
    ON public.assistant_kb_documents (path, content_sha256, version);

ALTER TABLE public.assistant_kb_chunks
    ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple'::regconfig, heading_path), 'A') ||
        setweight(to_tsvector('russian'::regconfig, content), 'B') ||
        setweight(to_tsvector('simple'::regconfig, content), 'C')
    ) STORED;
CREATE INDEX IF NOT EXISTS assistant_kb_chunks_fts
    ON public.assistant_kb_chunks USING gin (search_tsv);

CREATE TABLE IF NOT EXISTS public.assistant_kb_embedding_spaces (
    space_id UUID PRIMARY KEY,
    model TEXT NOT NULL,
    model_digest TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions BETWEEN 1 AND 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (model, model_digest, dimensions)
);

CREATE TABLE IF NOT EXISTS public.assistant_kb_chunk_embeddings (
    chunk_id UUID NOT NULL REFERENCES public.assistant_kb_chunks(chunk_id),
    space_id UUID NOT NULL REFERENCES public.assistant_kb_embedding_spaces(space_id),
    embedding public.vector NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, space_id),
    CHECK (public.vector_dims(embedding) BETWEEN 1 AND 2000)
);

CREATE TABLE IF NOT EXISTS public.assistant_kb_revisions (
    revision_id UUID PRIMARY KEY,
    manifest_sha256 TEXT NOT NULL,
    space_id UUID NOT NULL REFERENCES public.assistant_kb_embedding_spaces(space_id),
    app_version TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (manifest_sha256, space_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS assistant_one_active_kb_revision
    ON public.assistant_kb_revisions ((active)) WHERE active;

CREATE TABLE IF NOT EXISTS public.assistant_kb_revision_documents (
    revision_id UUID NOT NULL REFERENCES public.assistant_kb_revisions(revision_id),
    document_id UUID NOT NULL REFERENCES public.assistant_kb_documents(document_id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (revision_id, document_id)
);
CREATE INDEX IF NOT EXISTS assistant_kb_revision_document_lookup
    ON public.assistant_kb_revision_documents (document_id, revision_id);
