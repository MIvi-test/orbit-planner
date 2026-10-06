BEGIN;

CREATE TABLE IF NOT EXISTS upload_revisions (
    revision_id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('dataset', 'actuals')),
    pi_id TEXT NOT NULL,
    sprint_no SMALLINT,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    content BYTEA NOT NULL,
    idempotency_key TEXT,
    response JSONB,
    plan_snapshot JSONB,
    superseded_by BIGINT REFERENCES upload_revisions(revision_id),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((kind = 'dataset' AND sprint_no IS NULL) OR (kind = 'actuals' AND sprint_no IS NOT NULL)),
    UNIQUE (kind, idempotency_key)
);
COMMENT ON TABLE upload_revisions IS
 'Неизменяемые исходные файлы загрузок и связь замещения. Активное состояние остаётся в actual_uploads и tasks.';

COMMIT;
