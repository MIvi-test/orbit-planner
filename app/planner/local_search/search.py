"""Large-neighborhood repair around a feasible CP-SAT plan."""
from __future__ import annotations

import random
from itertools import combinations
from time import monotonic

from app.planner.local_search.solver import AllocationSolution, solve_allocation
from app.planner.model import Inputs, TaskInput


def _task_order(tasks: tuple[TaskInput, ...]) -> list[TaskInput]:
    return sorted(tasks, key=lambda task: (
        task.priority_rung is None,
        -(task.business_priority if task.business_priority is not None else task.priority_rung or 0),
        task.topo_order,
        task.task_id,
    ))


def _neighborhoods(
    inputs: Inputs,
    incumbent: AllocationSolution,
    *,
    limit: int,
) -> list[frozenset[str]]:
    """Deterministic small neighborhoods plus the 1-to-2 exchange operator."""
    tasks = {task.task_id: task for task in inputs.tasks}
    selected = incumbent.selected
    deferred = set(tasks) - selected
    ordered_deferred = [task.task_id for task in _task_order(tuple(tasks[key] for key in deferred))]
    ordered_selected = [task.task_id for task in _task_order(tuple(tasks[key] for key in selected))]
    result: list[frozenset[str]] = []
    seen: set[frozenset[str]] = set()

    def add(ids: set[str]) -> None:
        neighborhood = frozenset(ids)
        if neighborhood and neighborhood not in seen and len(result) < limit:
            seen.add(neighborhood)
            result.append(neighborhood)

    # Atomic initiatives must be released as one unit, regardless of size.
    if incumbent is not None:
        for members in _initiative_groups(inputs).values():
            if any(task_id in deferred for task_id in members):
                add(set(members))

    # Repack each selected task on its own: this can move work to earlier
    # sprints, reduce borrowed capacity, or change engineers without changing selection.
    for task_id in ordered_selected:
        add({task_id})

    # One-for-two exchanges are necessary for the 80 -> 40 + 40 trap.
    for selected_id in ordered_selected:
        selected_task = tasks[selected_id]
        candidates = [
            task_id for task_id in ordered_deferred
            if tasks[task_id].team_id == selected_task.team_id
            or set(tasks[task_id].needed) & set(selected_task.needed)
        ]
        for first, second in combinations(candidates, 2):
            if tasks[first].team_id != tasks[second].team_id:
                continue
            add({selected_id, first, second})
            if len(result) >= limit:
                return result

    # Release a selected task and one competing deferred task together.
    for deferred_id in ordered_deferred:
        deferred_task = tasks[deferred_id]
        candidates = [
            selected_id for selected_id in ordered_selected
            if tasks[selected_id].team_id == deferred_task.team_id
            or set(tasks[selected_id].needed) & set(deferred_task.needed)
        ]
        for selected_id in candidates:
            add({selected_id, deferred_id})
            if len(result) >= limit:
                return result

    # A single moved task can fill a small unused gap.
    for task_id in ordered_deferred:
        add({task_id})
        if len(result) >= limit:
            return result

    # Repack two deferred tasks against an already selected task, even where
    # the shared bottleneck is an engineer rather than the task's home team.
    role_candidates: dict[int, list[str]] = {}
    for role_id in sorted({role for task in tasks.values() for role in task.needed}):
        role_candidates[role_id] = [
            task_id for task_id in ordered_deferred if role_id in tasks[task_id].needed
        ]
    for selected_id in ordered_selected:
        for role_id, deferred_ids in role_candidates.items():
            if role_id not in tasks[selected_id].needed:
                continue
            for first, second in combinations(deferred_ids, 2):
                add({selected_id, first, second})
                if len(result) >= limit:
                    return result
    return result


def _initiative_groups(inputs: Inputs) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for task in inputs.tasks:
        groups.setdefault(task.prodf_id, []).append(task.task_id)
    return groups


def _expand_initiatives(inputs: Inputs, ids: set[str]) -> frozenset[str]:
    """Release whole initiatives: a partial one can never count as complete."""
    groups = _initiative_groups(inputs)
    by_task = {task.task_id: task.prodf_id for task in inputs.tasks}
    result = set(ids)
    for task_id in ids:
        result.update(groups[by_task[task_id]])
    return frozenset(result)


def _random_neighborhood(
    inputs: Inputs,
    incumbent: AllocationSolution,
    rng: random.Random,
    size: int,
) -> frozenset[str]:
    """Structured random neighborhood of about `size` tasks.

    Four kinds: everything of one team, everything touching one engineer,
    everything inside a sprint window, or a mixed random sample of selected and
    deferred tasks that compete for the same roles.
    """
    tasks = {task.task_id: task for task in inputs.tasks}
    selected = sorted(incumbent.selected)
    deferred = sorted(set(tasks) - incumbent.selected)
    kind = rng.choice(("team", "engineer", "window", "mixed"))
    pool: list[str] = []
    if kind == "team":
        team = rng.choice(sorted({task.team_id for task in tasks.values()}))
        pool = [task_id for task_id, task in tasks.items() if task.team_id == team]
    elif kind == "engineer" and incumbent.assignments:
        engineer_id = rng.choice(sorted({row.engineer_id for row in incumbent.assignments}))
        touched = {row.task_id for row in incumbent.assignments if row.engineer_id == engineer_id}
        roles = {row.role_id for row in incumbent.assignments if row.engineer_id == engineer_id}
        pool = sorted(touched) + [task_id for task_id in deferred if roles & set(tasks[task_id].needed)]
    elif kind == "window" and selected:
        low = rng.randint(1, max(1, inputs.sprint_count))
        high = min(inputs.sprint_count, low + rng.randint(0, 2))
        pool = [task_id for task_id in selected
                if incumbent.starts[task_id] <= high and incumbent.ends[task_id] >= low]
        pool += [task_id for task_id in deferred if tasks[task_id].earliest_start_sprint <= high]
    if not pool:
        pool = selected + deferred
    rng.shuffle(pool)
    chosen: list[str] = []
    for task_id in pool:
        if task_id not in chosen:
            chosen.append(task_id)
        if len(chosen) >= size:
            break
    # Always mix in at least one deferred task so selection can change.
    if deferred and not any(task_id in deferred for task_id in chosen):
        chosen.append(rng.choice(deferred))
    return _expand_initiatives(inputs, set(chosen))


def _signature(solution: AllocationSolution) -> tuple[object, ...]:
    return (
        tuple(sorted(solution.selected)),
        tuple((row.task_id, row.sprint_no, row.engineer_id, row.home_team_id, row.work_hours)
              for row in solution.assignments),
        tuple(solution.sp_shares),
    )


def improve_with_lns(
    inputs: Inputs,
    eligible_by_task: dict[str, dict[int, list[str]]],
    initial: AllocationSolution,
    *,
    replan_floor: int,
    dependency_mode: str,
    initiative_mode: str,
    priority_strategy: str,
    max_time_seconds: float,
    random_seed: int,
    max_neighborhoods: int = 32,
    max_stale_random: int = 60,
) -> AllocationSolution:
    """Adaptive LNS: spend the whole budget, grow neighborhoods while they prove out.

    Phase 1 sweeps the deterministic neighborhoods for the current incumbent.
    Phase 2 draws random structured neighborhoods whose size adapts: an exactly
    solved neighborhood without gain grows, one that times out shrinks. Search
    stops when time ends or `max_stale_random` consecutive random tries fail.
    `max_neighborhoods <= 0` disables the search; it no longer caps attempts.
    """
    if initial.solver_status == "OPTIMAL" or max_neighborhoods <= 0:
        return initial

    started = monotonic()
    rng = random.Random(random_seed)
    best = initial
    attempted = improved = stale = 0
    neighborhood_statuses: list[tuple[str, str, bool]] = []
    tried: set[tuple[frozenset[str], tuple[object, ...]]] = set()
    total_tasks = len(inputs.tasks)
    size = min(total_tasks, 6)
    call_budget = max(0.2, min(20.0, max_time_seconds / 10))

    while True:
        remaining = max_time_seconds - (monotonic() - started)
        if remaining <= 0.05 or stale >= max_stale_random:
            break
        signature = _signature(best)
        free = next((group for group in _neighborhoods(inputs, best, limit=max_neighborhoods * 4)
                     if (group, signature) not in tried), None)
        # Alternate: cheap deterministic operators must not starve the larger
        # random neighborhoods that can actually move the late-level objectives.
        deterministic = free is not None and attempted % 3 == 0
        if not deterministic:
            free = _random_neighborhood(inputs, best, rng, size)
            if (free, signature) in tried:
                stale += 1
                continue
        tried.add((free, signature))
        attempted += 1
        candidate = solve_allocation(
            inputs, eligible_by_task,
            replan_floor=replan_floor, dependency_mode=dependency_mode,
            initiative_mode=initiative_mode, priority_strategy=priority_strategy,
            max_time_seconds=min(call_budget, remaining),
            random_seed=random_seed + attempted,
            incumbent=best, free_task_ids=free,
        )
        accepted = (tuple(int(v) for v in candidate.objective_vector)
                    > tuple(int(v) for v in best.objective_vector))
        if len(neighborhood_statuses) < 500:
            neighborhood_statuses.append((",".join(sorted(free)), candidate.solver_status, accepted))
        if accepted:
            improved += 1
            stale = 0
            best = candidate  # a neighborhood proof is not a global optimality proof
        elif not deterministic:
            stale += 1
        if not deterministic:
            if candidate.solver_status == "OPTIMAL" and not accepted:
                size = min(total_tasks, size + max(1, size // 3))
            elif candidate.solver_status != "OPTIMAL":
                size = max(3, size - max(1, size // 4))

    return AllocationSolution(
        **{
            **best.__dict__,
            "solver_status": initial.solver_status,
            "search_method": "full_cp_sat_seed_plus_lns",
            "neighborhoods_attempted": attempted,
            "neighborhoods_improved": improved,
            "neighborhood_statuses": tuple(neighborhood_statuses),
            "wall_time_seconds": initial.wall_time_seconds + (monotonic() - started),
        }
    )


__all__ = ["improve_with_lns"]
