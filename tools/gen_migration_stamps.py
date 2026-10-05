#!/usr/bin/env python3
"""Генерирует db/06_migration_stamps.sql — отметки «миграция уже учтена в базовой схеме».

    python tools/gen_migration_stamps.py          # перезаписать db/06_migration_stamps.sql
    python tools/gen_migration_stamps.py --check  # 0 — файл актуален, 1 — устарел (для CI)

Зачем. Базовые `db/0*.sql` всегда описывают ПОСЛЕДНЮЮ схему, а `db/migrations/*.sql`
обновляют уже существующие базы. Чистая установка, у которой нет отметок в
`schema_migrations`, при `tools/migrate.py` попыталась бы накатить все миграции
поверх уже новой схемы и упала бы (B-1). Файл-отметки применяется последним шагом
установки: все миграции, лежащие в репозитории на этот момент, записываются как
применённые с контрольной суммой `baseline`, и `migrate.py` их пропускает.

Правило: добавили миграцию — внесите то же изменение в базовые файлы и
перегенерируйте отметки (CI проверяет `--check`).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "db" / "migrations"
OUTPUT = ROOT / "db" / "06_migration_stamps.sql"
NAME = re.compile(r"^(\d{4}_[a-z0-9_]+)\.sql$")

HEADER = """-- СГЕНЕРИРОВАНО tools/gen_migration_stamps.py — не править руками.
-- Миграции, уже учтённые в базовой схеме db/01…05. Контрольная сумма `baseline`
-- означает «применена установкой», tools/migrate.py такие миграции пропускает.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    checksum   TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations (version, checksum) VALUES
"""

ASSISTANT_BOOTSTRAP = """
-- The seed is loaded after db/01_schema.sql. Register its first generation now.
INSERT INTO public.assistant_dataset_generations
    (generation_id, schema_name, pi_id, scenario_id, source_sha256)
SELECT gen_random_uuid(), current_schema(), p.pi_id, 'main',
       COALESCE((SELECT b.source_sha256 FROM load_batches b
                 ORDER BY b.batch_id DESC LIMIT 1), 'unloaded')
FROM pi_periods p
WHERE NOT EXISTS (SELECT 1 FROM public.assistant_dataset_generations g
                  WHERE g.schema_name = current_schema() AND g.active)
ORDER BY p.pi_id LIMIT 1;
"""


def render() -> str:
    versions: list[str] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        match = NAME.fullmatch(path.name)
        if not match:
            raise SystemExit(f"недопустимое имя миграции: {path.name}")
        versions.append(match.group(1))
    if not versions:
        raise SystemExit(f"нет миграций в {MIGRATIONS}")
    rows = ",\n".join(f"  ('{version}', 'baseline')" for version in versions)
    return f"{HEADER}{rows}\nON CONFLICT (version) DO NOTHING;\n{ASSISTANT_BOOTSTRAP}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT.relative_to(ROOT)} устарел: выполните tools/gen_migration_stamps.py",
                  file=sys.stderr)
            return 1
        print("отметки миграций актуальны")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"✓ {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
