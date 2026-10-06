-- New runs snapshot role demand and equivalent completed work.
CREATE TABLE IF NOT EXISTS plan_role_demand_snapshot (
    run_id       INT NOT NULL REFERENCES plan_runs(run_id) ON DELETE CASCADE,
    task_id      TEXT NOT NULL REFERENCES tasks(task_id),
    role_id      SMALLINT NOT NULL REFERENCES roles(role_id),
    needed_hours NUMERIC(12,4) NOT NULL CHECK (needed_hours > 0),
    PRIMARY KEY (run_id, task_id, role_id)
);
ALTER TABLE plan_assignments ADD COLUMN IF NOT EXISTS work_hours NUMERIC(12,4);
-- Historical assignments predate the snapshot; preserve their value without
-- pretending that native hours prove substituted work.
UPDATE plan_assignments SET work_hours = hours WHERE work_hours IS NULL;
