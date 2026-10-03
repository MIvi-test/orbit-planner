BEGIN;
ALTER TABLE load_batches ADD COLUMN IF NOT EXISTS config_sha256 TEXT;
CREATE TABLE IF NOT EXISTS source_provenance (
    batch_id INT NOT NULL REFERENCES load_batches(batch_id) ON DELETE CASCADE,
    entity TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_cell TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    rule_version TEXT NOT NULL,
    PRIMARY KEY (batch_id, entity, entity_id, field_name, source_sheet, source_cell)
);
CREATE INDEX IF NOT EXISTS ix_source_provenance_entity ON source_provenance(entity, entity_id);
CREATE TABLE IF NOT EXISTS plan_capacity_snapshot (
    run_id INT NOT NULL REFERENCES plan_runs(run_id) ON DELETE CASCADE,
    engineer_id TEXT NOT NULL REFERENCES engineers(engineer_id),
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    sprint_no SMALLINT NOT NULL,
    available_hours NUMERIC(12,4) NOT NULL CHECK (available_hours >= 0),
    PRIMARY KEY (run_id, engineer_id, team_id, sprint_no)
);
COMMIT;
