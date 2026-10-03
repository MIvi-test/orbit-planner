-- Keep the task board's dispute flag consistent with all three input estimates.
CREATE OR REPLACE VIEW v_task_board AS
SELECT t.task_id, t.prodf_id, i.br_id, i.priority_rung, t.team_id, t.summary,
       t.status, t.rung, t.estimation_sp,
       t.estimated_hh_effective, t.estimated_hh_declared, t.estimated_hh_matrix_total,
       (t.estimated_hh_effective IS DISTINCT FROM t.estimated_hh_declared OR
        (t.estimated_hh_matrix_total IS NOT NULL AND
         t.estimated_hh_effective IS DISTINCT FROM t.estimated_hh_matrix_total)) AS estimate_disputed,
       t.planned_start, t.planned_end, t.actual_start, t.actual_end,
       q.topo_order, q.depth, q.earliest_start_sprint, q.on_critical_path,
       COALESCE(rm.remaining_hh, 0) AS remaining_hh,
       (SELECT COUNT(*) FROM task_dependencies d WHERE d.blocked_task_id  = t.task_id) AS blocked_by,
       (SELECT COUNT(*) FROM task_dependencies d WHERE d.blocking_task_id = t.task_id) AS blocks
FROM tasks t
JOIN initiatives i ON i.prodf_id = t.prodf_id
LEFT JOIN task_sequence q ON q.task_id = t.task_id
LEFT JOIN (SELECT task_id, SUM(remaining_hours) AS remaining_hh
             FROM v_task_remaining_hh GROUP BY task_id) rm ON rm.task_id = t.task_id;
