#!/usr/bin/env python3
"""Сравнение стратегий приоритета инициативы на одних и тех же ресурсах (DA-11, ADR-032).

    python tools/compare_priority.py                 # базовый срез (Неделя 0), таблица
    python tools/compare_priority.py --as-of 3       # срез пересчёта на начало спринта 3
    python tools/compare_priority.py --json out.json

Ничего не пишет в базу: читает вход, строит план для каждой стратегии и показывает, как
меняется состав квартала. Это ответ на вопрос «насколько результат зависит от выбранной
эвристики приоритета, а не от данных».
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import planner  # noqa: E402


def summarize(plan: planner.Plan, reference: set[str]) -> dict:
    planned = {row.task_id for row in plan.in_quarter}
    union = planned | reference
    return {
        "in_quarter": len(planned),
        "deferred": len(plan.deferred),
        "initiatives_complete": plan.params["initiatives_complete"],
        "initiatives_partial": len(plan.params["initiatives_partial"]),
        "in_quarter_hh": plan.params["in_quarter_hh"],
        "loan_hh": plan.params["loan_hh"],
        "same_as_max": round(len(planned & reference) / len(union), 2) if union else 1.0,
        "only_here": sorted(planned - reference),
        "only_in_max": sorted(reference - planned),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--as-of", type=int, default=0, help="срез: 0 — Неделя 0, k — начало спринта k")
    parser.add_argument("--json", help="сохранить результат в файл")
    args = parser.parse_args(argv)

    inputs = planner.load_inputs()
    starts = planner.load_baseline_starts() if args.as_of > 0 else {}
    plans = {
        strategy: planner.build_plan(inputs, as_of_sprint=args.as_of, baseline_starts=starts,
                                     priority_strategy=strategy, simulate_next_pi=False)
        for strategy in planner.PRIORITY_STRATEGIES
    }
    reference = {row.task_id for row in plans[planner.PRIORITY_MAX].in_quarter}
    report = {strategy: summarize(plan, reference) for strategy, plan in plans.items()}

    print(f"{'стратегия':<18} {'в квартале':>10} {'инициатив целиком':>18} {'частично':>9} {'ЧЧ':>8} {'заём ЧЧ':>8} {'= max':>6}")
    for strategy, row in report.items():
        print(f"{strategy:<18} {row['in_quarter']:>10} {row['initiatives_complete']:>18} "
              f"{row['initiatives_partial']:>9} {row['in_quarter_hh']:>8} {row['loan_hh']:>8} {row['same_as_max']:>6}")
        if row["only_here"] or row["only_in_max"]:
            print(f"    отличается от max: добавлены {row['only_here'] or '—'}, ушли {row['only_in_max'] or '—'}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"→ {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
