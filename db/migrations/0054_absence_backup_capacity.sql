-- Qualified and available replacement by sprint.
CREATE OR REPLACE VIEW v_engineer_absence_risk AS
WITH role_n AS (
    SELECT role_id, COUNT(*)::int AS n FROM engineers GROUP BY role_id
), uniq AS (
    SELECT UNNEST(engineers) AS engineer_id, skill_name, critical
    FROM v_bus_factor_skill WHERE bus_factor = 1
), asg AS (
    SELECT run_id, engineer_id, task_id, SUM(hours) AS hours
    FROM plan_assignments GROUP BY run_id, engineer_id, task_id
), assigned AS (
    SELECT run_id, task_id, engineer_id, role_id, sprint_no, SUM(hours) AS hours
    FROM plan_assignments GROUP BY run_id, task_id, engineer_id, role_id, sprint_no
), busy AS (
    SELECT run_id, engineer_id, sprint_no, SUM(hours) AS hours
    FROM plan_assignments GROUP BY run_id, engineer_id, sprint_no
), backup AS (
    SELECT a.*,
           EXISTS (SELECT 1 FROM task_role_skill_reviews review
                   WHERE review.task_id = a.task_id AND review.role_id = a.role_id
                     AND review.status = 'confirmed') AS stack_confirmed,
           EXISTS (
               SELECT 1 FROM engineers alternate
               JOIN plan_runs run ON run.run_id = a.run_id
               JOIN pi_periods p ON p.pi_id = run.pi_id
               JOIN v_sprint_fund_factor f ON f.pi_id = p.pi_id AND f.sprint_no = a.sprint_no
               LEFT JOIN busy occupied ON occupied.run_id = a.run_id
                   AND occupied.engineer_id = alternate.engineer_id
                   AND occupied.sprint_no = a.sprint_no
               WHERE alternate.engineer_id <> a.engineer_id
                 AND alternate.role_id = a.role_id
                 AND alternate.total_capacity_rate * p.fte_hours_per_sprint * f.factor
                     - COALESCE(occupied.hours, 0) >= a.hours
                 AND NOT EXISTS (
                     SELECT 1 FROM task_role_skill_requirements requirement
                     LEFT JOIN engineer_skills known
                       ON known.engineer_id = alternate.engineer_id
                      AND known.skill_id = requirement.skill_id
                     WHERE requirement.task_id = a.task_id
                       AND requirement.role_id = a.role_id
                       AND known.skill_id IS NULL
                 )
           ) AS has_capacity_and_skills
    FROM assigned a
)
SELECT r.run_id, e.engineer_id, ro.canonical_name AS role_name, e.grade,
       e.total_capacity_rate,
       ARRAY(SELECT o.team_id FROM engineer_orbits o
              WHERE o.engineer_id = e.engineer_id ORDER BY 1)            AS teams,
       rn.n                                                              AS role_bus_factor,
       ARRAY(SELECT u.skill_name FROM uniq u
              WHERE u.engineer_id = e.engineer_id ORDER BY 1)            AS unique_skills,
       ARRAY(SELECT u.skill_name FROM uniq u
              WHERE u.engineer_id = e.engineer_id AND u.critical ORDER BY 1) AS unique_critical_skills,
       COALESCE((SELECT SUM(a.hours) FROM asg a
                  WHERE a.run_id = r.run_id AND a.engineer_id = e.engineer_id), 0) AS planned_hours,
       ARRAY(SELECT a.task_id FROM asg a
              WHERE a.run_id = r.run_id AND a.engineer_id = e.engineer_id ORDER BY 1) AS planned_tasks,
       ARRAY(SELECT DISTINCT b.task_id FROM backup b
             WHERE b.run_id = r.run_id AND b.engineer_id = e.engineer_id
               AND b.stack_confirmed AND NOT b.has_capacity_and_skills ORDER BY 1)
                                                                        AS tasks_without_backup,
       COALESCE((SELECT SUM(b.hours) FROM backup b
                 WHERE b.run_id = r.run_id AND b.engineer_id = e.engineer_id
                   AND b.stack_confirmed AND NOT b.has_capacity_and_skills), 0)
                                                                        AS hours_without_backup,
       CASE WHEN EXISTS (SELECT 1 FROM backup b
                   WHERE b.run_id = r.run_id AND b.engineer_id = e.engineer_id
                     AND b.stack_confirmed AND NOT b.has_capacity_and_skills)
                 THEN 'нет прямой замены по фонду и стеку'
            WHEN EXISTS (SELECT 1 FROM backup b
                   WHERE b.run_id = r.run_id AND b.engineer_id = e.engineer_id
                     AND NOT b.stack_confirmed)
                 THEN 'замена не подтверждена'
            WHEN rn.n = 1 THEN 'единственный по роли'
            WHEN EXISTS (SELECT 1 FROM uniq u WHERE u.engineer_id = e.engineer_id AND u.critical)
                 THEN 'единственный носитель компетенций'
            ELSE 'ок' END                                                AS risk,
       ARRAY(SELECT DISTINCT b.task_id FROM backup b
             WHERE b.run_id = r.run_id AND b.engineer_id = e.engineer_id
               AND NOT b.stack_confirmed ORDER BY 1) AS tasks_backup_unverified
FROM plan_runs r
CROSS JOIN engineers e
JOIN roles ro  ON ro.role_id = e.role_id
JOIN role_n rn ON rn.role_id = e.role_id;
COMMENT ON VIEW v_engineer_absence_risk IS
 'Профиль инженера и проверка альтернативы по подтверждённому стеку и свободному '
 'фонду того же спринта. Для непроверенных требований выводится отдельное состояние. '
 'Полный сценарий с перестроением плана отдаёт /api/scenarios/absence.';
