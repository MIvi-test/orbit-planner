# Схема БД: что читать бэкенду

Схема `public` (плюс отдельные схемы PostgreSQL для каждого PI и сценария, см. §5).
Бэкенду нужны не все объекты — ниже то, что стоит отдавать наружу. Точный состав
вьюх и колонок всегда виден в SQL (`db/01_schema.sql` … `db/05_invariants.sql`) и в
`GET /api/views`. Правила планирования — [PLANNER_SPEC.md](PLANNER_SPEC.md), обзор
алгоритмов — [ALGORITHMS.md](ALGORITHMS.md).

Правило разделения: **слой данных пишет, бэкенд читает.** Пишут только явные
транзакции планировщика и загрузок (ADR-021); сессии чтения read-only.

---

## 1. Справочный слой — отдаётся во фронт как есть

| Таблица / вьюха | Что внутри |
|---|---|
| `v_task_board` | **Доска задач, денормализована.** Задача, инициатива, приоритет, остаток часов, позиция в графе. Джойнить ничего не надо |
| `v_orbit_map` | **Звёздная карта.** Инженер, роль, грейд, массив команд, массив навыков, bus factor. Фронт строит граф прямо отсюда |
| `v_team_capacity_sp` | Ёмкость команды в SP: velocity, focus factor, доступно на спринт и на квартал |
| `v_role_deficit` | **Главная аналитическая витрина.** Дефицит по связке «команда × роль» с вердиктом |
| `v_bus_factor` | Незаменимость по ролям, включая роли, которых нет в штате вообще |
| `v_bus_factor_skill` | **Bus Factor по компетенциям**: носители навыка, риск, критичность, источник спроса |
| `v_engineer_absence_risk` | Профиль инженера и задачи прогона, у которых нет запасного исполнителя |
| `v_team_profile` | Профиль команды: состав, роли, `roles_missing`, компетенции, ёмкость, бэклог |
| `sprints` | Сетка квартала: номер спринта, даты, `length_days` (генерируемая колонка) |
| `initiatives` | Инициативы PRODF со скорингом и явным бизнес-приоритетом |
| `ref_result_options` | Справочник «Варианты выбора цели» |
| `v_dq_summary`, `v_dq_issue_worklist` | Сводка и рабочий список находок качества исходных данных |

### Календарь и фонд часов (ADR-007, ADR-017, ADR-025)

Квартал `PI-2026-Q3` — 01.07.2026–22.09.2026: шесть спринтов по 14 дней, 84 дня.
Фонд часов пропорционален длине спринта, поэтому множитель нельзя «посчитать по
числу спринтов».

| Вьюха | Что даёт | На Q3-2026 |
|---|---|---|
| `v_sprint_fund_factor` | множитель фонда спринта: `length_days / sprint_length_days` | все шесть спринтов — 1,0000 |
| `v_pi_fund_factor` | множитель фонда всего PI: `Σ length_days / sprint_length_days`, `days_total` | 6,0000, 84 дня → 480 ЧЧ на ставку |
| `sprints.length_days` | длина спринта в днях (генерируемая колонка, ETL её не пишет) | 14 для каждого |

Фонд **одного** спринта лежит в `v_team_capacity_sp.available_sp_per_sprint` и в
`v_satellite_capacity.hours_own` (он уже умножен на множитель своего спринта);
ёмкость команды в SP для спринта другой длины умножайте на
`v_sprint_fund_factor.factor` — так делает проверка `SP_OVERFLOW`. Фонд **всего
квартала** — `available_sp_per_pi` и `v_role_supply_hh.hh_per_pi`: они уже посчитаны
через `v_pi_fund_factor`.

> Бэкенду арифметику фонда повторять не надо и **нельзя**: единственный источник
> правды — эти две вьюхи, иначе фонд разъедется с инвариантами. Готовые границы
> прогона — в `plan_runs.params.calendar`.

### Взаимозаменяемость ролей (ADR-009, ADR-010)

| Вьюха | Для чего |
|---|---|
| **`v_engineer_role_coverage`** | **Главный вход планировщика.** Какие роли может закрывать инженер: родную и разрешённые замещения. `is_native = false` — замещение, `efficiency` — множитель часов. Читать только эту вьюху: одного `engineers.role_id` не хватит |
| `v_role_coverage_org` | Срез по компании: где нужен **наём**, а где хватит займов |
| `v_role_deficit_effective` | Дефицит по командам с учётом замещения; сравнивать со строгим `v_role_deficit` |
| `v_plan_assignment_detail` | Назначения с флагами `is_loan` и `is_substitution`. Показывать в UI: «всё спланировалось» без ответа «кем» не принимается |

Правила лежат в таблице `role_substitutions` со `status`: `proposed`, `confirmed`,
`rejected`. Сейчас все строки `rejected`: замещения запрещены, человека можно только
дообучить (ADR-010). Планировщик игнорирует `rejected`, поэтому
`v_engineer_role_coverage` отдаёт только родные роли (`is_native = true`). Механизм
включается обратно правкой `db/03_substitutions.sql`.

---

## 2. Контракт планировщика — главное для бэкенда

Всё, что пишет планировщик. Структура заморожена: менять только предупредив.

```
plan_runs ──┬── plan_baseline          базовая линия Недели 0 (для KPI)
            ├── plan_task_schedule     какая задача в какие спринты, какое решение
            ├── plan_task_sp           доли Story Points по спринтам
            ├── plan_assignments       кто, на что, сколько часов + флаг займа
            ├── plan_dependency_bounds допустимая нижняя граница старта по зависимостям
            ├── plan_role_demand_snapshot  спрос по ролям на момент прогона
            ├── plan_team_capacity     ёмкость команд, с которой построен прогон
            ├── task_state             слепок задачи на каждый пересчёт
            ├── alerts                 три типа рисков
            └── kpi_snapshots          KPI с нормами
```

* **`plan_runs.run_id` — ось всего.** Каждый пересчёт создаёт новый `run_id`, старые
  не трогаются. Фронт всегда показывает конкретный прогон; «текущий» — последний
  опубликованный `ok` или `infeasible`.
* **Публикация прогона.** План записывается со статусом `failed`, а проверка
  `v_plan_violations` выполняется в той же транзакции. Только при отсутствии ошибок
  статус становится `ok`. При ошибках сохраняются диагностический прогон и
  `params.validation`; API отвечает 422, CLI завершает работу с кодом 1. Прежний
  активный прогон остаётся активным.
* **`plan_runs.status = 'ok'`** означает, что расчёт завершился и опубликован, даже
  если в квартале не осталось задач или ничего не поместилось. Бизнес-результат
  хранится в `plan_runs.params.business_outcome`: `completed`, `planned`, `partial`
  или `nothing_scheduled`.
* **`plan_assignments.is_loan`** считает СУБД (`home_team_id <> serving_team_id`);
  не вычислять на своей стороне.
* **`plan_task_schedule.decision`** — `in_quarter`, `deferred_next_pi` или
  `cancelled` (только рекомендация). У каждой строки есть `reason_code`,
  `reason_text`, `reason_details`; код расшифровывает `ref_decision_reasons`.
* **`alerts.level`**: `red` (срыв дедлайна), `yellow` (каскадный сдвиг), `orange`
  (дефицит по роли). `payload` — свободный JSONB с деталями.
* **`kpi_snapshots`** несёт `target_min` и `target_max` рядом со значением; `kind` —
  `forecast` или `actual` (входит в первичный ключ). Не зашивайте пороги во фронте.
* `plan_runs.actuals_upload_id` — на каком факте построен пересчёт.

### Приёмка плана

```sql
SELECT * FROM v_plan_violations WHERE run_id = :run_id AND severity = 'error';
```

Проверки лежат в `db/05_invariants.sql`, правила — [PLANNER_SPEC.md](PLANNER_SPEC.md),
раздел 7. `severity = 'error'` блокирует публикацию, `'warning'` требует показа в
интерфейсе: `SUBSTITUTION_USED` (инженер работает не по своей роли),
`PLANNED_END_OVERSAIL` (прогноз выходит за даты исходного плана) и `WINDOW_HAS_GAP`
(в окне задачи есть спринт без назначений).

### API для фронта — один маршрут на все витрины

Фронт получает данные из схемы только через `app/views.py` (ADR-019):

```
GET /api/views                                            # справочник витрин
GET /api/views/{view}?run_id=&limit=&offset=&order=       # строка витрины как есть
```

Один маршрут, а не маршрут на витрину: набор меток `route` в метриках заморожен
(ADR-018). `run_id` фильтрует только источники контракта; `plan_runs` намеренно не
фильтруется — она нужна, чтобы прогон выбрать. Без `run_id` подставляется последний
удачный, и в ответе это видно как `run_default: true`.

Наружу не отдаются внутренняя кухня ETL (§3) и промежуточные вьюхи
(`v_role_supply_hh`, `v_backlog_demand`): у экранов есть готовые витрины с
вердиктом. Формат конверта, типы и коды ответов — [UI_SPEC.md](UI_SPEC.md), раздел 0.

---

## 3. Внутренняя кухня ETL — бэкенду не нужна

`load_batches`, `dq_issues`, `role_aliases`, `task_sequence`,
`task_role_estimates`, `task_role_spent`, `skills`, `engineer_skills`,
`team_history`, `pi_periods`, `source_provenance`. Лежат в той же БД, читать можно,
но наружу отдавать нечего: границы PI и длины спринтов бэкенд получает через
`sprints`, `v_pi_fund_factor` и `v_sprint_fund_factor`, они же продублированы в
`plan_runs.params.calendar`.

---

## 4. Загрузки, факт и редакции (ADR-021, ADR-034)

| Маршрут | Что делает |
|---|---|
| `POST /api/dataset?filename=x.xlsx` | тело — xlsx датасета: ETL, полная заливка, базовый план; прежние прогоны и факт стираются |
| `GET /api/actuals/template?sprint=N` | CSV-шаблон факта: живые задачи и колонки ролей |
| `POST /api/actuals?sprint=N&filename=…` | тело — CSV или XLSX факта: проверка, журнал, пересборка состояния, пересчёт на спринт N+1 |
| `GET /api/upload-revisions`, `/file?id=…`, `/snapshot?id=…` | история загрузок и архив исходных файлов |

Ответы: `200` — сводка и результат прогона; `400 bad_upload` — файл не принят, в
теле `problems` со списком проблем по строкам; `503` — база недоступна.
`POST /api/dataset` и `/api/actuals` принимают необязательный `Idempotency-Key`:
повтор с тем же ключом и файлом возвращает сохранённый ответ; тот же ключ с другим
файлом отклоняется.

| Таблица | Что внутри |
|---|---|
| `actual_uploads` | журнал загрузок: один спринт — одна строка, `coverage_status` |
| `task_actuals` | статус и даты задачи по загрузке |
| `task_actual_spent` | часы по ролям **за этот спринт** (не накопительно) |
| `actual_report_issues` | исключения факта с причиной (новая роль, перерасход, часы у `ToDo`, возврат статуса) |
| `tasks_seed_state`, `task_role_spent_seed` | снимок датасета — точка отсчёта воспроизведения |
| `upload_revisions` | исходные байты каждой загрузки, `superseded_by`, ответ по `Idempotency-Key`, снимок KPI и расписания заменённого отчёта |
| `task_role_etc` | версионированная оценка остатка по роли с причиной |
| `engineer_orbit_availability` | ставка конкретной орбиты в спринте с источником; без записи действует штатная ставка |
| `engineer_role_qualifications` | подтверждённая дополнительная квалификация с датами; замещение роли не разрешает |
| `ref_decision_reasons` | справочник причин решений планировщика |
| `app_users`, `audit_log` | пользователи сервиса (SHA-256 токена) и журнал действий, меняющих данные |

Явный бизнес-приоритет инициативы — `initiatives.business_priority` (плюс `_by`, `_at`,
`_note`, ADR-032). Автор загрузки хранится в `load_batches.loaded_by`,
`actual_uploads.uploaded_by`, `task_role_etc.revised_by`.

`apply_actuals()` пересобирает текущее состояние `tasks` и `task_role_spent` из
снимка плюс закрытые загрузки по порядку. Функция идемпотентна, поэтому повторная
загрузка факта за спринт безопасна. После исправления старого отчёта более поздние
отчёты нужно заново загрузить из архива по порядку: автоматического переигрывания
нет.

Маршруты `GET/POST /api/engineers/availability`, `/api/engineers/qualifications` и
`GET/POST /api/tasks/skill-review` обслуживают календарь доступности, квалификации
и требования стека задач; изменение календаря и подтверждение требований
пересчитывают план.

### Витрины по факту и истории

| Витрина | Для чего |
|---|---|
| `v_plan_diff` | что изменилось против предыдущего прогона и почему (`cause`) |
| `v_sprint_deviation` | факт спринта против плана, который в нём действовал |
| `v_sprint_forecast_accuracy` | прогноз перед спринтом против факта |
| `v_plan_task_progress` | работа и доли SP по спринтам для задачи |
| `v_plan_goal_outcome`, `v_initiative_goal_progress` | цель исполнителя и заказчика, предложение плана, подтверждённый результат |
| `v_team_velocity_observed`, `v_task_done_sprint` | наблюдаемая скорость закрытых спринтов и спринт завершения задачи |

---

## 5. Контексты PI и сценарии

Каждый PI и сценарий хранится в отдельной схеме PostgreSQL; реестр —
`public.pi_contexts` (имя схемы и SHA-256 датасета). Исходный набор остаётся в
`public` как сценарий `main`. Выбор контекста в запросе — заголовки `X-PI-ID` и
`X-Scenario-ID`; создаёт новый контекст `POST /api/pi-contexts` (роль `admin`).

---

## Примеры запросов

**Текущий прогон и его KPI:**
```sql
WITH cur AS (SELECT MAX(run_id) AS run_id FROM plan_runs WHERE status IN ('ok', 'infeasible'))
SELECT k.kpi_code, k.kind, k.value, k.target_min, k.target_max
FROM kpi_snapshots k JOIN cur ON cur.run_id = k.run_id
WHERE k.sprint_no = (SELECT MAX(sprint_no) FROM kpi_snapshots WHERE run_id = cur.run_id);
```

**Гант: задачи текущего прогона по спринтам:**
```sql
SELECT s.task_id, b.summary, b.team_id, b.priority_rung,
       s.start_sprint, s.end_sprint, s.decision
FROM plan_task_schedule s
JOIN v_task_board b USING (task_id)
WHERE s.run_id = $1 AND s.decision = 'in_quarter'
ORDER BY s.start_sprint, b.priority_rung DESC;
```

**Календарь квартала и множители фонда:**
```sql
SELECT s.sprint_no, s.start_date, s.end_date, s.length_days, f.factor
FROM sprints s
JOIN v_sprint_fund_factor f USING (pi_id, sprint_no)
JOIN (SELECT pi_id FROM pi_periods ORDER BY start_date DESC LIMIT 1) p USING (pi_id)
ORDER BY s.sprint_no;
```

**Что перенесли и почему:**
```sql
SELECT b.prodf_id, s.task_id, b.summary, b.priority_rung,
       s.decision, s.reason_code, r.label AS reason, s.reason_text
FROM plan_task_schedule s
JOIN v_task_board b USING (task_id)
LEFT JOIN ref_decision_reasons r ON r.code = s.reason_code
WHERE s.run_id = $1 AND s.decision <> 'in_quarter'
ORDER BY b.priority_rung DESC;
```

**Займы между командами в спринте:**
```sql
SELECT sprint_no, home_team_id, serving_team_id, engineer_id, SUM(hours) AS hh
FROM plan_assignments
WHERE run_id = $1 AND is_loan
GROUP BY 1,2,3,4 ORDER BY sprint_no, hh DESC;
```

**Лента алертов:**
```sql
SELECT sprint_no, level, alert_type, entity_type, entity_id, message, payload
FROM alerts WHERE run_id = $1
ORDER BY sprint_no,
         CASE level WHEN 'red' THEN 1 WHEN 'orange' THEN 2 ELSE 3 END;
```

---

## Чего в данных нет

* **Связи «задача → требуемые навыки»** в исходном датасете нет, есть только
  «задача → роль → часы». Требования стека вводятся и подтверждаются отдельно
  (`GET/POST /api/tasks/skill-review`); пока задача не размечена, подбор идёт по
  роли, а Bus Factor по навыкам — приближение через роль (`demand_source =
  role_proxy`).
* **Базовой линии Недели 0** в исходнике фактически нет (ADR-004): брать только из
  `plan_baseline`, не из `tasks.committed_week0`.
* **Границ квартала** в датасете нет: они заданы конфигурацией ETL (ADR-007,
  ADR-025). Другие даты меняют таблицу `sprints`, номера спринтов в контракте
  остаются прежними.
* **Фактических часов по спринтам** в исходнике нет: `task_role_spent` — итог по
  задаче и роли (ADR-014).
