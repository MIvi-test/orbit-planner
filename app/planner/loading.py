"""Чтение входа планировщика из базы: сессия строго read-only."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from app import db
from app.planner.queries import (
    TEAM_VELOCITY_HISTORY_SQL,
    TEAM_VELOCITY_OBSERVED_SQL,
    ALL_DEPS_SQL,
    ALL_TASKS_SQL,
    BASELINE_SCHEDULE_SQL,
    BASELINE_STARTS_SQL,
    BUS_FACTOR_SQL,
    COVERAGE_SQL,
    DONE_IN_SPRINT_SQL,
    ENGINEERS_SQL,
    ENGINEER_SKILLS_SQL,
    ESTIMATE_CONFLICT_SQL,
    ESTIMATE_MISMATCH_SQL,
    LAST_UPLOAD_SQL,
    LIVE_DEPS_SQL,
    LIVE_TASKS_SQL,
    PI_SQL,
    SKILL_BUS_FACTOR_SQL,
    SPRINTS_SQL,
    SUBSTITUTION_ROWS_SQL,
    TASK_DATES_SQL,
    TASK_PRODF_SQL,
    TASK_ROLES_SQL,
    TASK_SKILL_REVIEWS_SQL,
    TEAM_CAPACITY_SQL,
)
from app.planner.model import EngineerInput, Inputs, TaskInput


def load_inputs() -> Inputs:
    """Читает всё, что нужно для плана. Только SELECT: сессия read-only."""
    pi = db.query_one(PI_SQL)
    if not pi:
        raise RuntimeError("pi_periods пуст: сначала залейте схему, seed и витрины (docs/RUNBOOK.md)")

    # Календарь читаем один раз: из него и границы спринтов, и множители фонда.
    sprint_rows = db.query_dicts(SPRINTS_SQL, (pi["pi_id"],))
    if len(sprint_rows) != int(pi["sprint_count"]):
        raise RuntimeError(
            f"календарь PI разъехался: sprints содержит {len(sprint_rows)} строк, "
            f"а pi_periods.sprint_count = {pi['sprint_count']} (docs/RUNBOOK.md, раздел 7)"
        )

    roles_by_task: dict[str, dict[int, Decimal]] = defaultdict(dict)
    names_by_task: dict[str, dict[int, str]] = defaultdict(dict)
    unknown_by_task: dict[str, bool] = defaultdict(bool)
    provisional_by_task: dict[str, bool] = defaultdict(bool)
    for row in db.query_dicts(TASK_ROLES_SQL):
        roles_by_task[row["task_id"]][row["role_id"]] = Decimal(row["remaining_hours"])
        names_by_task[row["task_id"]][row["role_id"]] = row["role_name"]
        unknown_by_task[row["task_id"]] |= bool(row.get("remaining_unknown", False))
        provisional_by_task[row["task_id"]] |= bool(row.get("remaining_provisional", False))

    tasks = tuple(
        TaskInput(
            task_id=row["task_id"],
            prodf_id=row["prodf_id"],
            team_id=row["team_id"],
            status=row["status"],
            priority_rung=row["priority_rung"],
            own_rung=row.get("own_rung"),
            business_priority=row.get("business_priority"),
            estimation_sp=Decimal(row["estimation_sp"]),
            summary=row["summary"],
            earliest_start_sprint=int(row["earliest_start_sprint"]),
            topo_order=int(row["topo_order"]),
            remaining=dict(roles_by_task.get(row["task_id"], {})),
            role_names=dict(names_by_task.get(row["task_id"], {})),
            estimate_disputed=bool(row["estimate_disputed"]),
            # «Неизвестно» — только если у задачи не осталось работы ни по одной
            # роли: исчерпанная роль при живых остальных задачу не блокирует.
            remaining_unknown=unknown_by_task[row["task_id"]] and not any(
                hours > 0 for hours in roles_by_task.get(row["task_id"], {}).values()
            ),
            remaining_provisional=provisional_by_task[row["task_id"]],
            remaining_sp=Decimal(row.get("remaining_sp", row["estimation_sp"])),
        )
        for row in db.query_dicts(LIVE_TASKS_SQL)
    )

    skill_requirements: dict[tuple[str, int], set[int]] = defaultdict(set)
    skill_reviews: set[tuple[str, int]] = set()
    skill_names: dict[int, str] = {}
    for row in db.query_dicts(TASK_SKILL_REVIEWS_SQL):
        if row["status"] != "confirmed":
            continue
        key = (row["task_id"], row["role_id"])
        skill_reviews.add(key)
        if row["skill_id"] is not None:
            skill_requirements[key].add(row["skill_id"])
            skill_names[row["skill_id"]] = row["skill_name"]
    engineer_skills: dict[str, set[int]] = defaultdict(set)
    for row in db.query_dicts(ENGINEER_SKILLS_SQL):
        engineer_skills[row["engineer_id"]].add(row["skill_id"])

    engineers: dict[str, dict[str, Any]] = {}
    for row in db.query_dicts(ENGINEERS_SQL):
        item = engineers.setdefault(
            row["engineer_id"],
            {
                "role_id": row["role_id"],
                "grade": row["grade"],
                "total_capacity_rate": Decimal(row["total_capacity_rate"]),
                "orbits": {},
            },
        )
        item["orbits"][row["team_id"]] = Decimal(row["capacity_rate"])

    # Кандидаты на роль и множитель часов — из вьюхи покрытия (ADR-012).
    coverage: dict[tuple[str, int], Decimal] = {}
    for row in db.query_dicts(COVERAGE_SQL):
        coverage[(row["engineer_id"], row["role_id"])] = Decimal(row["efficiency"])
    # Страховка: инженера нет в вьюхе — свою родную роль он всё равно закрывает.
    # Иначе человек молча выпал бы из плана, а инварианты этого не заметили бы.
    for engineer_id, item in engineers.items():
        coverage.setdefault((engineer_id, item["role_id"]), Decimal("1"))

    conflicts = db.query_one(ESTIMATE_CONFLICT_SQL) or {}
    substitutions = db.query_one(SUBSTITUTION_ROWS_SQL) or {}
    estimate_mismatches = db.query_dicts(ESTIMATE_MISMATCH_SQL)
    if estimate_mismatches:
        raise RuntimeError(
            "оценка задач расходится с ролевой сметой: " +
            ", ".join(row["task_id"] for row in estimate_mismatches[:10])
        )

    last_upload = db.query_one(LAST_UPLOAD_SQL, (pi["pi_id"],)) or {}
    baseline_rows = db.query_dicts(BASELINE_SCHEDULE_SQL, (pi["pi_id"],))
    done_in_sprint: dict[int, set[str]] = defaultdict(set)
    for row in db.query_dicts(DONE_IN_SPRINT_SQL, (pi["pi_id"],)):
        done_in_sprint[int(row["sprint_no"])].add(row["task_id"])
    task_dates = db.query_dicts(TASK_DATES_SQL)

    history_rows = db.query_dicts(TEAM_VELOCITY_HISTORY_SQL)
    velocity_history = {
        row["team_id"]: (Decimal(row["velocity_sum"]), int(row["points"])) for row in history_rows
    }
    team_capacity: dict[str, Decimal] = {}
    for row in db.query_dicts(TEAM_CAPACITY_SQL):
        if row["available_sp_per_sprint"] is None:
            raise RuntimeError(
                f"у команды {row['team_id']} нет истории производительности: ёмкость в SP "
                f"не вычислить (ETL блокирует такой датасет, TEAM_WITHOUT_HISTORY)"
            )
        team_capacity[row["team_id"]] = Decimal(row["available_sp_per_sprint"])

    return Inputs(
        pi_id=pi["pi_id"],
        sprint_count=int(pi["sprint_count"]),
        fte_hours_per_sprint=int(pi["fte_hours_per_sprint"]),
        fund_factor=Decimal(pi["fund_factor"]),
        pi_days=int(pi["pi_days"]),
        sprint_factors={
            int(row["sprint_no"]): Decimal(row["factor"]) for row in sprint_rows
        },
        team_sp_per_sprint=team_capacity,
        velocity_history=velocity_history,
        velocity_observed=tuple(
            (row["team_id"], int(row["sprint_no"]), Decimal(row["delivered_sp"]))
            for row in db.query_dicts(TEAM_VELOCITY_OBSERVED_SQL, (pi["pi_id"],))
        ),
        focus_factors={row["team_id"]: Decimal(row["focus_factor"]) for row in history_rows},
        tasks=tasks,
        engineers=tuple(
            EngineerInput(
                engineer_id=engineer_id,
                role_id=item["role_id"],
                grade=item["grade"],
                total_capacity_rate=item["total_capacity_rate"],
                orbits=item["orbits"],
            )
            for engineer_id, item in sorted(engineers.items())
        ),
        coverage=coverage,
        deps=tuple(
            (row["blocking_task_id"], row["blocked_task_id"], int(row["min_gap_sprints"]))
            for row in db.query_dicts(LIVE_DEPS_SQL)
        ),
        all_deps=tuple(
            (row["blocking_task_id"], row["blocked_task_id"], int(row["min_gap_sprints"]))
            for row in db.query_dicts(ALL_DEPS_SQL)
        ),
        done_task_dates={
            row["task_id"]: (row["actual_start"], row["actual_end"])
            for row in task_dates if row["status"] == "Done"
        },
        task_actual_starts={
            row["task_id"]: row["actual_start"]
            for row in task_dates if row["actual_start"] is not None
        },
        sprints={
            row["sprint_no"]: (row["start_date"], row["end_date"]) for row in sprint_rows
        },
        all_tasks=tuple(
            (
                row["task_id"],
                row["status"],
                Decimal(row["estimation_sp"]),
                Decimal(row["remaining_hh"]),
            )
            for row in db.query_dicts(ALL_TASKS_SQL)
        ),
        bus_factor=tuple(
            (row["role_name"], int(row["bus_factor"]), Decimal(row["demand_hh"]))
            for row in db.query_dicts(BUS_FACTOR_SQL)
        ),
        estimate_conflicts=int(conflicts.get("issues") or 0),
        estimate_conflict_warnings=int(conflicts.get("warnings") or 0),
        active_substitutions=int(substitutions.get("active") or 0),
        estimate_validated=not estimate_mismatches,
        actuals_upload_id=last_upload.get("upload_id"),
        last_reported_sprint=int(last_upload.get("sprint_no") or 0),
        done_in_sprint={no: frozenset(ids) for no, ids in done_in_sprint.items()},
        task_prodf={row["task_id"]: row["prodf_id"] for row in db.query_dicts(TASK_PRODF_SQL)},
        baseline_schedule={
            row["task_id"]: (row["decision"], row["start_sprint"], row["end_sprint"])
            for row in baseline_rows
        },
        baseline_sp={row["task_id"]: Decimal(row["planned_sp"]) for row in baseline_rows},
        baseline_run_id=int(baseline_rows[0]["run_id"]) if baseline_rows else None,
        skill_bus_factor=tuple(
            (row["skill_name"], int(row["bus_factor"]), bool(row["in_demand"]),
             bool(row["critical"]))
            for row in db.query_dicts(SKILL_BUS_FACTOR_SQL)
        ),
        skill_requirements={key: frozenset(ids) for key, ids in skill_requirements.items()},
        skill_reviews=frozenset(skill_reviews),
        engineer_skills={key: frozenset(ids) for key, ids in engineer_skills.items()},
        skill_names=skill_names,
    )


def load_baseline_starts() -> dict[str, int]:
    """Старты базового прогона — на пересчёте по ним видно сдвиги (yellow)."""
    return {
        row["task_id"]: int(row["start_sprint"]) for row in db.query_dicts(BASELINE_STARTS_SQL)
    }
