-- Compare all meaningful plan dimensions and avoid invented causes.
CREATE OR REPLACE VIEW v_plan_diff AS
WITH pairs AS (
    SELECT r.run_id, r.as_of_sprint, r.actuals_upload_id,
           (SELECT u.sprint_no FROM actual_uploads u
             WHERE u.upload_id = r.actuals_upload_id) AS reported_sprint,
           (SELECT MAX(p.run_id) FROM plan_runs p
             WHERE p.run_id < r.run_id AND p.pi_id = r.pi_id
               AND p.status IN ('ok', 'infeasible')
               AND p.algorithm = r.algorithm
               AND p.params->>'dependency_mode' IS NOT DISTINCT FROM r.params->>'dependency_mode'
               AND p.params->>'initiative_mode' IS NOT DISTINCT FROM r.params->>'initiative_mode'
           ) AS prev_run_id
    FROM plan_runs r
), base AS (
    SELECT pr.run_id, pr.prev_run_id, pr.reported_sprint, t.task_id, t.prodf_id, t.team_id,
           p.decision AS prev_decision, p.start_sprint AS prev_start, p.end_sprint AS prev_end,
           c.decision AS new_decision, c.start_sprint AS new_start, c.end_sprint AS new_end,
           ts.status AS status_at_run,
           jsonb_build_array(p.reason_code, p.reason_text, p.reason_details) AS prev_reason,
           jsonb_build_array(c.reason_code, c.reason_text, c.reason_details) AS new_reason,
           COALESCE((SELECT jsonb_agg(jsonb_build_array(a.sprint_no, a.engineer_id,
                        a.role_id, a.home_team_id, a.serving_team_id, a.hours, a.work_hours)
                        ORDER BY a.sprint_no, a.engineer_id, a.role_id, a.home_team_id, a.serving_team_id)
                     FROM plan_assignments a WHERE a.run_id = pr.prev_run_id
                       AND a.task_id = t.task_id), '[]'::jsonb) AS prev_assignments,
           COALESCE((SELECT jsonb_agg(jsonb_build_array(a.sprint_no, a.engineer_id,
                        a.role_id, a.home_team_id, a.serving_team_id, a.hours, a.work_hours)
                        ORDER BY a.sprint_no, a.engineer_id, a.role_id, a.home_team_id, a.serving_team_id)
                     FROM plan_assignments a WHERE a.run_id = pr.run_id
                       AND a.task_id = t.task_id), '[]'::jsonb) AS new_assignments,
           COALESCE((SELECT jsonb_agg(jsonb_build_array(x.sprint_no, x.sp)
                        ORDER BY x.sprint_no)
                     FROM plan_task_sp x WHERE x.run_id = pr.prev_run_id
                       AND x.task_id = t.task_id), '[]'::jsonb) AS prev_sp,
           COALESCE((SELECT jsonb_agg(jsonb_build_array(x.sprint_no, x.sp)
                        ORDER BY x.sprint_no)
                     FROM plan_task_sp x WHERE x.run_id = pr.run_id
                       AND x.task_id = t.task_id), '[]'::jsonb) AS new_sp
    FROM pairs pr
    JOIN tasks t ON TRUE
    LEFT JOIN plan_task_schedule p ON p.run_id = pr.prev_run_id AND p.task_id = t.task_id
    LEFT JOIN plan_task_schedule c ON c.run_id = pr.run_id AND c.task_id = t.task_id
    LEFT JOIN task_state ts ON ts.run_id = pr.run_id AND ts.task_id = t.task_id
    WHERE pr.prev_run_id IS NOT NULL
      AND (p.task_id IS NOT NULL OR c.task_id IS NOT NULL)
), classified AS (
    SELECT b.*,
           (b.prev_start IS DISTINCT FROM b.new_start) AS start_changed,
           (b.prev_assignments IS DISTINCT FROM b.new_assignments) AS assignment_changed,
           (b.prev_sp IS DISTINCT FROM b.new_sp) AS sp_changed,
           (b.prev_reason IS DISTINCT FROM b.new_reason) AS reason_changed,
           CASE
             WHEN b.new_decision IS NULL AND b.status_at_run = 'Done' THEN 'completed'
             WHEN b.prev_decision IS NULL AND b.new_decision IS NOT NULL THEN 'newly_planned'
             WHEN b.new_decision = 'cancelled' AND b.prev_decision IS DISTINCT FROM 'cancelled' THEN 'newly_cancelled'
             WHEN b.prev_decision = 'in_quarter' AND b.new_decision <> 'in_quarter' THEN 'newly_deferred'
             WHEN b.prev_decision <> 'in_quarter' AND b.new_decision = 'in_quarter' THEN 'newly_planned'
             WHEN b.prev_decision IS DISTINCT FROM b.new_decision THEN 'decision_changed'
             WHEN b.new_end > b.prev_end THEN 'shifted_later'
             WHEN b.new_end < b.prev_end THEN 'shifted_earlier'
             WHEN b.prev_start IS DISTINCT FROM b.new_start THEN 'start_changed'
             WHEN b.prev_assignments IS DISTINCT FROM b.new_assignments THEN 'assignment_changed'
             WHEN b.prev_sp IS DISTINCT FROM b.new_sp THEN 'sp_changed'
             WHEN b.prev_reason IS DISTINCT FROM b.new_reason THEN 'reason_changed'
             ELSE 'unchanged'
           END AS change_type
    FROM base b
), caused AS (
    SELECT c.*,
           CASE
             WHEN c.change_type = 'completed' THEN 'completed'
             WHEN c.change_type = 'unchanged' THEN NULL
             WHEN c.reported_sprint IS NOT NULL AND c.prev_decision = 'in_quarter'
                  AND c.prev_end <= c.reported_sprint AND c.status_at_run <> 'Done'
                  AND c.change_type IN ('shifted_later', 'newly_deferred', 'newly_cancelled')
               THEN 'own_slip'
             WHEN c.change_type IN ('shifted_later', 'newly_deferred', 'newly_cancelled')
                  AND EXISTS (SELECT 1 FROM task_dependencies d JOIN classified blocker
                    ON blocker.run_id = c.run_id AND blocker.task_id = d.blocking_task_id
                    WHERE d.blocked_task_id = c.task_id
                      AND blocker.change_type IN ('shifted_later', 'newly_deferred', 'newly_cancelled'))
               THEN 'dependency'
             ELSE 'unknown'
           END AS cause
    FROM classified c
)
SELECT b.run_id, b.prev_run_id, b.reported_sprint, b.task_id, b.prodf_id, b.team_id,
       b.prev_decision, b.prev_start, b.prev_end,
       b.new_decision, b.new_start, b.new_end, b.status_at_run, b.change_type,
       b.cause,
       CASE
         WHEN b.cause = 'completed' THEN 'выполнена по факту'
         WHEN b.cause = 'own_slip' THEN 'не закрыта к концу спринта ' || b.reported_sprint
         WHEN b.cause = 'dependency' THEN 'сдвинулась блокирующая задача ' || (
             SELECT string_agg(d.blocking_task_id, ', ' ORDER BY d.blocking_task_id)
             FROM task_dependencies d JOIN classified blocker
               ON blocker.run_id = b.run_id AND blocker.task_id = d.blocking_task_id
             WHERE d.blocked_task_id = b.task_id
               AND blocker.change_type IN ('shifted_later', 'newly_deferred', 'newly_cancelled'))
         WHEN b.cause IS NULL THEN NULL
         ELSE 'изменение плана; причина не установлена'
       END AS explanation,
       b.start_changed, b.assignment_changed, b.sp_changed, b.reason_changed
FROM caused b;
COMMENT ON VIEW v_plan_diff IS
 'Сравнение с предыдущим опубликованным прогоном того же сценария. Причина указывается '
 'только когда подтверждена фактом или сдвигом блокирующей; иначе unknown.';
