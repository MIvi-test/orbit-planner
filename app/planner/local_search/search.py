"""Large-neighborhood repair around a feasible CP-SAT plan."""
from __future__ import annotations

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
) -> AllocationSolution:
    """Try bounded repairs while preserving all decisions outside each neighborhood."""
    if initial.solver_status == "OPTIMAL" or max_neighborhoods <= 0:
        return initial

    started = monotonic()
    best = initial
    attempted = 0
    improved = 0
    neighborhood_statuses: list[tuple[str, str, bool]] = []
    attempted_neighborhoods: set[tuple[frozenset[str], tuple[object, ...]]] = set()
    # Retain time for a candidate check and leave most of the budget to repair.
    call_budget = max(0.05, min(0.75, max_time_seconds / max(4, min(16, max_neighborhoods + 1))))

    index = 0
    while attempted < max_neighborhoods:
        neighborhoods = _neighborhoods(inputs, best, limit=max_neighborhoods * 4)
        signature: tuple[object, ...] = (
            tuple(sorted(best.selected)),
            tuple((row.task_id, row.sprint_no, row.engineer_id, row.home_team_id, row.work_hours)
                  for row in best.assignments),
            tuple(best.sp_shares),
        )
        free_task_ids = next((group for group in neighborhoods
                              if (group, signature) not in attempted_neighborhoods), None)
        if free_task_ids is None:
            break
        elapsed = monotonic() - started
        remaining = max_time_seconds - elapsed
        if remaining <= 0.05:
            break
        attempted += 1
        attempted_neighborhoods.add((free_task_ids, signature))
        candidate = solve_allocation(
            inputs,
            eligible_by_task,
            replan_floor=replan_floor,
            dependency_mode=dependency_mode,
            initiative_mode=initiative_mode,
            priority_strategy=priority_strategy,
            max_time_seconds=min(call_budget, remaining),
            random_seed=random_seed + index + 1,
            incumbent=best,
            free_task_ids=free_task_ids,
        )
        candidate_vector = tuple(int(value) for value in candidate.objective_vector)
        best_vector = tuple(int(value) for value in best.objective_vector)
        accepted = candidate_vector > best_vector
        neighborhood_statuses.append((
            ",".join(sorted(free_task_ids)), candidate.solver_status, accepted,
        ))
        if accepted:
            improved += 1
            # A repaired-neighborhood proof is not a global optimality proof.
            best = candidate
        index += 1

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
