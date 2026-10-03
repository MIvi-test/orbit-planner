#!/usr/bin/env python3
"""Пользователи сервиса и журнал действий (ADR-027).

    python tools/manage_users.py create ivan --role planner   # токен печатается ОДИН раз
    python tools/manage_users.py list
    python tools/manage_users.py rotate ivan                  # новый токен, старый перестаёт работать
    python tools/manage_users.py disable ivan                 # отозвать доступ
    python tools/manage_users.py enable ivan
    python tools/manage_users.py audit --limit 50             # последние действия

В Docker: `docker compose exec app python tools/manage_users.py list`.
Токен в базе не хранится, только SHA-256; потерянный токен восстановить нельзя — только `rotate`.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import auth, db  # noqa: E402


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def cmd_create(args: argparse.Namespace) -> int:
    token = _new_token()
    try:
        db.execute_write(
            "INSERT INTO app_users (name, role, token_sha256) VALUES (%s, %s, %s)",
            (args.name, args.role, auth.hash_token(token)),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"не создан: {exc}", file=sys.stderr)
        return 1
    print(f"пользователь {args.name} ({args.role}) создан. Токен показывается один раз:\n{token}")
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    token = _new_token()
    changed = db.execute_write(
        "UPDATE app_users SET token_sha256 = %s WHERE name = %s", (auth.hash_token(token), args.name)
    )
    if not changed:
        print(f"нет пользователя {args.name}", file=sys.stderr)
        return 1
    print(f"новый токен для {args.name} (прежний больше не работает):\n{token}")
    return 0


def cmd_toggle(args: argparse.Namespace, active: bool) -> int:
    changed = db.execute_write("UPDATE app_users SET active = %s WHERE name = %s", (active, args.name))
    if not changed:
        print(f"нет пользователя {args.name}", file=sys.stderr)
        return 1
    print(f"{args.name}: {'доступ включён' if active else 'доступ отозван'}")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    rows = db.query_dicts(
        "SELECT name, role, active, created_at, last_seen_at FROM app_users ORDER BY name"
    )
    if not rows:
        print("пользователей нет (аварийный администратор — PI_PLANNER_ADMIN_TOKEN)")
        return 0
    for row in rows:
        state = "активен" if row["active"] else "отключён"
        print(f"{row['name']:<24} {row['role']:<8} {state:<9} создан {row['created_at']:%Y-%m-%d %H:%M}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    rows = db.query_dicts(
        "SELECT at, actor, role, action, outcome, target, detail FROM audit_log ORDER BY event_id DESC LIMIT %s",
        (args.limit,),
    )
    for row in rows:
        print(f"{row['at']:%Y-%m-%d %H:%M:%S} {row['actor']:<16} {row['role']:<8} "
              f"{row['outcome']:<8} {row['action']} {row['detail'] or ''}")
    if not rows:
        print("журнал пуст")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="создать пользователя")
    create.add_argument("name")
    create.add_argument("--role", choices=auth.ROLES, default="viewer")
    for name in ("rotate", "disable", "enable"):
        sub.add_parser(name).add_argument("name")
    sub.add_parser("list")
    audit = sub.add_parser("audit")
    audit.add_argument("--limit", type=int, default=30)
    args = parser.parse_args(argv)
    return {
        "create": cmd_create,
        "rotate": cmd_rotate,
        "disable": lambda a: cmd_toggle(a, False),
        "enable": lambda a: cmd_toggle(a, True),
        "list": cmd_list,
        "audit": cmd_audit,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
