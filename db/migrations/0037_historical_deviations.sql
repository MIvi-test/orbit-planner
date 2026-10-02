-- Pin the comparison plan at upload time and backfill older reports once.
ALTER TABLE actual_uploads ADD COLUMN IF NOT EXISTS plan_run_id INT;
DO $fk$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'actual_uploads_plan_run_fk') THEN
        ALTER TABLE actual_uploads ADD CONSTRAINT actual_uploads_plan_run_fk
            FOREIGN KEY (plan_run_id) REFERENCES plan_runs(run_id) ON DELETE SET NULL;
    END IF;
END
$fk$;
UPDATE actual_uploads u SET plan_run_id = (
    SELECT r.run_id FROM plan_runs r
    WHERE r.pi_id = u.pi_id AND r.status = 'ok' AND r.as_of_sprint <= u.sprint_no
      AND (r.actuals_upload_id IS NULL OR r.actuals_upload_id IN
           (SELECT x.upload_id FROM actual_uploads x
            WHERE x.pi_id = u.pi_id AND x.sprint_no < u.sprint_no))
    ORDER BY r.as_of_sprint DESC, r.run_id DESC LIMIT 1
);

CREATE OR REPLACE VIEW v_sprint_deviation AS
WITH report_items AS (
    SELECT u.upload_id, u.pi_id, u.sprint_no, u.plan_run_id, ids.task_id
    FROM actual_uploads u
    CROSS JOIN LATERAL (
        SELECT s.task_id FROM plan_task_schedule s
        WHERE s.run_id = u.plan_run_id AND s.decision = 'in_quarter'
          AND s.start_sprint <= u.sprint_no
        UNION
        SELECT a.task_id FROM task_actuals a WHERE a.upload_id = u.upload_id
    ) ids
)
SELECT f.upload_id, f.sprint_no, f.plan_run_id, f.task_id, t.team_id, t.estimation_sp,
       s.start_sprint AS planned_start, s.end_sprint AS planned_end,
       a.status       AS reported_status,
       COALESCE((SELECT SUM(x.hours) FROM plan_assignments x
                  WHERE x.run_id = f.plan_run_id AND x.task_id = f.task_id
                    AND x.sprint_no = f.sprint_no), 0)                    AS planned_hours,
       COALESCE((SELECT SUM(x.hours) FROM task_actual_spent x
                  WHERE x.upload_id = f.upload_id AND x.task_id = f.task_id), 0) AS spent_hours,
       CASE
         WHEN s.task_id IS NULL THEN 'вне плана'
         WHEN h.status = 'Done' AND completion.sprint_no > s.end_sprint
              THEN 'завершена с опозданием'
         WHEN h.status = 'Done' AND completion.sprint_no = s.end_sprint THEN 'в срок'
         WHEN h.status = 'Done' AND completion.sprint_no < s.end_sprint THEN 'раньше плана'
         WHEN s.end_sprint <= f.sprint_no AND COALESCE(h.status, seed.status) <> 'Done'
              THEN 'не закрыта в срок'
         WHEN a.task_id IS NULL THEN 'нет данных по задаче'
         ELSE 'по плану' END                                              AS deviation
FROM report_items f
JOIN tasks t ON t.task_id = f.task_id
LEFT JOIN tasks_seed_state seed ON seed.task_id = f.task_id
LEFT JOIN plan_task_schedule s ON s.run_id = f.plan_run_id AND s.task_id = f.task_id
    AND s.decision = 'in_quarter' AND s.start_sprint <= f.sprint_no
LEFT JOIN task_actuals a ON a.upload_id = f.upload_id AND a.task_id = f.task_id
LEFT JOIN LATERAL (
    SELECT prior.status FROM task_actuals prior
    JOIN actual_uploads u ON u.upload_id = prior.upload_id
    WHERE prior.task_id = f.task_id AND u.pi_id = f.pi_id AND u.sprint_no <= f.sprint_no
    ORDER BY u.sprint_no DESC LIMIT 1
) h ON TRUE
LEFT JOIN LATERAL (
    SELECT COALESCE(
        (SELECT sp.sprint_no FROM sprints sp
         WHERE sp.pi_id = f.pi_id AND done.actual_end BETWEEN sp.start_date AND sp.end_date
         LIMIT 1), first_done.sprint_no
    ) AS sprint_no
    FROM (
        SELECT u.sprint_no FROM task_actuals prior
        JOIN actual_uploads u ON u.upload_id = prior.upload_id
        WHERE prior.task_id = f.task_id AND u.pi_id = f.pi_id
          AND u.sprint_no <= f.sprint_no AND prior.status = 'Done'
        ORDER BY u.sprint_no LIMIT 1
    ) first_done
    LEFT JOIN LATERAL (
        SELECT prior.actual_end FROM task_actuals prior
        JOIN actual_uploads u ON u.upload_id = prior.upload_id
        WHERE prior.task_id = f.task_id AND u.pi_id = f.pi_id
          AND u.sprint_no <= f.sprint_no AND prior.actual_end IS NOT NULL
        ORDER BY u.sprint_no DESC LIMIT 1
    ) done ON TRUE
) completion ON TRUE;
COMMENT ON VIEW v_sprint_deviation IS
 'Факт и план на момент загрузки: план закреплён в actual_uploads, статус берётся из истории до спринта. '
 'Включает внеплановые задачи и позднее завершение.';
