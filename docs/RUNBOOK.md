# RUNBOOK — запуск, обновление и проверка сервиса

Документ для тех, кто поднимает сервис и сопровождает его в эксплуатации.
Быстрый старт для пользователя — в [README.md](../README.md); метрики, алерты и
дашборды — в [OBSERVABILITY.md](OBSERVABILITY.md); как устроено планирование — в
[ALGORITHMS.md](ALGORITHMS.md). Актуальные контрольные числа для загруженной
базы выдаёт `python tools/current_report.py`; числа в этом документе не хранятся.

## 0. Что где лежит

| Что | Где |
|---|---|
| Схема, контракт, витрины, приёмка плана | `db/01_schema.sql` … `db/05_invariants.sql`, отметки миграций `db/06_migration_stamps.sql` |
| Миграции | `db/migrations/NNNN_описание.sql` |
| Данные датасета (сид) | `build/seed.sql` |
| ETL (пересборка сида из Excel) | `etl/load.py`, `etl/config.py` |
| Планировщик | `app/planner/` |
| HTTP-сервер (`/api/*`, `/metrics`, статика `web/dist`) | `app/server.py`, `app/metrics.py` |
| Фронт | `web/` (собранный — `web/dist/`, он хранится в репозитории) |
| Типы фронта из схемы базы | `tools/gen_types.py` → `web/src/types/db.ts` |
| Docker Compose, Caddy, мониторинг | `docker-compose.yaml`, `Caddyfile`, `ops/` |
| Запуск без Docker | `run.sh` (Linux, macOS), `run.bat` (Windows) |
| Служебные команды | `tools/` (миграции, пользователи, запуск планировщика, отчёты, проверки) |

## 1. Запуск

### 1.1. Docker Compose (основной способ)

Нужен Docker с Compose v2 (или podman с `podman compose`).

```bash
cp .env.example .env     # задать POSTGRES_PASSWORD, PI_PLANNER_ADMIN_TOKEN, GRAFANA_ADMIN_PASSWORD
docker compose up -d --build
```

Приложение открывается на `https://localhost` (Caddy выпускает локальный
сертификат), вход — по токену `PI_PLANNER_ADMIN_TOKEN`. Grafana — на
`https://grafana.localhost`. При первом запуске собирается образ, PostgreSQL
инициализируется схемой и данными, одноразовый сервис `bootstrap-plan` строит
базовый план, и только затем стартует `app`.

| Команда | Что делает |
|---|---|
| `docker compose ps` | состояние сервисов |
| `docker compose logs -f app` | логи приложения |
| `docker compose up -d --build app` | пересобрать и перезапустить приложение |
| `docker compose run --rm migrate` | применить миграции |
| `docker compose down` | остановить стек, данные в томах сохраняются |
| `docker compose down -v` | остановить и **удалить все данные** |

### 1.2. Без Docker для приложения

```bash
./run.sh            # Linux, macOS
run.bat             # Windows
```

Скрипт ставит Python-зависимости (`uv` или `venv` + `pip`), при необходимости
поднимает PostgreSQL в контейнере `pi-planner-pg` (или использует вашу базу из
`PI_PLANNER_DSN`), заливает схему и данные, строит базовый план и запускает сервер
на `http://127.0.0.1:8000`. Токен администратора создаётся при первом запуске и
сохраняется в `.run-admin-token`. Флаги: `--reset` (перезалить базу с нуля),
`--no-build` (не собирать фронт); порт — `APP_PORT=8080`. Остановка — `Ctrl+C`.

Если порт 8000 занят прошлым запуском, закройте прежний процесс.

### 1.3. Строка подключения к базе

Приоритет источников: переменная `PI_PLANNER_DSN`, затем `dsn.json` в корне (см.
`dsn.example.json`, файл в `.gitignore`), затем локальная база по умолчанию.
Соединение по умолчанию read-only: пишут только явные транзакции планировщика и
загрузок.

## 2. Инструменты для разработки и сборки

| Инструмент | Зачем | Как поставить |
|---|---|---|
| Python 3.14 и `uv` | бэкенд и тесты | `uv sync --frozen`; `uv python install` подтянет версию из `.python-version` |
| Node LTS | сборка фронта (`web/dist`) | любая установка Node; на машине, которая только запускает сервис, не нужен |
| PostgreSQL 17 | база | `docker run -d --name pi-planner-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=pi_planner -p 5432:5432 postgres:17` |

**Кодировка базы обязательно UTF-8.** В сиде есть русский текст; на системе с
не-UTF-8 локалью по умолчанию `initdb` выбирает другую кодировку, и вставка падает
или записывает мусор. Для ручной установки: `initdb -E UTF8 --locale=C`. Проверка:
`SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname='pi_planner';`
должна вернуть `UTF8`.

**Фронт.** Разработка: запустите бэкенд (`./run.sh`), затем
`cd web && npm install && npm run dev` — Vite на `http://127.0.0.1:5173` проксирует
`/api` на `:8000`. Перед коммитом выполните `npm run build`: `web/dist`
хранится в репозитории и коммитится **вместе с правками `web/src`**, чтобы машине без
Node ничего не пришлось собирать. `run.sh` пересобирает `web/dist` сам только когда
это безопасно: есть `web/node_modules` и исходники новее сборки по git.

## 3. Ручная заливка SQL

Порядок обязателен:

```bash
for f in db/01_schema.sql db/02_contract.sql build/seed.sql \
         db/03_substitutions.sql db/04_views.sql db/05_invariants.sql db/06_migration_stamps.sql; do
  psql -h 127.0.0.1 -U postgres -d pi_planner -v ON_ERROR_STOP=1 -f "$f"
done
```

Либо без клиента `psql`: `python tools/apply_sql.py --wait 60 db/01_schema.sql …`.
`ON_ERROR_STOP=1` не косметика: без него после ошибки заливка продолжится и
получится полупустая база. Сид идёт **после** схемы и **до** витрин: витрины
зависят от заполненных таблиц.

> **Не пересевайте базу после первого планирования.** `build/seed.sql` начинается с
> `TRUNCATE … RESTART IDENTITY` и стирает историю прогонов (`plan_runs` и всё, что
> на неё ссылается).

## 4. Изменение схемы и миграции

Первичная инициализация PostgreSQL выполняет SQL из `docker-entrypoint-initdb.d`
только на пустом томе `postgres_data`. Обновлять схему повторной заливкой
`seed.sql` нельзя. Каждое изменение схемы — новый файл
`db/migrations/NNNN_описание.sql`; применённые файлы не редактируются
(`tools/migrate.py` сверяет их SHA-256).

* Номер новой миграции — следующий по порядку (`max + 1`): порядок применения на
  старой и на чистой базе должен совпадать.
* То же изменение вносится в базовые файлы `db/01…05.sql`: они всегда описывают
  **последнюю** схему и используются при чистой установке.
* После добавления миграции выполните `python tools/gen_migration_stamps.py`: файл
  `db/06_migration_stamps.sql` записывает лежащие в репозитории миграции как
  применённые с контрольной суммой `baseline`. Чистая установка получает эти
  отметки последним шагом, `tools/migrate.py` их пропускает; старая база без
  отметок получает миграции по порядку. CI-джоба `schema-equivalence` и тест
  `tests/test_migration_stamps.py` проверяют, что обе дороги дают одну схему
  (`tools/schema_fingerprint.py`).
* Миграции пишутся идемпотентно (`IF NOT EXISTS`, `CREATE OR REPLACE`).
* Любое удаление или переименование колонки — двухфазно: сначала релиз, умеющий
  читать обе схемы, затем миграция, и только в следующем релизе удаление старого
  контракта.

## 5. Деплой

### 5.1. Подготовка production-хоста

Минимум: Linux x86_64, Docker Engine с Compose v2, DNS-записи для `CADDY_DOMAIN` и
`GRAFANA_DOMAIN`, открытые входящие TCP 80 и 443, достаточно места под тома и
архивы. PostgreSQL, приложение, Prometheus и Grafana не публикуют host-порты:
наружу смотрит только Caddy.

```bash
cp .env.example .env
chmod 600 .env
openssl rand -hex 32       # POSTGRES_PASSWORD
openssl rand -hex 32       # GRAFANA_ADMIN_PASSWORD
openssl rand -hex 32       # PI_PLANNER_ADMIN_TOKEN
```

В `.env` задайте реальные `CADDY_DOMAIN`, `GRAFANA_DOMAIN`, оба пароля,
`PI_PLANNER_ADMIN_TOKEN` (заглушка `CHANGE-ME` не даёт приложению стартовать) и
абсолютный `BACKUP_DIR` на отдельном диске. Значения `change-me-*`, `localhost` и
относительный каталог копий — блокеры production-релиза. `.env` не коммитится и не
прикладывается к тикетам; в CI его создаёт хранилище секретов с правами только у
deploy-задачи.

До первого старта проверьте конфигурацию без вывода секретов:

```bash
docker compose config --quiet
docker compose build app migrate
docker compose pull db backup caddy prometheus grafana
```

Версии Prometheus и Grafana закреплены точно, но `postgres:17-bookworm`,
`python:3.14-slim`, `node:22-bookworm-slim` и `caddy:2-alpine` остаются плавающими
тегами. Для строго воспроизводимого релиза платформа должна фиксировать образы по
digest.

### 5.2. Доступ пользователей (ADR-027)

После первого старта войдите токеном `PI_PLANNER_ADMIN_TOKEN` и заведите людей
персональными токенами; общий токен храните как аварийный и не раздавайте:

```bash
docker compose exec app python tools/manage_users.py create ivan --role planner
docker compose exec app python tools/manage_users.py list
docker compose exec app python tools/manage_users.py rotate ivan     # токен утёк или потерян
docker compose exec app python tools/manage_users.py disable ivan    # сотрудник ушёл
docker compose exec app python tools/manage_users.py audit --limit 100
```

Роли: `viewer` — просмотр; `planner` — загрузка факта и подтверждения; `admin` —
загрузка датасета (стирает цикл). Токен показывается один раз, в базе хранится
SHA-256. Журнал `audit_log` дописывается при каждом изменении данных; события
`auth_denied` и `auth_blocked` в логе — основа для алертов на подбор токенов.
Токены передаются только по HTTPS (Caddy). `/metrics` закрыт Caddy снаружи и
открыт только внутри сети `monitoring`.

### 5.3. Релиз без потери данных

Перед каждым релизом запишите git SHA и снимите проверенную резервную копию:

```bash
git rev-parse HEAD
docker compose up -d db backup
docker compose restart backup
docker compose logs --since=10m backup
```

Дождитесь строки `[backup] completed …`, имя архива сохраните в тикете релиза.
Затем примените миграции одной задачей и обновите сервисы:

```bash
docker compose run --rm migrate
docker compose up -d --build app assistant-worker
docker compose up -d caddy prometheus grafana backup
docker compose ps
```

`docker-compose.yaml` не передаёт `PI_PLANNER_GIT_SHA` внутрь `app`, поэтому
`git_sha` в `/api/version` будет `null`: SHA фиксируется в тикете релиза вместе с
digest образа. Compose рассчитан на один экземпляр приложения и допускает короткий
перерыв при пересоздании `app`; настоящий zero-downtime требует оркестратора, двух
реплик и readiness-gate.

### 5.4. Резервные копии

`backup` снимает дамп PostgreSQL в custom-формате сразу после старта и далее раз в
сутки; после каждого дампа восстанавливает его во временную базу и проверяет
ключевые объекты. Сбой завершает контейнер, и Compose его перезапускает. Каталог,
срок хранения и интервал задаются в `.env`: `BACKUP_DIR`,
`BACKUP_RETENTION_DAYS`, `BACKUP_INTERVAL_SECONDS`. Для production `BACKUP_DIR`
должен быть смонтированным или реплицируемым хранилищем.

Каталог создайте заранее от имени пользователя деплоя и передайте его uid/gid
контейнеру (Linux: `BACKUP_UID=$(id -u)`, `BACKUP_GID=$(id -g)`): значения в `.env`
должны совпадать с владельцем `BACKUP_DIR`, иначе копия завершится с
`Permission denied`. RPO — до 24 часов; RTO заранее не гарантируется и должен быть
измерен учебным восстановлением.

### 5.5. Проверка после релиза

Замените домен и запускайте проверки с машины, которая обращается к сервису тем же
путём, что пользователь:

```bash
curl -fsS "https://planner.example.ru/api/livez"
curl -fsS "https://planner.example.ru/api/health"
curl -fsS "https://planner.example.ru/api/version"
test "$(curl -sS -o /dev/null -w '%{http_code}' "https://planner.example.ru/metrics")" = 404
curl -fsS "https://grafana.example.ru/api/health"
docker compose exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose exec -T prometheus wget -qO- \
  'http://127.0.0.1:9090/api/v1/query?query=up%7Bjob%3D%22pi-planner%22%7D'
```

Дополнительно откройте один разрешённый `/api/views/{view}`, сверьте версию из
`/api/version` с тикетом и убедитесь, что запрос Prometheus возвращает 1. Релиз
принят, только если `pi_planner_plan_violations{severity="error"}` равна нулю и нет
сработавших critical-правил.

### 5.6. Откат

Откат приложения — повторный запуск предыдущего образа или коммита; перед
переключением убедитесь, что старая версия совместима с уже применённой схемой.
SQL-миграции намеренно не имеют автоматического отката: откат схемы вслепую опаснее,
чем обратно совместимое расширение. Если миграция разрушительна или старая версия
несовместима со схемой:

1. остановите запись и приложение;
2. сохраните аварийный дамп текущей базы отдельно;
3. восстановите последний проверенный дорелизный дамп (раздел 5.7);
4. запустите предыдущую версию приложения;
5. повторите проверки раздела 5.5.

### 5.7. Восстановление PostgreSQL из дампа

Восстановление перезаписывает данные: сначала остановите сервисы, которые читают
или меняют базу, и сохраните аварийную копию. Команды предполагают, что
`POSTGRES_USER` и `POSTGRES_DB` экспортированы из защищённого окружения:

```bash
docker compose stop app assistant-worker backup
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -Fc --no-owner --no-privileges > pre-restore-emergency.dump
docker compose exec -T db dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
docker compose exec -T db createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose exec -T db pg_restore -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" --exit-on-error --no-owner --no-privileges \
  < /absolute/path/to/pi_planner-YYYYMMDDTHHMMSSZ.dump
docker compose run --rm migrate
docker compose up -d app assistant-worker backup
```

Подставляйте конкретное имя дампа, не glob. После восстановления повторите
проверки раздела 5.5 и SQL-проверку раздела 6; аварийный дамп удаляйте только с
согласия владельца данных.

### 5.8. Эксплуатационный чек-лист

| Периодичность | Проверка | Критерий |
|---|---|---|
| каждый релиз | миграции, health, версия, правила Prometheus | все команды завершились с кодом 0 |
| ежедневно | возраст и проверка восстановления копии | последний успех моложе 26 часов |
| еженедельно | место на дисках и томах, сработавшие алерты | запас диска не меньше 30%, critical нет |
| ежемесячно | ручное восстановление в изолированную базу | схема и ключевые таблицы читаются |
| перед обновлением образов | примечания к релизу и копия | есть проверенный дамп и план отката |

### 5.9. ИИ-ассистент

`assistant-worker` обрабатывает сохранённые задания чата отдельно от HTTP-сервера.
Контракт API — [openapi/assistant.yaml](openapi/assistant.yaml), правила ответа —
[ASSISTANT_RULES.md](ASSISTANT_RULES.md), запуск бэкенда — [ASSISTANT_RUNBOOK.md](ASSISTANT_RUNBOOK.md).

* Для Gemini, Groq и Qwen Cloud задайте нужный `*_API_KEY` в `.env`, затем создайте профиль
  через `POST /api/assistant/profiles` с `api_key_ref=env:ИМЯ_ПЕРЕМЕННОЙ` (в интерфейсе —
  «ИИ-ассистент» → «Настройки» → «Профили моделей»). Собственный OpenAI-совместимый сервер
  задаётся через `base_url`, `model` и `api_key_ref`; для локального Ollama допустим
  `auth_type=none`. После настройки вызовите `POST /api/assistant/profiles/{id}/check`.
* На локальном запуске `run.sh` поднимает worker автоматически; отдельно он запускается
  командой `python -m app.assistant.worker`.
* База знаний использует PostgreSQL 17 на образе `pgvector/pgvector` с тем же томом данных.
  После обновления образа выполните `docker compose run --rm migrate`: миграция создаёт
  расширение `vector`, не заменяя существующий volume.
* Локальные эмбеддинги:

```bash
docker compose --profile rag-local up -d ollama
docker compose --profile rag-local exec ollama ollama pull embeddinggemma
docker compose exec app python tools/index_assistant_kb.py
```

Последняя команда индексирует только `docs/assistant_kb_manifest.json`; повторная индексация
неизменённых документов сохраняет их версии и активную ревизию. Администратор также может
запустить её через `POST /api/assistant/kb/reindex` и проверить `GET /api/assistant/kb/status`.
Для собственного внутреннего Ollama задайте `PI_PLANNER_KB_EMBED_BASE_URL` и добавьте его хост в
`PI_PLANNER_INTERNAL_LLM_HOSTS`.

## 6. Проверка работоспособности

### 6.1. База

```bash
psql -h 127.0.0.1 -U postgres -d pi_planner -v ON_ERROR_STOP=1 -f tools/acceptance.sql
```

`tools/acceptance.sql` проверяет слой данных после заливки: кодировку, календарь и
множители фонда, число объектов, сводку находок качества данных, дефицит ролей,
Bus Factor, ёмкость команд, хэш исходного Excel и отсутствие ошибок в
`v_plan_violations`. Ожидаемые значения зависят от датасета: сверяйте с
`python tools/current_report.py`, а не с числами из документов.

Проверки приёмки плана должны не только молчать на живых данных, но и срабатывать
на заведомо битых: `tools/negative_test.sql` собирает неправильный прогон внутри
транзакции с `ROLLBACK` в конце, поэтому база после теста не меняется.

```bash
psql -h 127.0.0.1 -U postgres -d pi_planner -v ON_ERROR_STOP=1 -f tools/negative_test.sql
```

### 6.2. Планировщик

```bash
uv run python tools/run_planner.py                    # базовый план (as_of_sprint = 0)
uv run python tools/run_planner.py --as-of-sprint 3   # пересчёт на начало 3-го спринта
uv run python tools/run_planner.py --dry-run          # посчитать, не записывая
```

Прогон пишет контракт целиком одной транзакцией и публикуется, только если нет
строк `severity = 'error'`. Проверка результата:

```sql
SELECT * FROM v_plan_violations WHERE run_id = <прогон> AND severity = 'error';  -- пусто = нет ошибок
```

Полный цикл квартала (базовый план и факт спринтов 1–3) одной командой:
`python tools/ci_cycle_check.py --sprints 3` на чистой базе; без Docker для
приложения — `tools/demo_cycle.py`.

### 6.3. Сервер

| Проверка | Ожидается |
|---|---|
| `GET /api/health` | 200 JSON; при остановленной базе 503 `database_unavailable`, сервер не падает |
| `GET /api/livez` | 200 без обращения к базе |
| `GET /api/version` | 200, версии приложения и ETL |
| `GET /api/nope` | 404 JSON со списком известных маршрутов |
| `GET /` и любой путь SPA | `index.html`; при отсутствии `web/dist` — 503 `frontend_not_built` |
| `GET /assets/nope.js` | 404 JSON, а не подмена на `index.html` |
| `GET /api/views` | справочник витрин |
| `GET /api/views/nope` | 404 `not_found` и `known` |
| `GET /api/views/v_task_board?order=1;--` | 400 `bad_request`, в SQL ничего не уходит |
| `GET /api/views/v_task_board?limit=5001`, `?run_id=…` у справочной витрины | 400 с объяснением |
| `GET /metrics` | 200 `text/plain; version=0.0.4`; `pi_planner_db_up` равен 1 |
| `--log-format json` | одна строка лога — один JSON-объект |
| SIGTERM / SIGINT | штатная остановка, код возврата 0 |

При включённой авторизации добавляйте заголовок `Authorization: Bearer <токен>`
для всех маршрутов, кроме `livez`, `health` и `version`.

### 6.4. Тесты

```bash
uv run pytest -q                 # быстрые тесты без базы
```

Тесты с PostgreSQL используют `TEST_DATABASE_URL` (отдельная пустая база):
`tests/pg_support.py` поднимает схему и сид. Планировщик (`tests/test_planner.py`)
проверяется на чистой `build_plan()` и базы не касается; сервер
(`tests/test_server.py`) поднимается на свободном порту в потоке; витрины
(`tests/test_views.py`) проверяют, что попытка инъекции в имя витрины или `order`
**не доходит до базы**. Для фронта: `cd web && npm run build` (включает
`tsc --noEmit`).

### 6.5. ETL

ETL должен быть воспроизводимым: два запуска подряд на одном Excel дают
побайтово одинаковый `build/seed.sql`. Проверка после любой правки ETL:

```bash
python etl/load.py && cp build/seed.sql /tmp/seed_a.sql
python etl/load.py && cp build/seed.sql /tmp/seed_b.sql
diff /tmp/seed_a.sql /tmp/seed_b.sql        # пусто
```

## 7. Что легко сломать

| Симптом | Причина | Что делать |
|---|---|---|
| `column "is_loan" can only be updated to DEFAULT` | `plan_assignments.is_loan` — генерируемая колонка | не включать её в `INSERT` и `UPDATE` |
| `operator does not exist: text = integer` | параметры уходят как `text` | приводить явно: `WHERE task_id = %s::int` |
| Русский текст превратился в мусор | база создана не в UTF-8 | пересоздать с `-E UTF8 --locale=C` (раздел 2) |
| Заливка «прошла», но база пустая | нет `ON_ERROR_STOP=1` | всегда `-v ON_ERROR_STOP=1` |
| История прогонов исчезла | повторный залив `seed.sql` | не пересевать после первого планирования |
| Витрин меньше, чем ожидается, или они пустые | залиты не в том порядке | перезалить по разделу 3 |
| Фонд часов не совпадает с календарём | залит старый `db/04_views.sql` | перезалить схему и витрины по разделу 3 |
| `planner: календарь PI разъехался` | `pi_periods.sprint_count` не совпадает с числом строк `sprints` | перезалить `build/seed.sql`: он генерирует оба |
| `etl: календарь PI: спринты покрывают N дней из M` | в `etl/config.py` разошлись `PI_START`, `PI_END`, `SPRINT_COUNT` | править конфиг: сетка обязана закрыть квартал ровно (ADR-007, ADR-025) |
| `v_role_coverage_org` показывает меньше ролей найма, чем ожидалось | залит `db/03_substitutions.sql` со статусом, отличным от `rejected` | замещения отклонены организаторами (ADR-010): все строки должны быть `rejected` |
| В интерфейсе «API недоступен: 503» | PostgreSQL не отвечает или DSN смотрит в другую базу | `curl …/api/health`: в теле причина, DSN без пароля и подсказка; поднять базу |
| `Permission denied` у контейнера `backup` | uid/gid в `.env` не совпадают с владельцем `BACKUP_DIR` | выровнять `BACKUP_UID` и `BACKUP_GID` с владельцем каталога |
| `npm ci` уходит в сеть и падает | сборка фронта недоступна без интернета | собрать `web/dist` заранее и закоммитить |

## 8. Мониторинг

Контракт для мониторинга — эндпоинты `livez`, `health`, `version`, `metrics`,
имена метрик и меток, алерты и дашборды — описан целиком в
[OBSERVABILITY.md](OBSERVABILITY.md). Переименование метрики, метки или эндпоинта —
breaking change и объявляется отдельно, а не делается попутным рефакторингом.
