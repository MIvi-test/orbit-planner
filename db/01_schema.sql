-- =====================================================================
--  ПочтаТех PI-Planner · нормализованное ядро (вариант B)
--  Схема: public.  Полный сброс — секция DROP ниже.
--  Порядок применения: 01_schema.sql → 02_contract.sql → build/seed.sql
--                      → 03_substitutions.sql → 04_views.sql
--  Решения и допущения: docs/DECISIONS.md
-- =====================================================================
BEGIN;

-- ---------- полный сброс (ETL идемпотентен, датасет ожидается v2) ----
DROP FUNCTION IF EXISTS apply_actuals() CASCADE;
DROP TABLE IF EXISTS plan_dependency_bounds, plan_task_sp, kpi_snapshots, alerts, task_state, plan_assignments,
    plan_task_schedule, plan_baseline, plan_runs,
    task_goal_confirmations, plan_decision_goal_map, actual_report_issues, task_actual_spent, task_actuals, actual_uploads, task_role_spent_seed, tasks_seed_state,
    ref_decision_reasons,
    dq_issues, task_sequence, sprints, pi_periods, team_history,
    task_dependencies, task_role_skill_requirements, task_role_skill_reviews,
    task_role_spent, task_role_estimates, tasks, initiatives,
    engineer_skill_declarations, engineer_skills, engineer_orbits, engineers, teams,
    ref_closure_results, ref_mismatch_reasons, ref_result_options,
    role_substitutions, skill_aliases, skills, role_aliases, roles, load_batches CASCADE;

-- =====================================================================
--  0. СЛУЖЕБНОЕ
-- =====================================================================
CREATE TABLE load_batches (
    batch_id      SERIAL PRIMARY KEY,
    source_file   TEXT        NOT NULL,
    source_sha256 TEXT        NOT NULL,
    etl_version   TEXT        NOT NULL,
    pi_start      DATE        NOT NULL,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_counts    JSONB       NOT NULL DEFAULT '{}'::jsonb
);
COMMENT ON TABLE  load_batches IS 'Один прогон ETL. sha256 исходного xlsx — чтобы видеть, на какой версии датасета считали.';
COMMENT ON COLUMN load_batches.row_counts IS 'Счётчики строк по каждой целевой таблице, для быстрой сверки после перезалива.';

-- =====================================================================
--  1. СПРАВОЧНИКИ
-- =====================================================================
CREATE TABLE roles (
    role_id        SMALLSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    role_group     TEXT NOT NULL DEFAULT 'other'
        CHECK (role_group IN ('analysis','development','testing','ops','management','support','design','other'))
);
COMMENT ON TABLE roles IS 'Канонические ИТ-роли. Источник истины — строки матрицы сметы (блок Estimates).';

CREATE TABLE role_aliases (
    alias   TEXT     PRIMARY KEY,
    role_id SMALLINT NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE
);
COMMENT ON TABLE role_aliases IS
 'Разнописание ролей между блоками листа. В датасете v1: Девопс→ДевОпс, Разработчик IOS→Разработчик iOS, '
 'Разработчик BigData→Разработчик Big Data. Правится ДАННЫМИ, не кодом: добавь строку и перезалей.';

CREATE TABLE role_substitutions (
    required_role_id SMALLINT NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    covering_role_id SMALLINT NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    min_grade        TEXT     NOT NULL DEFAULT 'Middle' CHECK (min_grade IN ('Junior','Middle','Senior')),
    efficiency       NUMERIC(3,2) NOT NULL DEFAULT 1.00 CHECK (efficiency >= 1.00),
    status           TEXT     NOT NULL DEFAULT 'proposed'
                     CHECK (status IN ('proposed','confirmed','rejected')),
    rationale        TEXT     NOT NULL,
    PRIMARY KEY (required_role_id, covering_role_id),
    CHECK (required_role_id <> covering_role_id)
);
COMMENT ON TABLE role_substitutions IS
 'ВЗАИМОЗАМЕНЯЕМОСТЬ РОЛЕЙ. Кто может закрыть роль, которой в штате нет или не хватает. '
 'Это ВОЗМОЖНОСТЬ для планировщика, а не обязанность: алгоритм волен ею не пользоваться. '
 'Строки — решения, а не данные: каждую надо уметь защитить, поэтому rationale обязателен. См. ADR-009.';
COMMENT ON COLUMN role_substitutions.status IS
 'proposed = наша гипотеза, НЕ подтверждена авторами задачи; confirmed = согласовано на контрольной точке; '
 'rejected = запрещено. Планировщик игнорирует rejected. Правится одним UPDATE после контрольной точки.';
COMMENT ON COLUMN role_substitutions.min_grade IS
 'Замещать может только инженер не ниже этого грейда. Для руководителя проекта — Senior.';
COMMENT ON COLUMN role_substitutions.efficiency IS
 'Во сколько раз замещающий тратит больше часов. 1.00 = без потерь. Сейчас у всех 1.00 намеренно: '
 'придумывать коэффициенты без основания не стали, ручка оставлена под ответ авторов задачи.';

CREATE TABLE skills (
    skill_id        SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE
);
COMMENT ON COLUMN skills.normalized_name IS 'lower() + схлопнутые пробелы. Матчинг стека идёт по нему, name — первое встреченное написание.';
CREATE TABLE skill_aliases (
    alias_key TEXT NOT NULL,
    skill_id INT NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
    alias_text TEXT NOT NULL,
    rule TEXT NOT NULL CHECK (rule IN ('synonym','composite')),
    PRIMARY KEY (alias_key, skill_id)
);

CREATE TABLE ref_result_options   (code TEXT PRIMARY KEY, ord SMALLINT NOT NULL, label TEXT NOT NULL);
CREATE TABLE ref_mismatch_reasons (code TEXT PRIMARY KEY, ord SMALLINT NOT NULL, label TEXT NOT NULL);
CREATE TABLE ref_closure_results  (code TEXT PRIMARY KEY, ord SMALLINT NOT NULL, label TEXT NOT NULL);
CREATE TABLE plan_decision_goal_map (
    decision TEXT PRIMARY KEY CHECK (decision IN ('in_quarter','deferred_next_pi','cancelled')),
    proposal_action TEXT NOT NULL CHECK (proposal_action IN ('pursue_goal','defer','recommend_cancel')),
    fallback_result_code TEXT REFERENCES ref_result_options(code)
);
COMMENT ON TABLE ref_result_options IS 'Справочник «Варианты выбора цели» — в т.ч. статусы переноса/отмены для задач, не влезших в квартал.';
COMMENT ON TABLE ref_mismatch_reasons IS 'Причины расхождения планов заказчика и исполнителя. В датасете v1 не используется (заказчик=исполнитель везде) — задел под UI согласования.';

-- =====================================================================
--  2. ЯДРА И СПУТНИКИ  (модель «команда-ядро + инженеры-спутники»)
-- =====================================================================
CREATE TABLE teams (
    team_id      TEXT PRIMARY KEY,
    focus_factor NUMERIC(3,2) NOT NULL DEFAULT 0.80 CHECK (focus_factor > 0 AND focus_factor <= 1)
);
COMMENT ON TABLE  teams IS 'ЯДРО. Владеет только ёмкостью в Story Points. Часами владеют спутники (engineers).';
COMMENT ON COLUMN teams.focus_factor IS 'Из онбординга = 0.8. Вынесен в колонку, а не в константу, чтобы можно было крутить по командам.';

CREATE TABLE engineers (
    engineer_id         TEXT PRIMARY KEY,
    role_id             SMALLINT     NOT NULL REFERENCES roles(role_id),
    grade               TEXT         NOT NULL CHECK (grade IN ('Junior','Middle','Senior')),
    total_capacity_rate NUMERIC(3,2) NOT NULL CHECK (total_capacity_rate > 0 AND total_capacity_rate <= 1)
);
COMMENT ON TABLE  engineers IS
 'СПУТНИК. Роль, грейд и стек принадлежат инженеру, а не команде: проверено — у всех 4 парттаймеров '
 'атрибуты идентичны в обеих строках исходника. 30 уникальных инженеров из 34 строк листа.';
COMMENT ON COLUMN engineers.total_capacity_rate IS 'Сумма ставок по всем орбитам. У всех парттаймеров = 1.00 (0.5+0.5).';

CREATE TABLE engineer_orbits (
    engineer_id   TEXT         NOT NULL REFERENCES engineers(engineer_id) ON DELETE CASCADE,
    team_id       TEXT         NOT NULL REFERENCES teams(team_id)         ON DELETE CASCADE,
    capacity_rate NUMERIC(3,2) NOT NULL CHECK (capacity_rate > 0 AND capacity_rate <= 1),
    PRIMARY KEY (engineer_id, team_id)
);
COMMENT ON TABLE engineer_orbits IS
 'ОРБИТА: привязка спутника к ядру со ставкой. 34 строки / 30 инженеров — 4 висят на двух орбитах '
 '(ENG-405, ENG-406, ENG-419, ENG-426). Политика часов — «орбита с приоритетом», см. ADR-001.';

CREATE TABLE engineer_skills (
    engineer_id TEXT NOT NULL REFERENCES engineers(engineer_id) ON DELETE CASCADE,
    skill_id    INT  NOT NULL REFERENCES skills(skill_id)       ON DELETE CASCADE,
    PRIMARY KEY (engineer_id, skill_id)
);
COMMENT ON TABLE engineer_skills IS 'Звёздная карта: заявленный стек. Развёрнут из skills_declared по запятой (см. ADR-006 про «Java, Core»).';
CREATE TABLE engineer_skill_declarations (
    declaration_id BIGSERIAL PRIMARY KEY,
    engineer_id TEXT NOT NULL REFERENCES engineers(engineer_id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    skill_id INT NOT NULL REFERENCES skills(skill_id),
    source_row INT,
    UNIQUE (engineer_id, raw_text, skill_id, source_row)
);
COMMENT ON TABLE engineer_skill_declarations IS
 'Исходное написание навыка и связь с канонической компетенцией. Для составных выражений строк несколько.';

-- =====================================================================
--  3. БЭКЛОГ
-- =====================================================================
CREATE TABLE initiatives (
    prodf_id      TEXT PRIMARY KEY,
    br_id         TEXT NOT NULL UNIQUE,
    title         TEXT,
    priority_rung SMALLINT
);
COMMENT ON TABLE  initiatives IS 'Бизнес-инициатива заказчика. PRODF ↔ BR строго 1:1 (проверено на 15 инициативах).';
COMMENT ON COLUMN initiatives.priority_rung IS 'Скоринг инициативы = MAX(rung) её задач (ADR-005). У 7 из 15 rung внутри инициативы неоднороден.';

CREATE TABLE tasks (
    task_id                   TEXT PRIMARY KEY,
    prodf_id                  TEXT NOT NULL REFERENCES initiatives(prodf_id),
    team_id                   TEXT NOT NULL REFERENCES teams(team_id),
    summary                   TEXT,
    status                    TEXT NOT NULL CHECK (status IN ('ToDo','InProgress','Done')),
    rung                      SMALLINT,
    estimation_sp             SMALLINT,
    -- три источника трудозатрат; расходятся у 25 из 45 задач (ADR-002)
    estimated_hh_effective    NUMERIC(8,2) NOT NULL,
    estimated_hh_declared     NUMERIC(8,2),
    estimated_hh_matrix_total NUMERIC(8,2),
    spent_time_declared       NUMERIC(8,2),
    created_at                DATE,
    planned_start             DATE,
    planned_end               DATE,
    actual_start              DATE,
    actual_end                DATE,
    result_planned            TEXT REFERENCES ref_result_options(code),
    result_customer           TEXT REFERENCES ref_result_options(code),
    result_executor           TEXT REFERENCES ref_result_options(code),
    result_final              TEXT REFERENCES ref_closure_results(code),
    committed_week0           BOOLEAN NOT NULL DEFAULT FALSE
);
COMMENT ON COLUMN tasks.estimated_hh_effective IS
 'ВЫБРАННАЯ ИСТИНА = сумма столбца матрицы сметы (ADR-002). Именно она раскладывается по людям.';
COMMENT ON COLUMN tasks.committed_week0 IS
 'Колонка «будет включено в спринт». В датасете v1 заполнена ТОЛЬКО у 8 задач Done, поэтому для KPI '
 'непригодна — реальная базовая линия фиксируется в plan_baseline первым прогоном (ADR-004).';
CREATE INDEX ix_tasks_status  ON tasks(status);
CREATE INDEX ix_tasks_team    ON tasks(team_id);
CREATE INDEX ix_tasks_prodf   ON tasks(prodf_id);

CREATE TABLE task_goal_confirmations (
    confirmation_id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    goal_code TEXT REFERENCES ref_result_options(code),
    closure_code TEXT NOT NULL REFERENCES ref_closure_results(code),
    confirmed_by TEXT NOT NULL CHECK (btrim(confirmed_by) <> ''),
    note TEXT NOT NULL CHECK (btrim(note) <> ''),
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (closure_code <> 'ACHIEVED' OR (goal_code IS NOT NULL AND goal_code ~ '^R[1-6]$'))
);
CREATE INDEX ix_task_goal_confirmations_latest ON task_goal_confirmations(task_id, confirmed_at DESC, confirmation_id DESC);

CREATE TABLE task_role_estimates (
    task_id TEXT         NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    role_id SMALLINT     NOT NULL REFERENCES roles(role_id),
    hours   NUMERIC(8,2) NOT NULL CHECK (hours > 0),
    PRIMARY KEY (task_id, role_id)
);
COMMENT ON TABLE task_role_estimates IS 'Матрица сметы 22×45, развёрнутая в long. Нулевые ячейки не хранятся.';

CREATE TABLE task_role_skill_reviews (
    task_id TEXT NOT NULL,
    role_id SMALLINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('proposed','confirmed')),
    source_text TEXT NOT NULL CHECK (btrim(source_text) <> ''),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    PRIMARY KEY (task_id, role_id),
    FOREIGN KEY (task_id, role_id) REFERENCES task_role_estimates(task_id, role_id) ON DELETE CASCADE,
    CHECK (status <> 'confirmed' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE TABLE task_role_skill_requirements (
    task_id TEXT NOT NULL,
    role_id SMALLINT NOT NULL,
    skill_id INT NOT NULL REFERENCES skills(skill_id),
    source_text TEXT NOT NULL CHECK (btrim(source_text) <> ''),
    PRIMARY KEY (task_id, role_id, skill_id),
    FOREIGN KEY (task_id, role_id) REFERENCES task_role_skill_reviews(task_id, role_id) ON DELETE CASCADE
);
COMMENT ON TABLE task_role_skill_reviews IS
 'Ручная проверка стека для задачи и роли. Отсутствие записи означает неизвестные требования, '
 'confirmed без строк требований означает подтверждённое отсутствие технологических ограничений.';

CREATE TABLE task_role_spent (
    task_id TEXT         NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    role_id SMALLINT     NOT NULL REFERENCES roles(role_id),
    hours   NUMERIC(8,2) NOT NULL CHECK (hours >= 0),
    PRIMARY KEY (task_id, role_id)
);
CREATE TABLE task_role_etc (
    revision_id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    role_id SMALLINT NOT NULL,
    remaining_hours NUMERIC(8,2) NOT NULL CHECK (remaining_hours >= 0),
    reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (task_id, role_id) REFERENCES task_role_estimates(task_id, role_id) ON DELETE CASCADE
);
CREATE INDEX ix_task_role_etc_latest ON task_role_etc(task_id, role_id, revision_id DESC);
COMMENT ON TABLE task_role_spent IS
 'Факт по ролям (блок Spent_time_roles), только для 6 задач InProgress. Колонка tasks.spent_time у них пуста — '
 'остаток считается ТОЛЬКО отсюда, см. v_task_remaining_hh.';

CREATE TABLE task_dependencies (
    blocking_task_id TEXT     NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    blocked_task_id  TEXT     NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    raw_type         TEXT     NOT NULL,
    min_gap_sprints  SMALLINT NOT NULL DEFAULT 1 CHECK (min_gap_sprints >= 1),
    PRIMARY KEY (blocking_task_id, blocked_task_id),
    CHECK (blocking_task_id <> blocked_task_id)
);
COMMENT ON TABLE task_dependencies IS
 'Канонизировано как «A блокирует B» по заголовкам колонок листа. Все 3 типа (has to be done before / '
 'is required for / depends on) семантически одинаковы — проверено по смыслу задач, A везде предшествует B (ADR-003).';

CREATE TABLE team_history (
    team_id           TEXT     NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    snapshot_date     DATE     NOT NULL,
    velocity_achieved NUMERIC(6,2) NOT NULL,
    planned_sp        NUMERIC(6,2) NOT NULL,
    PRIMARY KEY (team_id, snapshot_date)
);
COMMENT ON TABLE team_history IS 'По 2 снимка на команду. Выборка мала — среднее velocity статистически шаткое, оговорить на защите.';

-- =====================================================================
--  4. КАЛЕНДАРЬ PI
-- =====================================================================
CREATE TABLE pi_periods (
    pi_id              TEXT PRIMARY KEY,
    start_date         DATE     NOT NULL,
    end_date           DATE     NOT NULL,
    sprint_count       SMALLINT NOT NULL DEFAULT 6,
    sprint_length_days SMALLINT NOT NULL DEFAULT 14,
    fte_hours_per_sprint SMALLINT NOT NULL DEFAULT 80,
    CHECK (end_date > start_date)
);
CREATE TABLE sprints (
    pi_id      TEXT     NOT NULL REFERENCES pi_periods(pi_id) ON DELETE CASCADE,
    sprint_no  SMALLINT NOT NULL CHECK (sprint_no BETWEEN 1 AND 12),
    start_date DATE     NOT NULL,
    end_date   DATE     NOT NULL,
    -- Генерируемая: длина спринта — единственный источник множителя фонда
    -- (`v_pi_fund_factor`). Считать её руками в ETL нельзя — разъедется
    -- с датами, и фонд спринта станет неверным молча.
    length_days SMALLINT GENERATED ALWAYS AS ((end_date - start_date) + 1) STORED,
    PRIMARY KEY (pi_id, sprint_no),
    CHECK (end_date >= start_date)
);
COMMENT ON COLUMN pi_periods.fte_hours_per_sprint IS
 'Из онбординга: 1.0 ставки = 80 ЧЧ за 2-недельный спринт (уже с учётом Focus Factor). '
 'Лежит в данных, а не в коде вьюх, — чтобы менялось одной строкой.';
COMMENT ON TABLE pi_periods IS
 'PI начинается 01.07.2026 и длится шесть двухнедельных спринтов до 22.09.2026 (ADR-025). '
 'Фонд ставки = 6 × 80 = 480 ЧЧ; остаток календарного квартала не входит в PI.';
COMMENT ON TABLE sprints IS
 'Шесть двухнедельных спринтов от PI_START до PI_END; календарь задаётся текущей спецификацией.';
COMMENT ON COLUMN sprints.length_days IS
 'Длина спринта в днях (включительно). Генерируемая колонка: ETL её не пишет. '
 'Множитель фонда = length_days / pi_periods.sprint_length_days.';

-- =====================================================================
--  5. ПРЕДРАСЧЁТ ГРАФА ЗАВИСИМОСТЕЙ
-- =====================================================================
CREATE TABLE task_sequence (
    task_id               TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE CASCADE,
    topo_order            INT      NOT NULL,
    depth                 SMALLINT NOT NULL,
    earliest_start_sprint SMALLINT,
    on_longest_edge_chain      BOOLEAN  NOT NULL DEFAULT FALSE
);
COMMENT ON TABLE task_sequence IS
 'Порядок и длина цепочки на момент загрузки датасета. Планировщик пересчитывает '
 'допустимые старты живого графа по фактическим датам при каждом прогоне.';

-- =====================================================================
--  6. КАЧЕСТВО ДАННЫХ
-- =====================================================================
CREATE TABLE dq_issues (
    issue_id  SERIAL PRIMARY KEY,
    batch_id  INT  NOT NULL REFERENCES load_batches(batch_id) ON DELETE CASCADE,
    entity    TEXT NOT NULL,
    entity_id TEXT,
    rule_code TEXT NOT NULL,
    severity  TEXT NOT NULL CHECK (severity IN ('info','warning','error')),
    detail    TEXT NOT NULL
);
COMMENT ON TABLE dq_issues IS 'Журнал находок ETL. Не блокирует загрузку — материал для слайда «что не так с исходными данными».';
CREATE INDEX ix_dq_rule ON dq_issues(rule_code);

-- =====================================================================
--  7. ПРИЧИНЫ РЕШЕНИЙ ПЛАНИРОВЩИКА (ADR-022)
--  ТЗ: «объяснять причины включения, переноса и отмены задач».
--  Статичный справочник: живёт в схеме, ETL его не трогает.
-- =====================================================================
CREATE TABLE ref_decision_reasons (
    code          TEXT PRIMARY KEY,
    ord           SMALLINT NOT NULL,
    decision      TEXT     NOT NULL CHECK (decision IN ('in_quarter','deferred_next_pi','cancelled')),
    label         TEXT     NOT NULL,
    legacy_reason TEXT  -- без FK: seed.sql делает TRUNCATE ref_mismatch_reasons CASCADE и снёс бы справочник
);
COMMENT ON TABLE ref_decision_reasons IS
 'Почему задача включена, перенесена или отменена. Текст для конкретной задачи — '
 'plan_task_schedule.reason_text, разбивка — reason_details. legacy_reason — старый код '
 'из справочника расхождений (M2/M3/M4), оставлен для совместимости контракта.';

-- =====================================================================
--  8. ФАКТ СПРИНТОВ (ADR-021)
--  ТЗ: «раз в две недели пользователь загружает фактические результаты
--  очередного спринта». Загрузки закрытых спринтов — замещаемый журнал; текущее состояние
--  tasks / task_role_spent ВОСПРОИЗВОДИТСЯ из снимка исходного датасета
--  плюс все загрузки по порядку (apply_actuals). Поэтому перезагрузка
--  факта за спринт безопасна: состояние пересобирается с нуля.
-- =====================================================================
CREATE TABLE tasks_seed_state (
    task_id      TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE CASCADE,
    status       TEXT NOT NULL,
    actual_start DATE,
    actual_end   DATE
);
CREATE TABLE task_role_spent_seed (
    task_id TEXT         NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    role_id SMALLINT     NOT NULL REFERENCES roles(role_id),
    hours   NUMERIC(8,2) NOT NULL CHECK (hours >= 0),
    PRIMARY KEY (task_id, role_id)
);
COMMENT ON TABLE tasks_seed_state IS
 'Состояние задач ровно как в загруженном датасете. Точка отсчёта для воспроизведения факта.';

CREATE TABLE actual_uploads (
    upload_id     SERIAL PRIMARY KEY,
    pi_id         TEXT        NOT NULL REFERENCES pi_periods(pi_id) ON DELETE CASCADE,
    sprint_no     SMALLINT    NOT NULL CHECK (sprint_no BETWEEN 1 AND 12),
    plan_run_id   INT,
    source_file   TEXT        NOT NULL,
    source_sha256 TEXT        NOT NULL,
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    coverage_status TEXT      NOT NULL DEFAULT 'complete'
        CHECK (coverage_status IN ('draft', 'incomplete', 'complete')),
    UNIQUE (pi_id, sprint_no)
);
COMMENT ON TABLE actual_uploads IS
 'Одна загрузка = факт одного спринта. Повторная загрузка за тот же спринт заменяет прежнюю '
 'и все более поздние (иначе факт спринта 3 висел бы на старом факте спринта 2).';

CREATE TABLE task_actuals (
    upload_id    INT  NOT NULL REFERENCES actual_uploads(upload_id) ON DELETE CASCADE,
    task_id      TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    status       TEXT NOT NULL CHECK (status IN ('ToDo','InProgress','Done')),
    actual_start DATE,
    actual_end   DATE,
    completed_sp NUMERIC(6,2) CONSTRAINT task_actuals_completed_sp_nonnegative
        CHECK (completed_sp >= 0),
    comment      TEXT,
    clear_actual_start BOOLEAN NOT NULL DEFAULT FALSE,
    clear_actual_end   BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (NOT clear_actual_start OR actual_start IS NULL),
    CHECK (NOT clear_actual_end OR actual_end IS NULL),
    PRIMARY KEY (upload_id, task_id)
);
CREATE TABLE task_actual_spent (
    upload_id INT          NOT NULL REFERENCES actual_uploads(upload_id) ON DELETE CASCADE,
    task_id   TEXT         NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    role_id   SMALLINT     NOT NULL REFERENCES roles(role_id),
    hours     NUMERIC(8,2) NOT NULL CHECK (hours >= 0),
    PRIMARY KEY (upload_id, task_id, role_id)
);
COMMENT ON TABLE task_actual_spent IS 'Часы, потраченные ЗА ЭТОТ спринт (не накопительно). Складываются по загрузкам.';

CREATE TABLE actual_report_issues (
    upload_id INT NOT NULL REFERENCES actual_uploads(upload_id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    role_id SMALLINT REFERENCES roles(role_id),
    issue_code TEXT NOT NULL CHECK (issue_code IN
        ('UNPLANNED_ROLE', 'ROLE_OVERRUN', 'TODO_WITH_HOURS', 'DONE_WITH_NEW_HOURS', 'STATUS_REGRESSION')),
    detail TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
    resolved_revision_id BIGINT REFERENCES task_role_etc(revision_id)
);
CREATE INDEX ix_actual_report_issues_upload ON actual_report_issues(upload_id);

CREATE FUNCTION apply_actuals() RETURNS void LANGUAGE plpgsql AS $fn$
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
COMMENT ON FUNCTION apply_actuals() IS
 'Пересобирает статус, независимые события дат и накопленные часы из seed и журнала. '
 'Пустая дата сохраняет прежнюю, clear_* явно очищает поле.';

COMMIT;

-- справочник причин — статичный, вне основной транзакции не нужен, но и
-- ETL его не перезаписывает: TRUNCATE в seed.sql его не касается.
INSERT INTO ref_decision_reasons (code, ord, decision, label, legacy_reason) VALUES
  ('PLANNED',              1, 'in_quarter',       'Включена в квартал: хватает ролей, часов и ёмкости команды', NULL),
  ('ROLE_NOT_IN_STAFF',    2, 'deferred_next_pi', 'В штате нет требуемой роли — нужен наём или дообучение',     'M2'),
  ('ROLE_HOURS_EXHAUSTED', 3, 'deferred_next_pi', 'Не хватает часов специалистов роли до конца квартала',      'M2'),
  ('SKILL_UNAVAILABLE',    10, 'deferred_next_pi', 'Нет инженера с подтверждённым стеком задачи',              'M2'),
  ('TEAM_SP_EXHAUSTED',    4, 'deferred_next_pi', 'Не хватает ёмкости команды в Story Points',                 'M2'),
  ('BLOCKED_BY_DEFERRED',  5, 'deferred_next_pi', 'Ждёт задачу, которая сама перенесена',                      'M3'),
  ('INITIATIVE_ATOMIC',    6, 'deferred_next_pi', 'Перенесена вместе со своей инициативой',                    'M2'),
  ('PI_CLOSED',            7, 'deferred_next_pi', 'Квартал завершён — остаток уходит в следующий PI',          'M2'),
  ('NOT_FEASIBLE_NEXT_PI', 8, 'cancelled',        'Не помещается и в следующий квартал — рекомендуем отменить или пересогласовать', 'M4');
INSERT INTO ref_decision_reasons (code, ord, decision, label, legacy_reason) VALUES
  ('ETC_REQUIRED', 9, 'deferred_next_pi', 'Нужно уточнить остаток работ или статус задачи', 'M2');
