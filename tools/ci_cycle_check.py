#!/usr/bin/env python3
"""CI: полный цикл квартала на чистой базе, приёмка без единой ошибки.

    # база уже залита (схема + seed + витрины), PI_PLANNER_DSN задан
    python tools/ci_cycle_check.py [--sprints 3]

Что делает:
1. строит базовый план (`tools/run_planner.py`);
2. прогоняет факт спринтов 1..N и пересчёт (`tools/demo_cycle.py`);
3. проверяет, что ни в одном прогоне нет нарушений `severity = 'error'`
   (`v_plan_violations`) и что прогонов столько, сколько ожидается.

Код возврата 0 — цикл прошёл, 1 — нарушения или неполный цикл.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402


def run(*args: str) -> None:
    print("$", " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sprints", type=int, default=3)
    args = parser.parse_args(argv)

    run("tools/run_planner.py")
    run("tools/demo_cycle.py", "--sprints", str(args.sprints))

    runs = db.query_dicts("SELECT run_id, as_of_sprint, status FROM plan_runs ORDER BY run_id")
    errors = db.query_dicts(
        "SELECT run_id, COUNT(*) AS n FROM v_plan_violations "
        "WHERE severity = 'error' GROUP BY run_id ORDER BY run_id"
    )
    print(f"прогонов: {len(runs)}; с ошибками приёмки: {len(errors)}")
    for row in runs:
        print(f"  run {row['run_id']}: as_of {row['as_of_sprint']}, status {row['status']}")

    problems: list[str] = []
    expected = args.sprints + 1  # базовый + по прогону на каждый загруженный факт
    if len(runs) < expected:
        problems.append(f"ожидалось не меньше {expected} прогонов, получено {len(runs)}")
    for row in errors:
        problems.append(f"прогон {row['run_id']}: {row['n']} нарушений severity=error")
    if problems:
        print("ЦИКЛ НЕ ПРОШЁЛ:", *problems, sep="\n  - ", file=sys.stderr)
        return 1
    print("цикл прошёл: 0 ошибок приёмки")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
