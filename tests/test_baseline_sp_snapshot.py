"""Say/Do сохраняет обещанный размер задач после изменения текущей оценки."""
from dataclasses import replace
from decimal import Decimal

from app import planner
from tests.test_planner import engineer, inputs, task


def test_replan_uses_baseline_sp_for_say_do_denominator():
    source = inputs(
        [task("A", sp=8, roles={1: 40})], [engineer("E")],
        all_tasks=(("A", "Done", Decimal(8), Decimal(0)),),
        baseline_schedule={"A": ("in_quarter", 1, 1)},
        done_in_sprint={1: frozenset({"A"})}, last_reported_sprint=1,
    )
    source = replace(source, baseline_sp={"A": Decimal(5)}, baseline_run_id=42)

    plan = planner.build_plan(source, as_of_sprint=2)
    sprint_one = next(row for row in plan.kpis
                      if row.kpi_code == "say_do_ratio" and row.sprint_no == 1)

    assert sprint_one.details["planned_sp"] == "5"
    assert sprint_one.details["done_sp"] == "8"
    assert plan.params["baseline_run_id"] == 42
