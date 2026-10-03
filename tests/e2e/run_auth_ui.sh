#!/usr/bin/env bash
# Браузерная проверка входа и ролей на настоящем сервере и базе.
#
#   PI_PLANNER_DSN="host=… dbname=…" tests/e2e/run_auth_ui.sh
#
# Нужны: PostgreSQL по PI_PLANNER_DSN (схема и базовый план заливаются здесь же), uv, node
# с пакетом playwright-core (`npm i playwright-core` в tests/e2e или рядом) и chromium
# (CHROME=/путь/к/chrome, либо браузер Playwright).
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${PI_PLANNER_DSN:?задайте PI_PLANNER_DSN}"
PORT="${E2E_PORT:-18090}"
ADMIN_TOKEN="e2e-admin-token-$(date +%s)-abcdef"
OUT="${OUT:-$(mktemp -d)}"
export PI_PLANNER_ADMIN_TOKEN="$ADMIN_TOKEN" PI_PLANNER_AUTH=required

uv run python tools/apply_sql.py --wait 60
uv run python tools/apply_sql.py db/01_schema.sql db/02_contract.sql build/seed.sql \
  db/03_substitutions.sql db/04_views.sql db/05_invariants.sql db/06_migration_stamps.sql >/dev/null
uv run python tools/run_planner.py >/dev/null
VIEWER_TOKEN="$(uv run python tools/manage_users.py create vera --role viewer | tail -1)"

uv run python -m app.server --port "$PORT" > "$OUT/server.log" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  curl -fs "http://127.0.0.1:$PORT/api/livez" >/dev/null && break
  sleep 1
done

BASE="http://127.0.0.1:$PORT" VIEWER="$VIEWER_TOKEN" ADMIN="$ADMIN_TOKEN" OUT="$OUT" \
  node tests/e2e/auth_ui.mjs
echo "скриншоты и лог сервера: $OUT"
