-- Explicit incremental completed SP; hours spent are not a progress measure.
ALTER TABLE task_actuals ADD COLUMN IF NOT EXISTS completed_sp NUMERIC(6,2);
DO $constraint$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'task_actuals_completed_sp_nonnegative'
    ) THEN
        ALTER TABLE task_actuals ADD CONSTRAINT task_actuals_completed_sp_nonnegative
            CHECK (completed_sp >= 0);
    END IF;
END
$constraint$;
