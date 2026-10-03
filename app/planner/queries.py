"""SQL чтения входа планировщика. Всё — к витринам: планировщик не знает ядро изнутри."""
from __future__ import annotations


# ---------------------------------------------------------------------------
#  Запросы на чтение. Все — к витринам: планировщик не знает ядро изнутри.
# ---------------------------------------------------------------------------
PI_SQL = """
SELECT p.pi_id, p.start_date, p.end_date, p.sprint_count, p.fte_hours_per_sprint,
       COALESCE(f.days_total, p.sprint_count * p.sprint_length_days) AS pi_days,
       COALESCE(f.factor, p.sprint_count)                            AS fund_factor
FROM pi_periods p
LEFT JOIN v_pi_fund_factor f ON f.pi_id = p.pi_id
ORDER BY p.pi_id
LIMIT 1
"""


# factor спринта — из вьюхи, а не «из головы»: в текущем PI
# шесть полных спринтов, и планировщик обязан считать так же, как инварианты.
SPRINTS_SQL = """
SELECT s.sprint_no, s.start_date, s.end_date, s.length_days, f.factor
FROM sprints s
JOIN v_sprint_fund_factor f ON f.pi_id = s.pi_id AND f.sprint_no = s.sprint_no
WHERE s.pi_id = %s
ORDER BY s.sprint_no
"""


# Порядок обхода — правило из спеки: инициатива по скорингу, задача по топологии.
LIVE_TASKS_SQL = """
SELECT b.task_id, b.prodf_id, b.team_id, b.status, b.priority_rung, b.rung AS own_rung,
       i.business_priority,
       COALESCE(b.estimation_sp, 0)          AS estimation_sp,
       GREATEST(COALESCE(b.estimation_sp, 0) - COALESCE(progress.completed_sp, 0), 0) AS remaining_sp,
       b.summary,
       COALESCE(b.earliest_start_sprint_at_load, 1)  AS earliest_start_sprint,
       COALESCE(b.topo_order, 0)             AS topo_order,
       b.estimate_disputed
FROM v_task_board b
JOIN initiatives i ON i.prodf_id = b.prodf_id
LEFT JOIN (SELECT a.task_id, SUM(a.completed_sp) AS completed_sp
           FROM task_actuals a JOIN actual_uploads u ON u.upload_id = a.upload_id
           WHERE u.coverage_status = 'complete' GROUP BY a.task_id) progress ON progress.task_id = b.task_id
WHERE b.status IN ('ToDo', 'InProgress')
ORDER BY b.priority_rung DESC NULLS LAST, b.topo_order, b.task_id
"""


TASK_ROLES_SQL = """
SELECT rm.task_id, rm.role_id, r.canonical_name AS role_name,
       rm.estimated_hours, rm.spent_hours, rm.remaining_hours, rm.remaining_unknown,
       rm.remaining_provisional
FROM v_task_remaining_hh rm
JOIN roles r ON r.role_id = rm.role_id
JOIN tasks t ON t.task_id = rm.task_id
WHERE t.status IN ('ToDo', 'InProgress')
ORDER BY rm.task_id, rm.role_id
"""


# Единственный источник правды о паре «инженер × роль» (ADR-012): и кандидаты
# на роль, и множитель часов берутся отсюда. Строгий режим — замещения
# отклонены организаторами (ответ №2, ADR-010), поэтому только родные строки.
COVERAGE_SQL = """
SELECT c.engineer_id, c.role_id, r.canonical_name AS role_name, c.is_native, c.efficiency
FROM v_engineer_role_coverage c
JOIN roles r ON r.role_id = c.role_id
WHERE c.is_native
ORDER BY c.role_id, c.engineer_id
"""


ENGINEERS_SQL = """
SELECT e.engineer_id, e.role_id, e.grade, e.total_capacity_rate,
       o.team_id, o.capacity_rate
FROM engineers e
JOIN engineer_orbits o ON o.engineer_id = e.engineer_id
ORDER BY e.engineer_id, o.team_id
"""


TASK_SKILL_REVIEWS_SQL = """
SELECT r.task_id, r.role_id, r.status, q.skill_id, s.name AS skill_name
FROM task_role_skill_reviews r
LEFT JOIN task_role_skill_requirements q
  ON q.task_id = r.task_id AND q.role_id = r.role_id
LEFT JOIN skills s ON s.skill_id = q.skill_id
ORDER BY r.task_id, r.role_id, q.skill_id
"""


ENGINEER_SKILLS_SQL = """
SELECT engineer_id, skill_id FROM engineer_skills ORDER BY engineer_id, skill_id
"""


TEAM_CAPACITY_SQL = """
SELECT team_id, available_sp_per_sprint, history_points, avg_velocity, focus_factor
FROM v_team_capacity_sp
ORDER BY team_id
"""

# Скорость по истории — суммой и числом точек, чтобы добавлять наблюдения текущего PI (DA-27).
TEAM_VELOCITY_HISTORY_SQL = """
SELECT t.team_id, t.focus_factor, COALESCE(SUM(h.velocity_achieved), 0) AS velocity_sum, COUNT(h.*) AS points
FROM teams t LEFT JOIN team_history h ON h.team_id = t.team_id
GROUP BY t.team_id, t.focus_factor ORDER BY t.team_id
"""

TEAM_VELOCITY_OBSERVED_SQL = """
SELECT team_id, sprint_no, delivered_sp FROM v_team_velocity_observed WHERE pi_id = %s ORDER BY sprint_no, team_id
"""


# Живые рёбра для упаковки; завершённые блокирующие входят в all_deps и
# пересчитываются по фактическим датам в _refresh_live_graph.
LIVE_DEPS_SQL = """
SELECT d.blocking_task_id, d.blocked_task_id, d.min_gap_sprints
FROM task_dependencies d
JOIN tasks bt ON bt.task_id = d.blocking_task_id
JOIN tasks kt ON kt.task_id = d.blocked_task_id
WHERE bt.status IN ('ToDo', 'InProgress')
  AND kt.status IN ('ToDo', 'InProgress')
ORDER BY d.blocking_task_id, d.blocked_task_id
"""


ALL_DEPS_SQL = """
SELECT blocking_task_id, blocked_task_id, min_gap_sprints
FROM task_dependencies ORDER BY blocking_task_id, blocked_task_id
"""


TASK_DATES_SQL = """
SELECT task_id, status, actual_start, actual_end FROM tasks ORDER BY task_id
"""


# Слепок task_state делается по ВСЕМ задачам, включая Done: это история.
ALL_TASKS_SQL = """
SELECT t.task_id, t.status, COALESCE(t.estimation_sp, 0) AS estimation_sp,
       COALESCE(SUM(rm.remaining_hours), 0)              AS remaining_hh
FROM tasks t
LEFT JOIN v_task_remaining_hh rm ON rm.task_id = t.task_id
GROUP BY t.task_id, t.status, t.estimation_sp
ORDER BY t.task_id
"""


BUS_FACTOR_SQL = """
SELECT role_name, bus_factor, demand_hh
FROM v_bus_factor
WHERE demand_hh > 0
ORDER BY bus_factor, role_name
"""


# Bus Factor по компетенциям (ТЗ, ADR-024): навык, носителей, роль нужна бэклогу,
# единственный носитель востребованного навыка.
SKILL_BUS_FACTOR_SQL = """
SELECT skill_name, bus_factor, in_demand, critical
FROM v_bus_factor_skill
ORDER BY bus_factor, skill_name
"""


# Факт спринтов (ADR-021): последняя загрузка и какие задачи в каком спринте
# ВПЕРВЫЕ отмечены выполненными. Спринт задаёт дата события, не дата загрузки.
LAST_UPLOAD_SQL = """
SELECT upload_id, sprint_no FROM actual_uploads
WHERE pi_id = %s AND coverage_status = 'complete' ORDER BY sprint_no DESC LIMIT 1
"""


DONE_IN_SPRINT_SQL = """
SELECT sprint_no, task_id FROM v_task_done_sprint WHERE pi_id = %s ORDER BY sprint_no, task_id
"""


TASK_PRODF_SQL = "SELECT task_id, prodf_id FROM tasks ORDER BY task_id"


# Первоначальный план = канонический базовый прогон целиком: решение, старт и
# конец каждой задачи Недели 0. Пересчёт базу сравнения не меняет (ТЗ).
BASELINE_SCHEDULE_SQL = """
SELECT b.run_id, b.task_id, b.planned_sp, s.decision, s.start_sprint, s.end_sprint
FROM plan_baseline b
JOIN plan_task_schedule s ON s.run_id = b.run_id AND s.task_id = b.task_id
WHERE b.run_id = (SELECT MIN(run_id) FROM plan_runs
                  WHERE pi_id = %s AND as_of_sprint = 0 AND status IN ('ok', 'infeasible'))
ORDER BY b.task_id
"""


# Проверка ответа №4: три источника часов расходятся — сколько раз и насколько.
ESTIMATE_CONFLICT_SQL = """
SELECT COUNT(*)                                     AS issues,
       COUNT(*) FILTER (WHERE severity = 'warning') AS warnings
FROM dq_issues
WHERE rule_code = 'ESTIMATE_SOURCES_DISAGREE'
"""


ESTIMATE_MISMATCH_SQL = """
SELECT t.task_id
FROM tasks t
LEFT JOIN (SELECT task_id, SUM(hours) AS role_hours
           FROM task_role_estimates GROUP BY task_id) r ON r.task_id = t.task_id
WHERE t.estimated_hh_effective IS DISTINCT FROM COALESCE(r.role_hours, 0)
   OR (COALESCE(t.estimation_sp, 0) > 0 AND COALESCE(r.role_hours, 0) = 0)
ORDER BY t.task_id
"""


SUBSTITUTION_ROWS_SQL = """
SELECT COUNT(*) AS active FROM role_substitutions WHERE status <> 'rejected'
"""


# Расписание ПЕРВОГО базового прогона (as_of_sprint = 0): это и есть обещание
# Недели 0, дальше оно не меняется (ADR-004). MIN, а не MAX: обещание фиксирует
# первый прогон, пересчёты на него не влияют.
BASELINE_STARTS_SQL = """
SELECT DISTINCT ON (s.task_id) s.task_id, s.start_sprint
FROM plan_task_schedule s
JOIN plan_runs r ON r.run_id = s.run_id
WHERE r.as_of_sprint = 0
  AND r.status IN ('ok', 'infeasible')
  AND r.run_id = (SELECT MIN(run_id) FROM plan_runs WHERE as_of_sprint = 0 AND status IN ('ok', 'infeasible'))
  AND s.start_sprint IS NOT NULL
ORDER BY s.task_id
"""
