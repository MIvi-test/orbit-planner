#!/usr/bin/env python3
"""Нормализованный «отпечаток» схемы public: сравнить две базы построчно.

    PI_PLANNER_DSN=... python tools/schema_fingerprint.py > schema.txt
    python tools/schema_fingerprint.py --dsn "host=... dbname=..." > schema.txt

Зачем. Схема живёт в двух местах: базовые `db/0*.sql` (чистая установка) и
`db/migrations/*.sql` (обновление существующей базы). CI поднимает обе базы и
сравнивает отпечатки: расхождение значит, что чистая установка и обновление
дают разные схемы. Порядок колонок не сравнивается — `ALTER TABLE ADD COLUMN`
законно ставит колонку в конец. Данные таблиц не сравниваются.
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg

QUERIES: dict[str, str] = {
    "column": """
        SELECT c.table_name, c.column_name, c.data_type, c.is_nullable,
               COALESCE(c.column_default, ''), c.is_generated,
               COALESCE(c.generation_expression, '')
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
    """,
    "constraint": """
        SELECT cl.relname, co.conname, pg_get_constraintdef(co.oid)
        FROM pg_constraint co
        JOIN pg_class cl ON cl.oid = co.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace
        WHERE n.nspname = 'public'
    """,
    "index": """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes WHERE schemaname = 'public'
    """,
    "view": """
        SELECT c.relname, pg_get_viewdef(c.oid, true)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'v'
    """,
    "function": """
        SELECT p.proname, pg_get_function_identity_arguments(p.oid),
               pg_get_functiondef(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prokind = 'f'
    """,
    "trigger": """
        SELECT cl.relname, t.tgname, pg_get_triggerdef(t.oid)
        FROM pg_trigger t JOIN pg_class cl ON cl.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace
        WHERE n.nspname = 'public' AND NOT t.tgisinternal
    """,
}


def fingerprint(dsn: str) -> list[str]:
    lines: list[str] = []
    with psycopg.connect(dsn) as conn:
        conn.read_only = True
        for kind, sql in QUERIES.items():
            for row in conn.execute(sql).fetchall():
                # Определение функции/представления многострочное: сворачиваем
                # пробелы, чтобы diff показывал одну строку на объект.
                text = " | ".join(" ".join(str(cell).split()) for cell in row)
                lines.append(f"{kind}: {text}")
    return sorted(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dsn", default=os.environ.get("PI_PLANNER_DSN", ""))
    args = parser.parse_args(argv)
    if not args.dsn:
        print("нужен --dsn или PI_PLANNER_DSN", file=sys.stderr)
        return 2
    sys.stdout.write("\n".join(fingerprint(args.dsn)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
