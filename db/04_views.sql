-- =====================================================================
--  ВИТРИНЫ. Вьюхи, не таблицы: пересчитываются сами, поддерживать нечего.
--  Первые пять — для планировщика, остальные — для бэкенда и фронта.
-- =====================================================================
BEGIN;

DROP VIEW IF EXISTS v_dq_summary, v_orbit_map, v_task_board, v_bus_factor,
     v_role_deficit, v_backlog_demand, v_role_supply_hh, v_satellite_capacity,
     v_task_remaining_hh, v_team_capacity_sp CASCADE;

DROP VIEW IF EXISTS v_remaining_pi_fund_factor, v_sprint_fund_factor, v_pi_fund_factor CASCADE;

-- --------------------------------------------------------------------
--  МНОЖИТЕЛЬ ФОНДА. Единственный источник ответа «сколько ЧЧ даёт
--  ставка в этом спринте / за весь PI». Полный спринт — 1.0000,
--  короткий 7-й (23.09..30.09.2026) — 8/14 = 0.5714 (ADR-017).
--  Дублировать эту арифметику по пяти вьюхам нельзя: разъедется, и
--  короткий спринт молча получит полный фонд.
-- --------------------------------------------------------------------
CREATE VIEW v_sprint_fund_factor AS
SELECT s.pi_id, s.sprint_no, s.start_date, s.end_date, s.length_days,
       ROUND(s.length_days::numeric / p.sprint_length_days, 4) AS factor
FROM sprints s
JOIN pi_periods p ON p.pi_id = s.pi_id;
COMMENT ON VIEW v_sprint_fund_factor IS
 'Фонд спринта = rate × fte_hours_per_sprint × factor. Короткий спринт даёт МЕНЬШЕ часов, '
 'а не «те же 80»: иначе фонд квартала вылез бы за 92 дня календаря. Проверки ENGINEER_OVERLOAD '
 'и ORBIT_OVERLOAD берут фонд именно отсюда.';

CREATE VIEW v_pi_fund_factor AS
SELECT p.pi_id,
       p.sprint_length_days,
       SUM(s.length_days)                                           AS days_total,
       ROUND(SUM(s.length_days)::numeric / p.sprint_length_days, 4) AS factor
FROM pi_periods p
JOIN sprints s ON s.pi_id = p.pi_id
GROUP BY p.pi_id, p.sprint_length_days;
COMMENT ON VIEW v_pi_fund_factor IS
 'Фонд ставки за весь PI, выраженный в «полных спринтах»: 1.0000 ставки × 80 ЧЧ × factor. '
 'На Q3-2026: 92 дня / 14 = 6.5714, то есть 525.71 ЧЧ за квартал (при 6 спринтах × 14 было 480). '
 'Используется вместо `sprint_count` везде, где считается фонд за квартал.';

CREATE VIEW v_remaining_pi_fund_factor AS
SELECT p.pi_id, COALESCE(u.last_reported_sprint, 0) AS last_reported_sprint,
       COALESCE(SUM(f.factor) FILTER (
           WHERE f.sprint_no > COALESCE(u.last_reported_sprint, 0)), 0) AS factor
FROM pi_periods p
LEFT JOIN (SELECT pi_id, MAX(sprint_no) AS last_reported_sprint
           FROM actual_uploads GROUP BY pi_id) u ON u.pi_id = p.pi_id
JOIN v_sprint_fund_factor f ON f.pi_id = p.pi_id
GROUP BY p.pi_id, u.last_reported_sprint;
COMMENT ON VIEW v_remaining_pi_fund_factor IS
 'Фонд только ещё не закрытых спринтов. Остаток работ нельзя сравнивать с фондом всего PI.';

-- --------------------------------------------------------------------
--  Ёмкость ядра в SP. Velocity × Focus Factor (онбординг, раздел 3А).
-- --------------------------------------------------------------------
CREATE VIEW v_team_capacity_sp AS
SELECT t.team_id,
       COUNT(h.*)                                            AS history_points,
       ROUND(AVG(h.velocity_achieved), 2)                    AS avg_velocity,
       t.focus_factor,
       ROUND(AVG(h.velocity_achieved) * t.focus_factor, 2)   AS available_sp_per_sprint,
       ROUND(AVG(h.velocity_achieved) * t.focus_factor
             * (SELECT factor FROM v_pi_fund_factor LIMIT 1), 2) AS available_sp_per_pi
FROM teams t
LEFT JOIN team_history h ON h.team_id = t.team_id
GROUP BY t.team_id, t.focus_factor;
COMMENT ON VIEW v_team_capacity_sp IS
 'history_points = 2 на команду: среднее шаткое, на защите оговорить. '
 'available_sp_per_sprint — фонд ОДНОГО ПОЛНОГО спринта; для короткого умножать на '
 'v_sprint_fund_factor.factor (так делает проверка SP_OVERFLOW).';

-- --------------------------------------------------------------------
--  Остаток часов по задаче и роли. Для InProgress факт берётся ТОЛЬКО
--  из task_role_spent — колонка tasks.spent_time у них пуста.
-- --------------------------------------------------------------------
CREATE VIEW v_task_remaining_hh AS
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

-- --------------------------------------------------------------------
--  Фонд часов спутника на орбите в спринте.
--  hours_own      — обязательство перед своим ядром;
--  hours_lendable — то же самое, но доступное другим ядрам как заём,
--                   если своё ядро часы не выбрало (ADR-001).
-- --------------------------------------------------------------------
CREATE VIEW v_satellite_capacity AS
SELECT o.engineer_id, o.team_id, e.role_id, e.grade,
       s.pi_id, s.sprint_no, s.start_date, s.end_date,
       o.capacity_rate,
       (SELECT COUNT(*) > 1 FROM engineer_orbits x WHERE x.engineer_id = o.engineer_id) AS is_shared_orbit,
       s.length_days,
       ROUND(o.capacity_rate * p.fte_hours_per_sprint * f.factor, 2) AS hours_own
FROM engineer_orbits o
JOIN engineers  e ON e.engineer_id = o.engineer_id
JOIN sprints    s ON TRUE
JOIN pi_periods p ON p.pi_id = s.pi_id
JOIN v_sprint_fund_factor f ON f.pi_id = s.pi_id AND f.sprint_no = s.sprint_no;
COMMENT ON VIEW v_satellite_capacity IS
 'hours_own — фонд спутника на орбите в КОНКРЕТНОМ спринте: rate × 80 × factor спринта. '
 'В коротком 7-м спринте это 0.5714 от обычного.';

-- --------------------------------------------------------------------
--  Предложение часов по роли: в разрезе ядра и по всей компании.
-- --------------------------------------------------------------------
CREATE VIEW v_role_supply_hh AS
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
COMMENT ON VIEW v_role_supply_hh IS
 'hh_per_sprint — фонд одного ПОЛНОГО спринта. hh_per_pi — фонд всего квартала: '
 '× v_pi_fund_factor.factor (92/14 = 6.5714), а НЕ × sprint_count, иначе короткий '
 '7-й спринт подарил бы команде лишние 8 дней фонда. hh_remaining_pi — фонд '
 'будущих спринтов после последнего принятого факта.';

-- --------------------------------------------------------------------
--  Потребность живого бэклога по ядру и роли за квартал.
-- --------------------------------------------------------------------
CREATE VIEW v_backlog_demand AS
SELECT t.team_id, r.role_id, r.canonical_name AS role_name,
       COUNT(DISTINCT t.task_id)          AS tasks,
       ROUND(SUM(rm.remaining_hours), 2)  AS demand_hh
FROM v_task_remaining_hh rm
JOIN tasks t ON t.task_id = rm.task_id
JOIN roles r ON r.role_id = rm.role_id
WHERE t.status IN ('ToDo', 'InProgress')
  AND rm.remaining_hours > 0
GROUP BY t.team_id, r.role_id, r.canonical_name;

-- --------------------------------------------------------------------
--  ГЛАВНАЯ ВИТРИНА: дефицит по связке «ядро × роль».
--  Именно она показывает, что без займов (ADR-001) план нерешаем.
-- --------------------------------------------------------------------
CREATE VIEW v_role_deficit AS
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

-- --------------------------------------------------------------------
--  Bus Factor. Роли без единого инженера тоже попадают сюда —
--  это самая опасная категория, её нельзя терять во INNER JOIN.
-- --------------------------------------------------------------------
CREATE VIEW v_bus_factor AS
SELECT r.role_id, r.canonical_name AS role_name, r.role_group,
       COUNT(DISTINCT e.engineer_id)                       AS bus_factor,
       COALESCE(ROUND(MAX(d.demand_hh), 2), 0)            AS demand_hh,
       CASE WHEN COUNT(DISTINCT e.engineer_id) = 0 THEN 'НЕТ В ШТАТЕ'
            WHEN COUNT(DISTINCT e.engineer_id) = 1 THEN 'КРИТИЧНО (BF=1)'
            ELSE 'ок' END                                  AS risk
FROM roles r
LEFT JOIN engineers e ON e.role_id = r.role_id
LEFT JOIN (SELECT role_id, SUM(demand_hh) AS demand_hh
             FROM v_backlog_demand GROUP BY role_id) d ON d.role_id = r.role_id
GROUP BY r.role_id, r.canonical_name, r.role_group;
COMMENT ON VIEW v_bus_factor IS
 'ПОКРЫТИЕ РОЛЕЙ: сколько инженеров на роль, включая роли без людей в штате (найм). '
 'Bus Factor по компетенциям, которого требует ТЗ, — v_bus_factor_skill (ADR-024).';

-- --------------------------------------------------------------------
--  Доска задач — денормализованная, чтобы бэкенд не джойнил руками.
-- --------------------------------------------------------------------
CREATE VIEW v_task_board AS
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

-- --------------------------------------------------------------------
--  Звёздная карта — отдаётся фронту как есть, без трансформации.
-- --------------------------------------------------------------------
CREATE VIEW v_orbit_map AS
SELECT e.engineer_id, r.canonical_name AS role_name, r.role_group, e.grade,
       e.total_capacity_rate,
       (SELECT COUNT(*) FROM engineer_orbits x WHERE x.engineer_id = e.engineer_id) AS orbit_count,
       ARRAY(SELECT o.team_id FROM engineer_orbits o
              WHERE o.engineer_id = e.engineer_id ORDER BY o.team_id)                AS teams,
       ARRAY(SELECT s.name FROM engineer_skills es JOIN skills s ON s.skill_id = es.skill_id
              WHERE es.engineer_id = e.engineer_id ORDER BY s.name)                  AS skills,
       bf.bus_factor, bf.risk
FROM engineers e
JOIN roles r        ON r.role_id = e.role_id
JOIN v_bus_factor bf ON bf.role_id = e.role_id;

-- --------------------------------------------------------------------
CREATE VIEW v_dq_summary AS
SELECT rule_code, severity, COUNT(*) AS n,
       MIN(detail) AS example
FROM dq_issues GROUP BY rule_code, severity ORDER BY
     CASE severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END, COUNT(*) DESC;

COMMIT;

-- =====================================================================
--  ЗАМЕЩЕНИЕ РОЛЕЙ (ADR-009).
--  Добавлено отдельным блоком: базовые витрины выше остаются «строгими»,
--  чтобы всегда можно было сравнить картину с замещением и без него.
-- =====================================================================
BEGIN;

DROP VIEW IF EXISTS v_plan_assignment_detail, v_role_deficit_effective,
     v_role_coverage_org, v_engineer_role_coverage CASCADE;

-- --------------------------------------------------------------------
--  ГЛАВНЫЙ ВХОД ДЛЯ ПЛАНИРОВЩИКА: какие роли может закрыть инженер.
--  Родная роль + разрешённые замещения. Строки с status='rejected'
--  не попадают. Бэкенду достаточно читать только эту вьюху.
-- --------------------------------------------------------------------
CREATE VIEW v_engineer_role_coverage AS
SELECT e.engineer_id, e.role_id, r.canonical_name AS role_name,
       TRUE  AS is_native, 1.00::numeric(3,2) AS efficiency,
       'основная роль'::text AS basis, 'confirmed'::text AS status
FROM engineers e JOIN roles r ON r.role_id = e.role_id
UNION ALL
SELECT e.engineer_id, s.required_role_id, r.canonical_name,
       FALSE, s.efficiency, s.rationale, s.status
FROM engineers e
JOIN role_substitutions s ON s.covering_role_id = e.role_id
JOIN roles r ON r.role_id = s.required_role_id
WHERE s.status <> 'rejected'
  AND CASE e.grade WHEN 'Senior' THEN 3 WHEN 'Middle' THEN 2 ELSE 1 END
   >= CASE s.min_grade WHEN 'Senior' THEN 3 WHEN 'Middle' THEN 2 ELSE 1 END;
COMMENT ON VIEW v_engineer_role_coverage IS
 'Кто какую роль может закрывать. is_native=false — замещение, показывать в UI явно. '
 'efficiency — множитель часов (сейчас везде 1.00). Планировщик ВПРАВЕ игнорировать неродные строки.';

-- --------------------------------------------------------------------
--  Дефицит с учётом замещения — рядом со строгим v_role_deficit.
-- --------------------------------------------------------------------
CREATE VIEW v_role_deficit_effective AS
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
COMMENT ON VIEW v_role_deficit_effective IS
 'Сравнивать с v_role_deficit (строгим). Разница между ними — ровно то, что даёт замещение.';

-- --------------------------------------------------------------------
--  ИТОГОВЫЙ СРЕЗ ПО КОМПАНИИ: что не закрыть НИКЕМ И НИГДЕ.
--  v_role_deficit_effective смотрит по командам и потому смешивает
--  «некому закрыть» с «человек в другой команде» — второе лечится
--  займами (ADR-001), а не наймом. Эта вьюха отвечает на вопрос найма.
-- --------------------------------------------------------------------
CREATE VIEW v_role_coverage_org AS
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
COMMENT ON VIEW v_role_coverage_org IS
 'Срез по всей компании: где нужен НАЙМ, а где хватит займов между командами. '
 'verdict=«только замещением» — роль держится исключительно на неродных исполнителях, '
 'это риск, показывать в UI.';

-- --------------------------------------------------------------------
--  Назначения с пометкой замещения. Контракт plan_assignments не
--  трогаем — признак выводится джойном, бэкенду писать ничего лишнего.
-- --------------------------------------------------------------------
CREATE VIEW v_plan_assignment_detail AS
SELECT a.run_id, a.task_id, a.sprint_no, a.engineer_id, a.hours,
       a.home_team_id, a.serving_team_id, a.is_loan,
       rq.canonical_name AS served_role,
       rn.canonical_name AS native_role,
       (a.role_id <> e.role_id) AS is_substitution,
       e.grade
FROM plan_assignments a
JOIN engineers e ON e.engineer_id = a.engineer_id
JOIN roles rq ON rq.role_id = a.role_id
JOIN roles rn ON rn.role_id = e.role_id;
COMMENT ON VIEW v_plan_assignment_detail IS
 'is_substitution — инженер работает не по своей роли. Обязательно показывать в UI: '
 '«всё спланировалось» без ответа «кем» на защите не проходит.';

COMMIT;

-- =====================================================================
--  ЗВЁЗДНАЯ КАРТА ПО ТЗ, ПРОФИЛИ КОМАНД, ПЕРЕСЧЁТ ПО ФАКТУ (ADR-021, 024)
--
--  ТЗ: «рассчитывать Bus Factor ПО КОМПЕТЕНЦИЯМ и выделять компетенции,
--  которыми владеет только один специалист… показать, где отсутствие одного
--  сотрудника создаёт риск»; «строить профили инженеров и команд»;
--  «пользователь должен понимать, какие отклонения вызвали изменения».
-- =====================================================================
BEGIN;

DROP VIEW IF EXISTS v_sprint_deviation, v_plan_diff, v_team_profile,
     v_plan_role_demand_snapshot, v_plan_task_progress,
     v_engineer_absence_risk, v_bus_factor_skill CASCADE;

-- --------------------------------------------------------------------
--  Подтверждённый спрос берётся из ручной разметки задача × роль × навык.
--  Для ещё не проверенных задач сохраняется оценка через роль, но помечается
--  как приближение. Один коллега без нужного навыка не снимает риск.
-- --------------------------------------------------------------------
CREATE VIEW v_bus_factor_skill AS
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
 'demand_source=confirmed — ручная разметка задач; role_proxy — приблизительная оценка '
 'по роли на непроверенном бэклоге; mixed — оба источника. '
 'Покрытие ролей (роли без людей в штате) — отдельно: v_bus_factor, v_role_coverage_org.';

-- --------------------------------------------------------------------
--  Где отсутствие одного сотрудника создаёт риск (по прогону).
--  tasks_without_backup — задачи прогона, которые инженер закрывает, а
--  второго человека с такой ролью в компании нет: он выпал — они встали.
-- --------------------------------------------------------------------
CREATE VIEW v_engineer_absence_risk AS
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

-- --------------------------------------------------------------------
--  Профиль команды: состав, роли, дыры, компетенции, ёмкость, бэклог.
-- --------------------------------------------------------------------
CREATE VIEW v_team_profile AS
WITH mem AS (
    SELECT o.team_id, o.engineer_id, o.capacity_rate, e.role_id
    FROM engineer_orbits o JOIN engineers e ON e.engineer_id = o.engineer_id
), fte_h AS (SELECT fte_hours_per_sprint AS h FROM pi_periods LIMIT 1)
SELECT tm.team_id,
       (SELECT COUNT(*) FROM mem m WHERE m.team_id = tm.team_id)::int                 AS members,
       (SELECT COUNT(*) FROM mem m WHERE m.team_id = tm.team_id
                                     AND m.capacity_rate < 1)::int                     AS part_time_members,
       (SELECT COALESCE(SUM(m.capacity_rate), 0) FROM mem m WHERE m.team_id = tm.team_id) AS fte,
       (SELECT COALESCE(SUM(m.capacity_rate), 0) FROM mem m WHERE m.team_id = tm.team_id)
         * (SELECT h FROM fte_h)                                                       AS hours_per_sprint,
       c.avg_velocity, c.available_sp_per_sprint, c.available_sp_per_pi,
       ARRAY(SELECT DISTINCT r.canonical_name FROM mem m JOIN roles r ON r.role_id = m.role_id
              WHERE m.team_id = tm.team_id ORDER BY 1)                                 AS roles_present,
       ARRAY(SELECT d.role_name FROM v_backlog_demand d
              WHERE d.team_id = tm.team_id
                AND NOT EXISTS (SELECT 1 FROM mem m
                                 WHERE m.team_id = d.team_id AND m.role_id = d.role_id)
              ORDER BY 1)                                                              AS roles_missing,
       (SELECT COUNT(DISTINCT es.skill_id) FROM mem m
          JOIN engineer_skills es ON es.engineer_id = m.engineer_id
         WHERE m.team_id = tm.team_id)::int                                            AS skills_n,
       ARRAY(SELECT DISTINCT b.skill_name FROM v_bus_factor_skill b
              JOIN mem m ON m.engineer_id = ANY (b.engineers)
              WHERE m.team_id = tm.team_id AND b.bus_factor = 1 ORDER BY 1)            AS unique_skills,
       (SELECT COUNT(*) FROM tasks t WHERE t.team_id = tm.team_id
                                       AND t.status IN ('ToDo','InProgress'))::int     AS live_tasks,
       (SELECT COALESCE(SUM(t.estimation_sp), 0) FROM tasks t
         WHERE t.team_id = tm.team_id AND t.status IN ('ToDo','InProgress'))           AS live_sp,
       (SELECT COALESCE(SUM(d.demand_hh), 0) FROM v_backlog_demand d
         WHERE d.team_id = tm.team_id)                                                 AS live_hh
FROM teams tm
LEFT JOIN v_team_capacity_sp c ON c.team_id = tm.team_id;
COMMENT ON VIEW v_team_profile IS
 'Профиль команды для звёздной карты. roles_missing — роли, которые нужны бэклогу команды, '
 'но в ней нет ни одного инженера (закрываются займом или наймом).';

-- --------------------------------------------------------------------
--  Что изменилось между прогоном и предыдущим — и почему.
--  cause: completed | own_slip (сама не закрылась к отчётному спринту) |
--  dependency (сдвинулась блокирующая) | capacity (ресурсы перераспределены)
-- --------------------------------------------------------------------
CREATE VIEW v_plan_role_demand_snapshot AS
SELECT d.run_id, d.task_id, d.role_id, r.canonical_name AS role_name,
       d.needed_hours
FROM plan_role_demand_snapshot d
JOIN roles r ON r.role_id = d.role_id;

-- SP are a team throughput budget, not a conversion from engineer hours.
-- Keep both streams visible for every sprint in a task's planned window.
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

CREATE VIEW v_plan_diff AS
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

-- --------------------------------------------------------------------
--  Отклонения факта спринта от плана, действовавшего в этом спринте.
-- --------------------------------------------------------------------
CREATE VIEW v_sprint_deviation AS
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

COMMIT;
