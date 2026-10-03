#!/usr/bin/env python3
"""Числа README (§8, §9) считаются по базе, а не пишутся руками.

    python tools/readme_numbers.py           # обновить блоки в README.md
    python tools/readme_numbers.py --check   # 0 — README актуален, 1 — устарел (CI)

Запускать на базе, в которой загружен датасет и построен БАЗОВЫЙ план, но ещё
нет факта спринтов (после `tools/run_planner.py`): числа описывают состояние
«Недели 0». Блоки в README ограничены маркерами
`<!-- numbers:NAME:begin -->` / `<!-- numbers:NAME:end -->`.
"""
from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402

README = ROOT / "README.md"


def _fmt(value: Decimal | int | float) -> str:
    number = Decimal(str(value)).quantize(Decimal("0.01"))
    text = f"{number:f}".rstrip("0").rstrip(".")
    return text or "0"


def _names(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items)


def plan_block() -> str:
    deficit = db.query_dicts(
        "SELECT verdict, COUNT(*) AS n, SUM(gap_hh) AS hh FROM v_role_deficit "
        "WHERE gap_hh > 0 GROUP BY verdict ORDER BY SUM(gap_hh) DESC"
    )
    total_n = sum(int(row["n"]) for row in deficit)
    total_hh = sum((Decimal(row["hh"]) for row in deficit), Decimal(0))
    hire = db.query_dicts(
        "SELECT role_name, gap_hh FROM v_role_coverage_org WHERE verdict LIKE 'НАЙМ%%' ORDER BY role_name"
    )
    teams_tight = db.query_dicts(
        "SELECT team_id, live_sp, available_sp_per_pi FROM v_team_profile "
        "WHERE live_sp > available_sp_per_pi ORDER BY team_id"
    )
    edges = db.query_one("SELECT COUNT(*) AS n FROM task_dependencies") or {"n": 0}
    live_edges = db.query_one(
        "SELECT COUNT(*) AS n FROM task_dependencies d "
        "JOIN tasks a ON a.task_id = d.blocking_task_id JOIN tasks b ON b.task_id = d.blocked_task_id "
        "WHERE a.status <> 'Done' AND b.status <> 'Done'"
    ) or {"n": 0}
    run = db.query_one(
        "SELECT run_id, params FROM plan_runs WHERE as_of_sprint = 0 ORDER BY run_id LIMIT 1"
    )
    if run is None:
        raise SystemExit("нет базового прогона: сначала python tools/run_planner.py")
    params = run["params"]
    labels = {
        row["code"]: row["label"]
        for row in db.query_dicts("SELECT code, label FROM ref_decision_reasons")
    }
    reasons = [
        f"{labels.get(code, code)} — {count}"
        for code, count in sorted(params["reasons"].items(), key=lambda item: -item[1])
        if code != "PLANNED"
    ]

    rows = ["| | |", "|---|---|"]
    if teams_tight:
        rows.append(
            "| Ёмкость в SP | узкое место: "
            + "; ".join(
                f"`{row['team_id']}` ({_fmt(row['live_sp'])} SP бэклога при ёмкости "
                f"{_fmt(row['available_sp_per_pi'])} SP на квартал)"
                for row in teams_tight
            )
            + " |"
        )
    else:
        rows.append("| Ёмкость в SP | у всех команд хватает |")
    rows.append(
        f"| Часы по ролям | **{_fmt(total_hh)} ЧЧ** дефицита по {total_n} связкам «команда × роль» |"
    )
    for row in deficit:
        rows.append(f"| ↳ {row['verdict']} | {row['n']} связок, {_fmt(row['hh'])} ЧЧ |")
    rows.append(
        f"| Нужен наём | {len(hire)} ролей, {_fmt(sum((Decimal(r['gap_hh']) for r in hire), Decimal(0)))} ЧЧ: "
        + _names([r["role_name"] for r in hire]) + " |"
    )
    rows.append(f"| Зависимости | живых рёбер {live_edges['n']} из {edges['n']} |")
    rows.append(
        f"| Итог базового плана | **{params['in_quarter']} из {params['live_tasks']}** задач в квартале, "
        f"{params['deferred']} не в квартале; инициатив целиком {params['initiatives_complete']} "
        f"из {params['initiatives_planned']} |"
    )
    rows.append("| Причины переноса | " + "; ".join(reasons) + " |")
    return "\n".join(rows)


def skills_block() -> str:
    skills = db.query_one(
        "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE bus_factor = 1) AS single, "
        "COUNT(*) FILTER (WHERE critical) AS critical, "
        "COUNT(*) FILTER (WHERE critical AND demand_source = 'confirmed') AS confirmed "
        "FROM v_bus_factor_skill"
    ) or {"total": 0, "single": 0, "critical": 0, "confirmed": 0}
    basis = (
        "по подтверждённым требованиям задач к технологиям"
        if skills["critical"] and skills["confirmed"] == skills["critical"]
        else "оценка через роль носителя как приближение: требования задач к технологиям "
        "не подтверждены (`docs/TASK_SKILL_ANNOTATION.md`)"
    )
    return (
        f"На датасете: **{skills['total']} компетенций, у {skills['single']} из них один носитель, "
        f"критичных — {skills['critical']}** ({basis})."
    )


BLOCKS = {"plan": plan_block, "skills": skills_block}


def apply(text: str) -> str:
    for name, build in BLOCKS.items():
        pattern = re.compile(
            rf"(<!-- numbers:{name}:begin -->)(.*?)(<!-- numbers:{name}:end -->)", re.S
        )
        if not pattern.search(text):
            raise SystemExit(f"в README нет маркеров numbers:{name}")
        text = pattern.sub(lambda m: m.group(1) + "\n" + build() + "\n" + m.group(3), text)
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    current = README.read_text(encoding="utf-8")
    updated = apply(current)
    if args.check:
        if updated != current:
            print("README.md устарел: выполните python tools/readme_numbers.py", file=sys.stderr)
            return 1
        print("числа README актуальны")
        return 0
    README.write_text(updated, encoding="utf-8")
    print("✓ README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
