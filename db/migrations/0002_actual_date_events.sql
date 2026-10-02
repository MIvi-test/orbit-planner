-- Empty date cells keep the last confirmed value; CLEAR is an explicit event.
ALTER TABLE task_actuals
    ADD COLUMN IF NOT EXISTS clear_actual_start BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS clear_actual_end BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE task_actuals
    ADD CONSTRAINT task_actuals_clear_start_requires_null
        CHECK (NOT clear_actual_start OR actual_start IS NULL),
    ADD CONSTRAINT task_actuals_clear_end_requires_null
        CHECK (NOT clear_actual_end OR actual_end IS NULL);

CREATE OR REPLACE FUNCTION apply_actuals() RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
    UPDATE tasks t
       SET status = s.status, actual_start = s.actual_start, actual_end = s.actual_end
      FROM tasks_seed_state s
     WHERE s.task_id = t.task_id;
    DELETE FROM task_role_spent;
    INSERT INTO task_role_spent (task_id, role_id, hours)
    SELECT task_id, role_id, hours FROM task_role_spent_seed;

    UPDATE tasks t
       SET status       = a.status,
           actual_start = CASE WHEN start_event.task_id IS NOT NULL
                               THEN CASE WHEN start_event.clear_actual_start THEN NULL
                                         ELSE start_event.actual_start END
                               ELSE t.actual_start END,
           actual_end   = CASE WHEN a.status <> 'Done' THEN NULL
                               WHEN end_event.task_id IS NOT NULL
                               THEN CASE WHEN end_event.clear_actual_end THEN NULL
                                         ELSE end_event.actual_end END
                               ELSE t.actual_end END
      FROM (SELECT DISTINCT ON (ta.task_id) ta.task_id, ta.status
              FROM task_actuals ta JOIN actual_uploads u ON u.upload_id = ta.upload_id
             ORDER BY ta.task_id, u.sprint_no DESC, u.upload_id DESC) a
      LEFT JOIN LATERAL (
          SELECT ta.task_id, ta.actual_start, ta.clear_actual_start
          FROM task_actuals ta JOIN actual_uploads u ON u.upload_id = ta.upload_id
          WHERE ta.task_id = a.task_id
            AND (ta.actual_start IS NOT NULL OR ta.clear_actual_start)
          ORDER BY u.sprint_no DESC, u.upload_id DESC LIMIT 1
      ) start_event ON TRUE
      LEFT JOIN LATERAL (
          SELECT ta.task_id, ta.actual_end, ta.clear_actual_end
          FROM task_actuals ta JOIN actual_uploads u ON u.upload_id = ta.upload_id
          WHERE ta.task_id = a.task_id
            AND (ta.actual_end IS NOT NULL OR ta.clear_actual_end)
          ORDER BY u.sprint_no DESC, u.upload_id DESC LIMIT 1
      ) end_event ON TRUE
     WHERE a.task_id = t.task_id;

    INSERT INTO task_role_spent (task_id, role_id, hours)
    SELECT task_id, role_id, SUM(hours) FROM task_actual_spent GROUP BY task_id, role_id
    ON CONFLICT (task_id, role_id) DO UPDATE SET hours = task_role_spent.hours + EXCLUDED.hours;
END
$fn$;

COMMENT ON FUNCTION apply_actuals() IS
 'Пересобирает статус, независимые события дат и накопленные часы из seed и журнала. '
 'Пустая дата сохраняет прежнюю, clear_* явно очищает поле.';

-- Apply corrected replay to data already uploaded before this migration.
DO $replay$
BEGIN
    IF EXISTS (SELECT 1 FROM tasks_seed_state) THEN
        PERFORM apply_actuals();
    END IF;
END
$replay$;
