"""Deterministic staffing packages on a copy of a pinned planner snapshot."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from app import auth, db, planner
from app.assistant import conversations, facts, snapshots
from app.planner.constants import ALGORITHM, FORMULA_VERSION

MAX_ALTERNATIVES = 3
MAX_MEASURES = 5


class ScenarioError(ValueError):
    pass


def _rate(value: Any, field: str, *, allow_zero: bool = False) -> Decimal:
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ScenarioError("invalid_" + field) from exc
    if not rate.is_finite() or rate > 1 or (rate < 0 if allow_zero else rate <= 0):
        raise ScenarioError("invalid_" + field)
    return rate


def _integer(value: Any, field: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ScenarioError("invalid_" + field)
    return value


def _person(inputs: planner.Inputs, engineer_id: Any) -> planner.EngineerInput:
    if not isinstance(engineer_id, str):
        raise ScenarioError("engineer_required")
    worker = next((row for row in inputs.engineers if row.engineer_id == engineer_id), None)
    if worker is None:
        raise ScenarioError("engineer_not_found")
    return worker


def _available(inputs: planner.Inputs, worker: planner.EngineerInput,
               team_id: str, sprint: int) -> Decimal:
    return inputs.sprint_orbit_rates.get((worker.engineer_id, team_id, sprint),
                                         worker.orbits.get(team_id, Decimal(0)))


def _deduct(inputs: planner.Inputs, worker: planner.EngineerInput,
            rates: dict[tuple[str, str, int], Decimal], sprint: int, amount: Decimal,
            *, exclude: str | None = None) -> None:
    remaining = amount
    teams = sorted(worker.orbits, key=lambda team: (-rates.get((worker.engineer_id, team, sprint),
                                                               worker.orbits[team]), team))
    for team in teams:
        if team == exclude:
            continue
        key = (worker.engineer_id, team, sprint)
        current = rates.get(key, worker.orbits[team])
        taken = min(current, remaining)
        rates[key] = current - taken
        remaining -= taken
        if remaining == 0:
            return
    raise ScenarioError("insufficient_worker_capacity")


def _skills(inputs: planner.Inputs, role_id: int, provided: Any) -> frozenset[int]:
    required = frozenset(skill for (_task, role), skills in inputs.skill_requirements.items()
                         if role == role_id for skill in skills)
    if provided is None:
        raise ScenarioError("skill_ids_required")
    if (not isinstance(provided, list) or any(type(skill) is not int or skill < 1 for skill in provided)):
        raise ScenarioError("invalid_skill_ids")
    selected = frozenset(provided)
    if not required.issubset(selected):
        raise ScenarioError("required_skills_missing")
    return selected


def _apply(inputs: planner.Inputs, measure: dict[str, Any], number: int,
           earliest_start: int) -> tuple[planner.Inputs, dict[str, Any]]:
    kind = measure.get("kind")
    if kind not in {"hire", "loan", "train"}:
        raise ScenarioError("invalid_measure_kind")
    team = measure.get("team_id")
    if not isinstance(team, str) or team not in inputs.team_sp_per_sprint:
        raise ScenarioError("team_not_found")
    start = _integer(measure.get("start_sprint"), "start_sprint",
                     max(1, inputs.last_reported_sprint + 1, earliest_start),
                     inputs.sprint_count)
    rate = _rate(measure.get("rate"), "rate")
    role = measure.get("role_id")
    if kind != "loan":
        _integer(role, "role_id", 1, 2**31 - 1)
    if kind == "loan":
        worker = _person(inputs, measure.get("engineer_id"))
        role = worker.role_id
    if not any(task.team_id == team and role in task.needed for task in inputs.tasks):
        raise ScenarioError("no_role_demand")
    rates = dict(inputs.sprint_orbit_rates)
    people = inputs.engineers
    coverage = dict(inputs.coverage)
    skills = dict(inputs.engineer_skills)
    assumptions: dict[str, Any] = {}
    if kind == "hire":
        lag = _integer(measure.get("hiring_lag_sprints"), "hiring_lag_sprints", 0, inputs.sprint_count)
        effective = start + lag
        if effective > inputs.sprint_count:
            raise ScenarioError("measure_effect_outside_pi")
        skill_ids = _skills(inputs, role, measure.get("skill_ids"))
        worker_id = f"assistant-hire-{number}"
        if worker_id in {worker.engineer_id for worker in people}:
            raise ScenarioError("virtual_worker_collision")
        people = (*people, planner.EngineerInput(worker_id, role, "Scenario", rate, {team: rate}))
        coverage[worker_id, role] = Decimal(1)
        skills[worker_id] = skill_ids
        for sprint in range(1, min(effective, inputs.sprint_count + 1)):
            rates[worker_id, team, sprint] = Decimal(0)
        assumptions = {"effective_sprint": effective, "skill_ids": sorted(skill_ids)}
    elif kind == "loan":
        if (worker.engineer_id, role) not in coverage:
            raise ScenarioError("worker_role_unavailable")
        for sprint in range(start, inputs.sprint_count + 1):
            _deduct(inputs, worker, rates, sprint, rate, exclude=team)
            key = (worker.engineer_id, team, sprint)
            rates[key] = rates.get(key, worker.orbits.get(team, Decimal(0))) + rate
            if rates[key] > worker.total_capacity_rate:
                raise ScenarioError("worker_capacity_exceeded")
        people = tuple(replace(item, orbits={**item.orbits, team: item.orbits.get(team, Decimal(0))})
                       if item.engineer_id == worker.engineer_id else item for item in people)
        assumptions = {"effective_sprint": start, "donor_engineer_id": worker.engineer_id}
    else:
        trainee = _person(inputs, measure.get("trainee_id"))
        mentor = _person(inputs, measure.get("mentor_id"))
        if trainee.engineer_id == mentor.engineer_id or (trainee.engineer_id, role) in coverage:
            raise ScenarioError("invalid_training_pair")
        duration = _integer(measure.get("training_sprints"), "training_sprints", 1, inputs.sprint_count)
        mentor_cost = _rate(measure.get("mentor_rate"), "mentor_rate")
        effective = start + duration
        if effective > inputs.sprint_count:
            raise ScenarioError("measure_effect_outside_pi")
        skill_ids = _skills(inputs, role, measure.get("skill_ids"))
        if (mentor.engineer_id, role) not in coverage or not skill_ids.issubset(
                inputs.engineer_skills.get(mentor.engineer_id, frozenset())):
            raise ScenarioError("mentor_skill_unavailable")
        worker_id = f"assistant-trained-{number}-{trainee.engineer_id}"
        if worker_id in {worker.engineer_id for worker in people}:
            raise ScenarioError("virtual_worker_collision")
        for sprint in range(start, inputs.sprint_count + 1):
            _deduct(inputs, trainee, rates, sprint, rate)
        for sprint in range(start, min(effective, inputs.sprint_count + 1)):
            key = (mentor.engineer_id, team, sprint)
            current = rates.get(key, mentor.orbits.get(team, Decimal(0)))
            if current < mentor_cost:
                raise ScenarioError("insufficient_mentor_capacity")
            rates[key] = current - mentor_cost
        people = (*people, planner.EngineerInput(worker_id, role, "Scenario", rate, {team: rate}))
        coverage[worker_id, role] = Decimal(1)
        skills[worker_id] = skill_ids
        for sprint in range(1, min(effective, inputs.sprint_count + 1)):
            rates[worker_id, team, sprint] = Decimal(0)
        assumptions = {"effective_sprint": effective, "skill_ids": sorted(skill_ids),
                       "training_rate_lost": str(rate), "mentor_rate_lost": str(mentor_cost),
                       "trainee_id": trainee.engineer_id, "mentor_id": mentor.engineer_id}
    return replace(inputs, engineers=people, coverage=coverage, engineer_skills=skills,
                   sprint_orbit_rates=rates), {"kind": kind, "team_id": team,
                                               "role_id": role, "rate": str(rate),
                                               "start_sprint": start, **assumptions}


def _difference(before: planner.Plan, after: planner.Plan, inputs: planner.Inputs) -> dict[str, Any]:
    old = {row.task_id: row for row in before.schedule}
    new = {row.task_id: row for row in after.schedule}
    old_in = {key for key, row in old.items() if row.decision == "in_quarter"}
    new_in = {key for key, row in new.items() if row.decision == "in_quarter"}
    initiatives: dict[str, set[str]] = {}
    for task in inputs.tasks:
        initiatives.setdefault(task.prodf_id, set()).add(task.task_id)
    old_kpis = {(row.kpi_code, row.sprint_no, row.kind): row for row in before.kpis}
    new_kpis = {(row.kpi_code, row.sprint_no, row.kind): row for row in after.kpis}
    kpis = []
    for key in sorted(old_kpis.keys() | new_kpis.keys()):
        prior, current = old_kpis.get(key), new_kpis.get(key)
        stale_competence = key[0] == "bus_factor"
        delta = (current.value - prior.value if not stale_competence and prior and current and prior.value is not None
                 and current.value is not None and prior.calculation_status == "calculated"
                 and current.calculation_status == "calculated" else None)
        kpis.append({"code": key[0], "sprint": key[1], "kind": key[2],
                     "before": facts.plain(prior), "after": None if stale_competence else facts.plain(current),
                     "delta": facts.plain(delta),
                     "status": "calculated" if delta is not None else "unavailable",
                     "reason": ("Состав носителей навыков меняется по спринтам; исходный KPI нельзя "
                                "считать результатом сценария." if stale_competence else None)})
    shifted = [{"task_id": key, "before": facts.plain(old[key]), "after": facts.plain(new[key])}
               for key in sorted(old.keys() & new.keys()) if old[key] != new[key]]
    old_assignments = {(row.task_id, row.sprint_no, row.engineer_id, row.role_id): row
                       for row in before.assignments}
    new_assignments = {(row.task_id, row.sprint_no, row.engineer_id, row.role_id): row
                       for row in after.assignments}
    changed_assignments = [{"key": facts.plain(key),
                            "before": facts.plain(old_assignments.get(key)),
                            "after": facts.plain(new_assignments.get(key))}
                           for key in sorted(old_assignments.keys() | new_assignments.keys())
                           if old_assignments.get(key) != new_assignments.get(key)]
    impacted_ids = {row["task_id"] for row in shifted}
    impacted_ids.update(row["key"][0] for row in changed_assignments)
    affected_teams = {task.team_id for task in inputs.tasks if task.task_id in impacted_ids}
    for row in changed_assignments:
        for assignment in (row["before"], row["after"]):
            if assignment:
                affected_teams.update((assignment["home_team_id"], assignment["serving_team_id"]))
    return {"kpis": kpis, "gained_tasks": sorted(new_in - old_in),
            "lost_tasks": sorted(old_in - new_in),
            "restored_initiatives": sorted(name for name, ids in initiatives.items()
                                           if ids <= new_in and not ids <= old_in),
            "lost_initiatives": sorted(name for name, ids in initiatives.items()
                                       if ids <= old_in and not ids <= new_in),
            "changed_schedule": shifted, "changed_assignments": changed_assignments,
            "affected_teams": sorted(affected_teams)}


def evaluate(snapshot_id: UUID, alternatives: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(alternatives, list) or not 1 <= len(alternatives) <= MAX_ALTERNATIVES:
        raise ScenarioError("invalid_alternatives")
    inputs, baseline, baseline_starts, options = snapshots.replay(snapshot_id)
    results = []
    for alternative in alternatives:
        measures = alternative.get("measures") if isinstance(alternative, dict) else None
        if not isinstance(measures, list) or not 1 <= len(measures) <= MAX_MEASURES:
            raise ScenarioError("invalid_measures")
        changed = inputs
        applied = []
        for number, measure in enumerate(measures, 1):
            if not isinstance(measure, dict):
                raise ScenarioError("invalid_measure")
            changed, description = _apply(changed, measure, number, baseline.as_of_sprint)
            applied.append(description)
        proposed = planner.build_plan(changed, baseline_starts=baseline_starts, **options)
        results.append({"measures": applied, "result": _difference(baseline, proposed, inputs),
                        "plan_status": proposed.status, "verified_by_scenario": True,
                        "limitations": ["KPI bus_factor недоступен: состав навыков зависит от спринта."]})
    return {"snapshot_id": str(snapshot_id), "status": "completed", "baseline_status": baseline.status,
            "alternatives": results,
            "interpretation": "Каждый пакет пересчитан целиком; эффекты отдельных мер не суммируются."}


def enqueue(principal: auth.Principal, conversation_id: str, raw: Any,
            idempotency_key: str | None) -> dict[str, str]:
    if not principal.allows("planner"):
        raise conversations.ChatError("planner_required", 403)
    if (not isinstance(raw, dict) or set(raw) != {"expected_context_revision", "alternatives"}
            or type(raw["expected_context_revision"]) is not int
            or not isinstance(raw["alternatives"], list)
            or not 1 <= len(raw["alternatives"]) <= MAX_ALTERNATIVES
            or any(not isinstance(item, dict) or not isinstance(item.get("measures"), list)
                   or not 1 <= len(item["measures"]) <= MAX_MEASURES for item in raw["alternatives"])):
        raise conversations.ChatError("invalid_scenario_request")
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
        raise conversations.ChatError("idempotency_key_required")
    cid = conversations._uuid(conversation_id)
    digest = hashlib.sha256(json.dumps({"conversation_id": str(cid), **raw},
                                     sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    job_id = uuid4()
    with db.transaction(operation="assistant_scenario_enqueue") as cur:
        cur.execute("SELECT pg_advisory_xact_lock(90340212, hashtext(%s))",
                    (principal.owner_key + ":" + idempotency_key,))
        cur.execute("SELECT job_id, request_sha256, status FROM public.assistant_jobs "
                    "WHERE owner_key = %s AND idempotency_key = %s",
                    (principal.owner_key, idempotency_key))
        existing = cur.fetchone()
        if existing:
            if existing["request_sha256"] != digest:
                raise conversations.ChatError("idempotency_conflict", 409)
            return {"job_id": str(existing["job_id"]), "status": existing["status"]}
        context = conversations._joined(cur, cid, principal.owner_key, lock=True)
        if context["revision"] != raw["expected_context_revision"]:
            raise conversations.ChatError("context_revision_conflict", 409)
        if context["scope"] != "planning" or not context["snapshot_id"]:
            raise conversations.ChatError("planning_context_required")
        conversations._no_active_job(cur, cid)
        payload = {"context_revision": context["revision"], "snapshot_id": str(context["snapshot_id"]),
                   "alternatives": raw["alternatives"],
                   "principal": {"name": principal.name, "role": principal.role,
                                 "source": principal.source, "user_id": principal.user_id}}
        cur.execute("INSERT INTO public.assistant_jobs "
                    "(job_id, owner_key, conversation_id, kind, status, idempotency_key, "
                    "request_sha256, input_payload, deadline_at) "
                    "VALUES (%s, %s, %s, 'scenario', 'queued', %s, %s, %s, now() + interval '120 seconds')",
                    (job_id, principal.owner_key, cid, idempotency_key, digest, Jsonb(payload)))
    return {"job_id": str(job_id), "status": "queued"}


def publish(job: dict[str, Any], result: dict[str, Any]) -> bool:
    with db.transaction(operation="assistant_scenario_publish") as cur:
        cur.execute("SELECT status, attempt_count FROM public.assistant_jobs WHERE job_id = %s FOR UPDATE",
                    (job["job_id"],))
        current = cur.fetchone()
        if (current is None or current["status"] != "running"
                or current["attempt_count"] != job["attempt_count"]):
            return False
        cur.execute("SELECT now() < lease_until AND now() < deadline_at AS valid "
                    "FROM public.assistant_jobs WHERE job_id = %s", (job["job_id"],))
        if not cur.fetchone()["valid"]:
            return False
        scenario_id, evidence_id = uuid4(), uuid4()
        cur.execute("INSERT INTO public.assistant_scenario_results "
                    "(scenario_result_id, conversation_id, snapshot_id, input_payload, result_payload, engine_version) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (scenario_id, job["conversation_id"], UUID(job["input_payload"]["snapshot_id"]),
                     Jsonb(job["input_payload"]["alternatives"]), Jsonb(result),
                     ALGORITHM + "/" + FORMULA_VERSION))
        cur.execute("INSERT INTO public.assistant_evidence "
                    "(evidence_id, conversation_id, source_type, source_ref, payload) "
                    "VALUES (%s, %s, 'scenario', %s, %s)",
                    (evidence_id, job["conversation_id"], str(scenario_id), Jsonb(result)))
        output = {**result, "scenario_result_id": str(scenario_id),
                  "evidence_ids": [str(evidence_id)]}
        cur.execute("UPDATE public.assistant_jobs SET status = 'completed', result_payload = %s, "
                    "lease_until = NULL, updated_at = now() WHERE job_id = %s",
                    (Jsonb(output), job["job_id"]))
        return True
