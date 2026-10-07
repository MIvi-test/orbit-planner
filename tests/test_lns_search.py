"""LNS must never publish a plan the greedy algorithm beats; neighborhoods stay sound."""
import random
from dataclasses import replace

from app import planner
from app.planner.local_search import search, solver
from tests.test_planner import engineer, inputs, task


def _source():
    return inputs(
        [task("A", prodf="P1", roles={1: 40}), task("B", prodf="P1", roles={1: 40}),
         task("C", prodf="P2", roles={1: 80}), task("D", prodf="P3", roles={1: 40})],
        [engineer("E")], sprint_count=2,
    )


def test_worse_than_greedy_result_falls_back_to_greedy(monkeypatch):
    source = _source()
    real = solver.solve_allocation

    def degraded(*args, **kwargs):
        result = real(*args, **kwargs)
        vector = tuple(str(int(v) - 1) for v in result.objective_vector)
        return replace(result, objective_vector=vector)

    monkeypatch.setattr("app.planner.core.solve_allocation", degraded)
    plan = planner.build_plan(source, algorithm=planner.ALGORITHM_LOCAL_SEARCH,
                              simulate_next_pi=False, max_time_seconds=3)
    greedy = planner.build_plan(source, simulate_next_pi=False)
    assert plan.params["fallback_reason"] == "lns result is lexicographically worse than greedy"
    assert {r.task_id for r in plan.in_quarter} == {r.task_id for r in greedy.in_quarter}


def test_random_neighborhood_releases_whole_initiatives_and_a_deferred_task():
    source = _source()
    greedy = planner.build_plan(source, simulate_next_pi=False)
    seed = solver.allocation_from_plan(greedy, source, priority_strategy="initiative")
    deferred = {t.task_id for t in source.tasks} - seed.selected
    assert deferred
    rng = random.Random(1)
    for _ in range(30):
        free = search._random_neighborhood(source, seed, rng, 2)
        assert free & deferred
        if free & {"A", "B"}:
            assert {"A", "B"} <= free
