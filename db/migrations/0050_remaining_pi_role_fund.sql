-- Recompute role coverage against the fund of still open sprints.

CREATE VIEW v_remaining_pi_fund_factor AS
SELECT p.pi_id, COALESCE(u.last_reported_sprint, 0) AS last_reported_sprint,
       COALESCE(SUM(f.factor) FILTER (
           WHERE f.sprint_no > COALESCE(u.last_reported_sprint, 0)), 0) AS factor
FROM pi_periods p
LEFT JOIN (SELECT pi_id, MAX(sprint_no) AS last_reported_sprint
           FROM actual_uploads GROUP BY pi_id) u ON u.pi_id = p.pi_id
JOIN v_sprint_fund_factor f ON f.pi_id = p.pi_id
GROUP BY p.pi_id, u.last_reported_sprint;

CREATE OR REPLACE VIEW v_role_supply_hh AS
SELECT r.role_id, r.canonical_name AS role_name, o.team_id,
       COUNT(DISTINCT o.engineer_id)                                     AS engineers,
       SUM(o.capacity_rate)                                              AS fte,
       ROUND(SUM(o.capacity_rate * p.fte_hours_per_sprint), 2)           AS hh_per_sprint,
       ROUND(SUM(o.capacity_rate * p.fte_hours_per_sprint)
             * (SELECT factor FROM v_pi_fund_factor LIMIT 1), 2)         AS hh_per_pi,
       ROUND(SUM(o.capacity_rate * p.fte_hours_per_sprint)
             * (SELECT factor FROM v_remaining_pi_fund_factor LIMIT 1), 2) AS hh_remaining_pi
FROM roles r
JOIN engineers       e ON e.role_id = r.role_id
JOIN engineer_orbits o ON o.engineer_id = e.engineer_id
CROSS JOIN pi_periods p
GROUP BY r.role_id, r.canonical_name, o.team_id;

CREATE OR REPLACE VIEW v_role_deficit AS
SELECT COALESCE(d.team_id, s.team_id)       AS team_id,
       COALESCE(d.role_name, s.role_name)   AS role_name,
       COALESCE(d.demand_hh, 0)             AS demand_hh,
       COALESCE(s.hh_remaining_pi, 0)       AS supply_hh,
       COALESCE(d.demand_hh, 0) - COALESCE(s.hh_remaining_pi, 0) AS gap_hh,
       CASE WHEN COALESCE(d.demand_hh, 0) = 0 THEN 'спроса нет'
            WHEN COALESCE(s.hh_remaining_pi, 0) = 0 AND COALESCE(org.hh, 0) = 0
                 THEN 'нет доступного фонда в организации'
            WHEN COALESCE(s.hh_remaining_pi, 0) = 0 THEN 'роли нет в команде — возможен заём'
            WHEN COALESCE(d.demand_hh, 0) > COALESCE(s.hh_remaining_pi, 0)
                 AND COALESCE(org.hh, 0) >= d.demand_hh THEN 'не хватает часов в команде — возможен заём'
            WHEN COALESCE(d.demand_hh, 0) > COALESCE(s.hh_remaining_pi, 0)
                 THEN 'не хватает часов'
            ELSE 'покрыто' END              AS verdict
FROM v_backlog_demand d
FULL OUTER JOIN v_role_supply_hh s
  ON s.team_id = d.team_id AND s.role_id = d.role_id
LEFT JOIN (SELECT role_id, SUM(hh_remaining_pi) AS hh
           FROM v_role_supply_hh GROUP BY role_id) org
  ON org.role_id = COALESCE(d.role_id, s.role_id);

CREATE OR REPLACE VIEW v_role_deficit_effective AS
WITH supply AS (
    SELECT c.role_id, o.team_id,
           SUM(o.capacity_rate * p.fte_hours_per_sprint)
           * (SELECT factor FROM v_remaining_pi_fund_factor LIMIT 1) AS hh
    FROM v_engineer_role_coverage c
    JOIN engineer_orbits o ON o.engineer_id = c.engineer_id
    CROSS JOIN pi_periods p
    GROUP BY c.role_id, o.team_id
)
SELECT COALESCE(d.team_id, s.team_id)     AS team_id,
       COALESCE(d.role_name, r.canonical_name) AS role_name,
       COALESCE(d.demand_hh, 0)           AS demand_hh,
       COALESCE(s.hh, 0)                  AS supply_with_substitution_hh,
       COALESCE(d.demand_hh, 0) - COALESCE(s.hh, 0) AS gap_hh,
       CASE WHEN COALESCE(d.demand_hh, 0) <= COALESCE(s.hh, 0) THEN 'покрыто'
            WHEN COALESCE(s.hh, 0) = 0 AND COALESCE(org.hh, 0) > 0
                 THEN 'роли нет в команде — возможен заём'
            WHEN COALESCE(s.hh, 0) = 0 THEN 'нет доступного фонда в организации'
            WHEN COALESCE(org.hh, 0) >= d.demand_hh
                 THEN 'не хватает часов в команде — возможен заём'
            ELSE 'не хватает часов' END   AS verdict
FROM v_backlog_demand d
FULL OUTER JOIN supply s ON s.team_id = d.team_id AND s.role_id = d.role_id
LEFT JOIN roles r ON r.role_id = s.role_id
LEFT JOIN (SELECT role_id, SUM(hh) AS hh FROM supply GROUP BY role_id) org
  ON org.role_id = COALESCE(d.role_id, s.role_id);

CREATE OR REPLACE VIEW v_role_coverage_org AS
WITH demand AS (
    SELECT role_id, SUM(demand_hh) AS demand_hh FROM v_backlog_demand GROUP BY role_id
), supply AS (
    SELECT c.role_id,
           COUNT(DISTINCT c.engineer_id)                                   AS people,
           COUNT(DISTINCT c.engineer_id) FILTER (WHERE c.is_native)        AS native_people,
           SUM(e.total_capacity_rate * p.fte_hours_per_sprint)
           * (SELECT factor FROM v_remaining_pi_fund_factor LIMIT 1) AS hh
    FROM v_engineer_role_coverage c
    JOIN engineers e ON e.engineer_id = c.engineer_id
    CROSS JOIN pi_periods p
    GROUP BY c.role_id
)
SELECT r.canonical_name                      AS role_name,
       COALESCE(d.demand_hh, 0)              AS demand_hh,
       COALESCE(s.native_people, 0)          AS native_people,
       COALESCE(s.people, 0)                 AS people_incl_substitution,
       COALESCE(s.hh, 0)                     AS supply_hh,
       COALESCE(d.demand_hh, 0) - COALESCE(s.hh, 0) AS gap_hh,
       CASE WHEN COALESCE(d.demand_hh, 0) = 0                  THEN 'спроса нет'
            WHEN COALESCE(s.hh, 0) = 0 AND COALESCE(s.people, 0) > 0
                 THEN 'нет фонда до конца PI'
            WHEN COALESCE(s.hh, 0) = 0                         THEN 'НАЙМ: закрыть некем'
            WHEN COALESCE(d.demand_hh, 0) > COALESCE(s.hh, 0)  THEN 'НАЙМ: не хватает часов'
            WHEN COALESCE(s.native_people, 0) = 0              THEN 'только замещением'
            ELSE 'покрыто' END               AS verdict
FROM roles r
LEFT JOIN demand d ON d.role_id = r.role_id
LEFT JOIN supply s ON s.role_id = r.role_id;
