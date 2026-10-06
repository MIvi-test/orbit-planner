-- RAG-01. Global assistant state survives PI dataset TRUNCATE and run_id reuse.
-- Intentionally no FK to mutable per-PI tables or app_users: both are recreated
-- by bootstrap, while historical conversation ownership remains stable.
CREATE TABLE IF NOT EXISTS public.assistant_dataset_generations (
    generation_id UUID PRIMARY KEY,
    schema_name TEXT NOT NULL,
    pi_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX IF NOT EXISTS assistant_one_active_generation
    ON public.assistant_dataset_generations (schema_name) WHERE active;

-- Existing installations already have a dataset but no assistant generation.
INSERT INTO public.assistant_dataset_generations
    (generation_id, schema_name, pi_id, scenario_id, source_sha256)
SELECT gen_random_uuid(), current_schema(), p.pi_id,
       COALESCE((SELECT c.scenario_id FROM public.pi_contexts c
                 WHERE c.schema_name = current_schema() LIMIT 1), 'main'),
       COALESCE((SELECT b.source_sha256 FROM load_batches b
                 ORDER BY b.batch_id DESC LIMIT 1), 'unloaded')
FROM pi_periods p
WHERE NOT EXISTS (SELECT 1 FROM public.assistant_dataset_generations g
                  WHERE g.schema_name = current_schema() AND g.active)
ORDER BY p.pi_id LIMIT 1;

CREATE TABLE IF NOT EXISTS public.assistant_input_snapshots (
    snapshot_id UUID PRIMARY KEY,
    generation_id UUID NOT NULL REFERENCES public.assistant_dataset_generations(generation_id),
    run_id BIGINT NOT NULL,
    serialization_version INTEGER NOT NULL,
    input_payload JSONB NOT NULL,
    plan_payload JSONB NOT NULL,
    input_sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (generation_id, run_id)
);

CREATE TABLE IF NOT EXISTS public.assistant_prompt_versions (
    prompt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('default', 'user')),
    owner_key TEXT,
    version INTEGER NOT NULL CHECK (version > 0),
    content TEXT NOT NULL CHECK (length(btrim(content)) > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((scope = 'default' AND owner_key IS NULL) OR (scope = 'user' AND owner_key IS NOT NULL)),
    UNIQUE (scope, owner_key, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS assistant_one_default_prompt
    ON public.assistant_prompt_versions (scope) WHERE scope = 'default' AND active;
CREATE UNIQUE INDEX IF NOT EXISTS assistant_one_user_prompt
    ON public.assistant_prompt_versions (owner_key) WHERE scope = 'user' AND active;

CREATE TABLE IF NOT EXISTS public.assistant_provider_profiles (
    profile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    protocol TEXT NOT NULL CHECK (protocol IN ('gemini', 'ollama', 'openai_compatible')),
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    auth_type TEXT NOT NULL CHECK (auth_type IN ('bearer', 'header', 'none')),
    auth_header_name TEXT,
    api_key_ref TEXT,
    network_scope TEXT NOT NULL CHECK (network_scope IN ('internal', 'external')),
    capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
    limits JSONB NOT NULL DEFAULT '{}'::jsonb,
    min_role TEXT NOT NULL DEFAULT 'viewer' CHECK (min_role IN ('viewer', 'planner', 'admin')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (auth_type = 'none' OR api_key_ref IS NOT NULL),
    UNIQUE (name, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS assistant_one_active_provider_profile
    ON public.assistant_provider_profiles (name) WHERE active;

CREATE TABLE IF NOT EXISTS public.assistant_conversations (
    conversation_id UUID PRIMARY KEY,
    owner_key TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    profile_id BIGINT REFERENCES public.assistant_provider_profiles(profile_id),
    privacy_mode TEXT NOT NULL CHECK (privacy_mode IN ('local_only', 'configured')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assistant_conversations_owner
    ON public.assistant_conversations (owner_key, updated_at DESC);

CREATE TABLE IF NOT EXISTS public.assistant_context_revisions (
    conversation_id UUID NOT NULL REFERENCES public.assistant_conversations(conversation_id),
    revision INTEGER NOT NULL CHECK (revision > 0),
    scope TEXT NOT NULL CHECK (scope IN ('knowledge', 'planning')),
    generation_id UUID REFERENCES public.assistant_dataset_generations(generation_id),
    snapshot_id UUID REFERENCES public.assistant_input_snapshots(snapshot_id),
    pi_id TEXT,
    scenario_id TEXT,
    run_id BIGINT,
    kb_revision TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (conversation_id, revision),
    CHECK ((scope = 'knowledge' AND generation_id IS NULL AND snapshot_id IS NULL AND run_id IS NULL)
        OR (scope = 'planning' AND generation_id IS NOT NULL AND snapshot_id IS NOT NULL
            AND pi_id IS NOT NULL AND scenario_id IS NOT NULL AND run_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS public.assistant_messages (
    message_id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES public.assistant_conversations(conversation_id),
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    context_revision INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    status TEXT NOT NULL DEFAULT 'complete',
    content TEXT NOT NULL,
    payload JSONB,
    default_prompt_id BIGINT REFERENCES public.assistant_prompt_versions(prompt_id),
    user_prompt_id BIGINT REFERENCES public.assistant_prompt_versions(prompt_id),
    profile_id BIGINT REFERENCES public.assistant_provider_profiles(profile_id),
    usage JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, sequence_no),
    FOREIGN KEY (conversation_id, context_revision)
        REFERENCES public.assistant_context_revisions(conversation_id, revision)
);

CREATE TABLE IF NOT EXISTS public.assistant_jobs (
    job_id UUID PRIMARY KEY,
    owner_key TEXT NOT NULL,
    conversation_id UUID REFERENCES public.assistant_conversations(conversation_id),
    kind TEXT NOT NULL CHECK (kind IN ('message', 'scenario', 'kb_reindex')),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'expired')),
    idempotency_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    input_payload JSONB NOT NULL,
    result_payload JSONB,
    error_payload JSONB,
    deadline_at TIMESTAMPTZ NOT NULL,
    lease_until TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_key, idempotency_key),
    CHECK ((kind = 'kb_reindex' AND conversation_id IS NULL)
        OR (kind IN ('message', 'scenario') AND conversation_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS assistant_one_active_job_per_chat
    ON public.assistant_jobs (conversation_id)
    WHERE conversation_id IS NOT NULL AND status IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS public.assistant_scenario_results (
    scenario_result_id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES public.assistant_conversations(conversation_id),
    snapshot_id UUID NOT NULL REFERENCES public.assistant_input_snapshots(snapshot_id),
    input_payload JSONB NOT NULL,
    result_payload JSONB NOT NULL,
    engine_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.assistant_evidence (
    evidence_id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES public.assistant_conversations(conversation_id),
    message_id UUID REFERENCES public.assistant_messages(message_id),
    source_type TEXT NOT NULL CHECK (source_type IN ('snapshot', 'document', 'scenario')),
    source_ref TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.assistant_recommendations (
    recommendation_id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES public.assistant_conversations(conversation_id),
    message_id UUID REFERENCES public.assistant_messages(message_id),
    scenario_result_id UUID REFERENCES public.assistant_scenario_results(scenario_result_id),
    context_revision INTEGER NOT NULL,
    text TEXT NOT NULL,
    basis_status TEXT NOT NULL CHECK (basis_status IN ('verified_by_scenario', 'proposal', 'needs_data')),
    freshness TEXT NOT NULL DEFAULT 'current' CHECK (freshness IN ('current', 'stale', 'superseded')),
    supersedes UUID REFERENCES public.assistant_recommendations(recommendation_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (conversation_id, context_revision)
        REFERENCES public.assistant_context_revisions(conversation_id, revision)
);

CREATE TABLE IF NOT EXISTS public.assistant_kb_documents (
    document_id UUID PRIMARY KEY,
    path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (path, content_sha256)
);
CREATE TABLE IF NOT EXISTS public.assistant_kb_chunks (
    chunk_id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES public.assistant_kb_documents(document_id),
    chunk_no INTEGER NOT NULL,
    heading_path TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding_model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_no)
);
