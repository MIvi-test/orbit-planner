"""Вход и выход планировщика: что прочитано (`Inputs`) и что ляжет в контракт (`Plan`)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


# ---------------------------------------------------------------------------
#  ВХОД: то же, что планировщик прочитал, но уже разложенное по смыслу
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TaskInput:
    """Живая задача: что просит по ролям и в каких рамках может стартовать."""

    task_id: str
    prodf_id: str
    team_id: str
    status: str
    priority_rung: int | None  # приоритет инициативы из датасета (MAX(rung) её задач)
    estimation_sp: Decimal
    summary: str | None
    earliest_start_sprint: int
    topo_order: int
    remaining: dict[int, Decimal]  # role_id -> ЧЧ; может быть 0
    role_names: dict[int, str]
    estimate_disputed: bool
    remaining_unknown: bool = False
    # Остаток оценён как смета − факт и не подтверждён ETC (B-6).
    remaining_provisional: bool = False
    remaining_sp: Decimal | None = None
    # Собственный rung задачи и явный бизнес-приоритет инициативы (DA-11).
    own_rung: int | None = None
    business_priority: int | None = None

    @property
    def sp_to_plan(self) -> Decimal:
        return self.estimation_sp if self.remaining_sp is None else self.remaining_sp

    @property
    def needed(self) -> dict[int, Decimal]:
        """Роли, по которым реально остались часы (нулевые не планируем)."""
        return {role_id: hours for role_id, hours in self.remaining.items() if hours > 0}

    @property
    def demand_hh(self) -> Decimal:
        return sum(self.remaining.values(), Decimal("0"))


@dataclass(frozen=True)
class EngineerInput:
    engineer_id: str
    role_id: int
    grade: str
    total_capacity_rate: Decimal
    orbits: dict[str, Decimal]  # team_id -> ставка на орбите


@dataclass(frozen=True)
class Inputs:
    pi_id: str
    sprint_count: int
    fte_hours_per_sprint: int
    # Календарь: PI начинается с календарного квартала и длится шесть
    # двухнедельных спринтов (ADR-025).
    # `fund_factor` — сколько полных спринтов в PI (сейчас 84/14 = 6.0000),
    # `sprint_factors` — множитель фонда каждого спринта (сейчас все 1.0000).
    # Фонд ставки за PI = fte_hours_per_sprint × fund_factor = 480 ЧЧ.
    fund_factor: Decimal
    pi_days: int
    sprint_factors: dict[int, Decimal]
    team_sp_per_sprint: dict[str, Decimal]
    tasks: tuple[TaskInput, ...]
    engineers: tuple[EngineerInput, ...]
    coverage: dict[tuple[str, int], Decimal]  # (engineer_id, role_id) -> efficiency
    deps: tuple[tuple[str, str, int], ...]  # (blocking, blocked, min_gap)
    sprints: dict[int, tuple[date, date]]
    all_tasks: tuple[tuple[str, str, Decimal, Decimal], ...]  # id, статус, SP, остаток ЧЧ
    bus_factor: tuple[tuple[str, int, Decimal], ...]  # роль, BF, спрос ЧЧ
    estimate_conflicts: int
    estimate_conflict_warnings: int
    active_substitutions: int
    estimate_validated: bool = True
    # --- факт спринтов и первоначальный план (ADR-021, ADR-023) ---------
    actuals_upload_id: int | None = None
    last_reported_sprint: int = 0  # последний спринт, по которому загружен факт
    done_in_sprint: dict[int, frozenset[str]] = field(default_factory=dict)
    task_prodf: dict[str, str] = field(default_factory=dict)  # все задачи, и Done тоже
    # task_id -> (decision, start, end) канонического базового прогона
    baseline_schedule: dict[str, tuple[str, int | None, int | None]] = field(default_factory=dict)
    baseline_sp: dict[str, Decimal] = field(default_factory=dict)
    baseline_run_id: int | None = None
    # Bus Factor по компетенциям: (навык, носителей, in_demand, critical)
    skill_bus_factor: tuple[tuple[str, int, bool, bool], ...] = ()
    skill_requirements: dict[tuple[str, int], frozenset[int]] = field(default_factory=dict)
    skill_reviews: frozenset[tuple[str, int]] = frozenset()
    engineer_skills: dict[str, frozenset[int]] = field(default_factory=dict)
    skill_names: dict[int, str] = field(default_factory=dict)
    all_deps: tuple[tuple[str, str, int], ...] = ()
    done_task_dates: dict[str, tuple[date | None, date | None]] = field(default_factory=dict)
    task_actual_starts: dict[str, date] = field(default_factory=dict)
    # Ёмкость по истории и закрытым спринтам (DA-27, ADR-030): team -> (сумма скоростей, число точек).
    velocity_history: dict[str, tuple[Decimal, int]] = field(default_factory=dict)
    # Наблюдения текущего PI: (команда, спринт, поставленные SP).
    velocity_observed: tuple[tuple[str, int, Decimal], ...] = ()
    focus_factors: dict[str, Decimal] = field(default_factory=dict)
    preferred_engineers: dict[tuple[str, int], frozenset[str]] = field(default_factory=dict)
    sprint_orbit_rates: dict[tuple[str, str, int], Decimal] = field(default_factory=dict)
    source_sha256: str | None = None
    config_sha256: str | None = None
    etl_version: str | None = None

    @property
    def fund_hours_per_fte(self) -> Decimal:
        """Фонд одной ставки за весь PI в ЧЧ: сейчас 80 × 6 = 480."""
        return (self.fund_factor * Decimal(self.fte_hours_per_sprint)).quantize(
            Decimal("0.01")
        )

    def short_sprints_note(self) -> str:
        """Короткие спринты человеческим языком — для логов прогона и UI."""
        short = {no: f for no, f in sorted(self.sprint_factors.items()) if f < 1}
        if not short:
            return "нет"
        return ", ".join(f"спринт {no} — ×{factor}" for no, factor in short.items())


# ---------------------------------------------------------------------------
#  ВЫХОД: ровно то, что ляжет в таблицы контракта
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScheduleRow:
    task_id: str
    start_sprint: int | None
    end_sprint: int | None
    forecast_end_date: date | None
    decision: str
    decision_reason: str | None
    reason_code: str | None = None
    reason_text: str | None = None
    reason_details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Assignment:
    task_id: str
    sprint_no: int
    engineer_id: str
    role_id: int
    hours: Decimal
    home_team_id: str
    serving_team_id: str
    work_hours: Decimal | None = None  # эквивалент выполненной ролевой сметы


@dataclass(frozen=True)
class AlertRow:
    sprint_no: int
    level: str
    alert_type: str
    entity_type: str
    entity_id: str
    message: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class KpiRow:
    sprint_no: int
    kpi_code: str
    value: Decimal | None
    target_min: Decimal | None
    target_max: Decimal | None
    details: dict[str, Any]
    kind: str = "forecast"  # forecast | actual (ТЗ: прогноз отличать от факта)
    calculation_status: str = "calculated"


@dataclass(frozen=True)
class BaselineRow:
    task_id: str
    planned_sp: Decimal
    committed: bool


@dataclass(frozen=True)
class StateRow:
    task_id: str
    as_of_sprint: int
    status: str
    remaining_hh: Decimal
    remaining_sp: Decimal
    forecast_end_sprint: int | None


@dataclass(frozen=True)
class CapacityRow:
    """Ёмкость команды, с которой построен прогон (таблица `plan_team_capacity`)."""

    team_id: str
    history_points: int
    observed_points: int
    avg_velocity: Decimal
    focus_factor: Decimal
    available_sp_per_sprint: Decimal
    observed_through_sprint: int


@dataclass(frozen=True)
class Plan:
    pi_id: str
    as_of_sprint: int
    status: str
    note: str
    params: dict[str, Any]
    schedule: tuple[ScheduleRow, ...]
    assignments: tuple[Assignment, ...]
    alerts: tuple[AlertRow, ...]
    kpis: tuple[KpiRow, ...]
    baseline: tuple[BaselineRow, ...]
    states: tuple[StateRow, ...]
    sp_shares: tuple[tuple[str, int, Decimal], ...] = ()  # (task_id, sprint_no, sp), ADR-020
    actuals_upload_id: int | None = None
    role_demands: tuple[tuple[str, int, Decimal], ...] = ()
    graph_bounds: tuple[tuple[str, int], ...] = ()
    team_capacity: tuple[CapacityRow, ...] = ()
    capacity_snapshot: tuple[tuple[str, str, int, Decimal], ...] = ()

    @property
    def in_quarter(self) -> tuple[ScheduleRow, ...]:
        return tuple(row for row in self.schedule if row.decision == "in_quarter")

    @property
    def deferred(self) -> tuple[ScheduleRow, ...]:
        return tuple(row for row in self.schedule if row.decision != "in_quarter")
