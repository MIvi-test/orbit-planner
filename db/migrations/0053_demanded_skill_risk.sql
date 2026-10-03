-- Demand for confirmed task technologies, with an explicit role proxy for unreviewed work.

CREATE OR REPLACE VIEW v_bus_factor_skill AS
WITH holders AS (
    SELECT es.skill_id, e.engineer_id, e.role_id,
           (SELECT COUNT(*) FROM engineers x WHERE x.role_id = e.role_id) AS role_n
    FROM engineer_skills es JOIN engineers e ON e.engineer_id = es.engineer_id
), exact_demand AS (
    SELECT q.skill_id, SUM(rm.remaining_hours) AS demand_hh
    FROM task_role_skill_requirements q
    JOIN task_role_skill_reviews review
      ON review.task_id = q.task_id AND review.role_id = q.role_id
      AND review.status = 'confirmed'
    JOIN v_task_remaining_hh rm ON rm.task_id = q.task_id AND rm.role_id = q.role_id
    JOIN tasks t ON t.task_id = q.task_id
    WHERE t.status IN ('ToDo', 'InProgress') AND rm.remaining_hours > 0
    GROUP BY q.skill_id
), proxy_demand AS (
    SELECT h.skill_id, SUM(rm.remaining_hours) AS demand_hh
    FROM (SELECT DISTINCT skill_id, role_id FROM holders) h
    JOIN v_task_remaining_hh rm ON rm.role_id = h.role_id
    JOIN tasks t ON t.task_id = rm.task_id
    LEFT JOIN task_role_skill_reviews review
      ON review.task_id = rm.task_id AND review.role_id = rm.role_id
    WHERE t.status IN ('ToDo', 'InProgress') AND rm.remaining_hours > 0
      AND review.status IS DISTINCT FROM 'confirmed'
    GROUP BY h.skill_id
)
SELECT s.skill_id,
       s.name                                                   AS skill_name,
       COUNT(DISTINCT h.engineer_id)::int                       AS bus_factor,
       COALESCE(ARRAY_AGG(DISTINCT h.engineer_id ORDER BY h.engineer_id)
                FILTER (WHERE h.engineer_id IS NOT NULL), '{}'::text[]) AS engineers,
       ARRAY(SELECT DISTINCT o.team_id FROM engineer_orbits o
              JOIN holders x ON x.engineer_id = o.engineer_id
              WHERE x.skill_id = s.skill_id ORDER BY 1)         AS teams,
       ARRAY(SELECT DISTINCT r.canonical_name FROM holders x
              JOIN roles r ON r.role_id = x.role_id
              WHERE x.skill_id = s.skill_id ORDER BY 1)         AS roles,
       (COALESCE(ex.demand_hh, 0) + COALESCE(px.demand_hh, 0)) AS roles_demand_hh,
       (COALESCE(ex.demand_hh, 0) > 0 OR COALESCE(px.demand_hh, 0) > 0) AS in_demand,
       (COUNT(DISTINCT h.engineer_id) = 1 AND MAX(h.role_n) = 1) AS sole_in_role,
       CASE
         WHEN COUNT(DISTINCT h.engineer_id) = 0 AND COALESCE(ex.demand_hh, 0) > 0
              THEN 'нет носителей требуемого навыка'
         WHEN COUNT(DISTINCT h.engineer_id) = 1 AND COALESCE(ex.demand_hh, 0) > 0
              THEN 'критично: требуемый навык у одного'
         WHEN COUNT(DISTINCT h.engineer_id) = 1 AND COALESCE(px.demand_hh, 0) > 0
              THEN 'предварительно: один носитель роли'
         WHEN COUNT(DISTINCT h.engineer_id) = 1 THEN 'единственный носитель'
         WHEN COUNT(DISTINCT h.engineer_id) = 2 THEN 'два носителя'
         ELSE 'ок' END                                          AS risk,
       (COUNT(DISTINCT h.engineer_id) = 1
        AND (COALESCE(ex.demand_hh, 0) > 0 OR COALESCE(px.demand_hh, 0) > 0)) AS critical,
       CASE WHEN COALESCE(ex.demand_hh, 0) > 0 AND COALESCE(px.demand_hh, 0) > 0
                 THEN 'mixed'
            WHEN COALESCE(ex.demand_hh, 0) > 0 THEN 'confirmed'
            WHEN COALESCE(px.demand_hh, 0) > 0 THEN 'role_proxy'
            ELSE 'none' END AS demand_source
FROM skills s
LEFT JOIN holders h ON h.skill_id = s.skill_id
LEFT JOIN exact_demand ex ON ex.skill_id = s.skill_id
LEFT JOIN proxy_demand px ON px.skill_id = s.skill_id
GROUP BY s.skill_id, s.name, ex.demand_hh, px.demand_hh;
COMMENT ON VIEW v_bus_factor_skill IS
 'Bus Factor по компетенциям (ТЗ): число инженеров, заявивших навык. Градация риска: '
 '«критично» — единственный носитель требуемого навыка, независимо от числа коллег по роли. '
 'demand_source=confirmed — ручная разметка задач;

CREATE OR REPLACE VIEW v_engineer_absence_risk AS
WITH role_n AS (
    SELECT role_id, COUNT(*)::int AS n FROM engineers GROUP BY role_id
), uniq AS (
    SELECT UNNEST(engineers) AS engineer_id, skill_name, critical
    FROM v_bus_factor_skill WHERE bus_factor = 1
), asg AS (
    SELECT run_id, engineer_id, task_id, SUM(hours) AS hours
    FROM plan_assignments GROUP BY run_id, engineer_id, task_id
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
       CASE WHEN rn.n = 1 THEN ARRAY(SELECT a.task_id FROM asg a
              WHERE a.run_id = r.run_id AND a.engineer_id = e.engineer_id ORDER BY 1)
            ELSE '{}'::text[] END                                        AS tasks_without_backup,
       CASE WHEN rn.n = 1 THEN COALESCE((SELECT SUM(a.hours) FROM asg a
              WHERE a.run_id = r.run_id AND a.engineer_id = e.engineer_id), 0)
            ELSE 0 END                                                   AS hours_without_backup,
       CASE WHEN rn.n = 1 AND EXISTS (SELECT 1 FROM asg a
                   WHERE a.run_id = r.run_id AND a.engineer_id = e.engineer_id)
                 THEN 'критично: работы встанут'
            WHEN rn.n = 1 THEN 'единственный по роли'
            WHEN EXISTS (SELECT 1 FROM uniq u WHERE u.engineer_id = e.engineer_id AND u.critical)
                 THEN 'единственный носитель компетенций'
            ELSE 'ок' END                                                AS risk
FROM plan_runs r
CROSS JOIN engineers e
JOIN roles ro  ON ro.role_id = e.role_id
JOIN role_n rn ON rn.role_id = e.role_id;
COMMENT ON VIEW v_engineer_absence_risk IS
 'Профиль инженера + «что будет, если он выпадет» в данном прогоне. Замещения ролей '
 'запрещены организаторами (ADR-010), поэтому замена = другой инженер той же роли.';
