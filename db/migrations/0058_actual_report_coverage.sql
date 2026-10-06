BEGIN;
ALTER TABLE actual_uploads ADD COLUMN coverage_status TEXT NOT NULL DEFAULT 'complete'
    CHECK (coverage_status IN ('draft', 'incomplete', 'complete'));
COMMENT ON COLUMN actual_uploads.coverage_status IS
 'Only complete, explicitly confirmed reports close a sprint and allow actual KPI calculation.';
CREATE OR REPLACE FUNCTION apply_actuals() RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
    -- 1. назад к датасету
    UPDATE tasks t
       SET status = s.status, actual_start = s.actual_start, actual_end = s.actual_end
      FROM tasks_seed_state s
     WHERE s.task_id = t.task_id;
    DELETE FROM task_role_spent;
    INSERT INTO task_role_spent (task_id, role_id, hours)
    SELECT task_id, role_id, hours FROM task_role_spent_seed;

    -- 2. Статус — из последней строки. Каждая дата — из последнего явного
    --    события для своего поля; NULL без clear_* означает «не передано».
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
              FROM task_actuals ta JOIN actual_uploads u ON u.upload_id = ta.upload_id AND u.coverage_status = 'complete'
             ORDER BY ta.task_id, u.sprint_no DESC, u.upload_id DESC) a
      LEFT JOIN LATERAL (
          SELECT ta.task_id, ta.actual_start, ta.clear_actual_start
          FROM task_actuals ta JOIN actual_uploads u ON u.upload_id = ta.upload_id AND u.coverage_status = 'complete'
          WHERE ta.task_id = a.task_id
            AND (ta.actual_start IS NOT NULL OR ta.clear_actual_start)
          ORDER BY u.sprint_no DESC, u.upload_id DESC LIMIT 1
      ) start_event ON TRUE
      LEFT JOIN LATERAL (
          SELECT ta.task_id, ta.actual_end, ta.clear_actual_end
          FROM task_actuals ta JOIN actual_uploads u ON u.upload_id = ta.upload_id AND u.coverage_status = 'complete'
          WHERE ta.task_id = a.task_id
            AND (ta.actual_end IS NOT NULL OR ta.clear_actual_end)
          ORDER BY u.sprint_no DESC, u.upload_id DESC LIMIT 1
      ) end_event ON TRUE
     WHERE a.task_id = t.task_id;

    -- 3. часы копятся по всем загрузкам
    INSERT INTO task_role_spent (task_id, role_id, hours)
    SELECT a.task_id, a.role_id, SUM(a.hours) FROM task_actual_spent a JOIN actual_uploads u ON u.upload_id = a.upload_id
    WHERE u.coverage_status = 'complete' GROUP BY a.task_id, a.role_id
    ON CONFLICT (task_id, role_id) DO UPDATE SET hours = task_role_spent.hours + EXCLUDED.hours;
END
$fn$;

CREATE OR REPLACE VIEW v_remaining_pi_fund_factor AS
SELECT p.pi_id, COALESCE(u.last_reported_sprint, 0) AS last_reported_sprint,
       COALESCE(SUM(f.factor) FILTER (
           WHERE f.sprint_no > COALESCE(u.last_reported_sprint, 0)), 0) AS factor
FROM pi_periods p
LEFT JOIN (SELECT pi_id, MAX(sprint_no) AS last_reported_sprint
           FROM actual_uploads WHERE coverage_status = 'complete' GROUP BY pi_id) u ON u.pi_id = p.pi_id
JOIN v_sprint_fund_factor f ON f.pi_id = p.pi_id
GROUP BY p.pi_id, u.last_reported_sprint;
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
    WHERE u.coverage_status = 'complete'
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
COMMIT;
