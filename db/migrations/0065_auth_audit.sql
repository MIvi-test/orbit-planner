-- S-2: пользователи, роли и журнал действий; кто загрузил данные.
-- Токены в базе не хранятся: только SHA-256. Роли: viewer < planner < admin.
CREATE TABLE IF NOT EXISTS app_users (
    user_id      SERIAL PRIMARY KEY,
    name         TEXT        NOT NULL UNIQUE CHECK (btrim(name) <> ''),
    role         TEXT        NOT NULL CHECK (role IN ('viewer', 'planner', 'admin')),
    token_sha256 TEXT        NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    active       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ
);
COMMENT ON TABLE app_users IS
 'Пользователи сервиса. token_sha256 — SHA-256 токена; сам токен показывается один раз при создании '
 '(tools/manage_users.py). Не входит в TRUNCATE загрузки датасета.';

CREATE TABLE IF NOT EXISTS audit_log (
    event_id BIGSERIAL PRIMARY KEY,
    at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor    TEXT        NOT NULL,
    role     TEXT        NOT NULL,
    action   TEXT        NOT NULL,
    target   TEXT,
    outcome  TEXT        NOT NULL CHECK (outcome IN ('ok', 'rejected', 'failed')),
    client   TEXT,
    detail   JSONB       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_audit_log_at ON audit_log (at DESC);
COMMENT ON TABLE audit_log IS 'Журнал действий, меняющих данные: кто, что, с каким итогом. Только дописывается.';

ALTER TABLE load_batches    ADD COLUMN IF NOT EXISTS loaded_by   TEXT;
ALTER TABLE actual_uploads  ADD COLUMN IF NOT EXISTS uploaded_by TEXT;
ALTER TABLE task_role_etc   ADD COLUMN IF NOT EXISTS revised_by  TEXT;
