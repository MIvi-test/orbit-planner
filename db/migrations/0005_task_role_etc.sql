CREATE TABLE IF NOT EXISTS task_role_etc (
    revision_id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    role_id SMALLINT NOT NULL,
    remaining_hours NUMERIC(8,2) NOT NULL CHECK (remaining_hours >= 0),
    reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (task_id, role_id) REFERENCES task_role_estimates(task_id, role_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_task_role_etc_latest ON task_role_etc(task_id, role_id, revision_id DESC);

INSERT INTO ref_decision_reasons (code, ord, decision, label, legacy_reason) VALUES
  ('ETC_REQUIRED', 9, 'deferred_next_pi', 'Нужно уточнить остаток работ или статус задачи', 'M2')
ON CONFLICT (code) DO NOTHING;

CREATE OR REPLACE VIEW v_task_remaining_hh AS
SELECT COALESCE(e.task_id, s.task_id)                            AS task_id,
       COALESCE(e.role_id, s.role_id)                            AS role_id,
       COALESCE(e.hours, 0)                                      AS estimated_hours,
       COALESCE(s.hours, 0)                                      AS spent_hours,
       COALESCE(etc.remaining_hours,
                CASE WHEN COALESCE(s.hours, 0) > 0 THEN 0 ELSE COALESCE(e.hours, 0) END) AS remaining_hours,
       (etc.revision_id IS NULL AND (COALESCE(s.hours, 0) > 0 OR COALESCE(e.hours, 0) = 0)
        AND t.status <> 'Done') AS remaining_unknown,
       etc.reason AS etc_reason
FROM task_role_estimates e
FULL OUTER JOIN task_role_spent s
  ON s.task_id = e.task_id AND s.role_id = e.role_id
JOIN tasks t ON t.task_id = COALESCE(e.task_id, s.task_id)
LEFT JOIN LATERAL (
    SELECT x.revision_id, x.remaining_hours, x.reason FROM task_role_etc x
    WHERE x.task_id = e.task_id AND x.role_id = e.role_id
    ORDER BY x.revision_id DESC LIMIT 1
) etc ON TRUE;
