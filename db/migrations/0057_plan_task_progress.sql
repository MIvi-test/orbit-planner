BEGIN;
CREATE VIEW v_plan_task_progress AS
WITH activity AS (
    SELECT run_id, task_id, sprint_no, SUM(hours) AS assigned_hours,
           SUM(work_hours) AS work_hours, 0::numeric AS sp
    FROM plan_assignments GROUP BY run_id, task_id, sprint_no
    UNION ALL
    SELECT run_id, task_id, sprint_no, 0::numeric, 0::numeric, SUM(sp)
    FROM plan_task_sp GROUP BY run_id, task_id, sprint_no
)
SELECT run_id, task_id, sprint_no, SUM(assigned_hours) AS assigned_hours,
       SUM(work_hours) AS work_hours, SUM(sp) AS sp,
       CASE WHEN SUM(assigned_hours) > 0 AND SUM(sp) > 0 THEN 'both'
            WHEN SUM(sp) > 0 THEN 'team_sp_only'
            ELSE 'engineer_hours_only' END AS progress_basis
FROM activity GROUP BY run_id, task_id, sprint_no;
COMMENT ON VIEW v_plan_task_progress IS
 'SP — отдельный бюджет пропускной способности команды, без универсального перевода в часы;'
 ' итоговая дата задачи определяется последним спринтом любого из двух потоков.';
COMMIT;
