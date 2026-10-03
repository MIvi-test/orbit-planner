"""Константы планировщика: версия алгоритма, коды причин, режимы, нормы KPI."""
from __future__ import annotations

from decimal import Decimal


ALGORITHM = "greedy-priority-topo@2"


ESTIMATE_SOURCE = "matrix_column_sum"


SUBSTITUTION_MODE = "rejected"


DEFERRED_REASON = "M2"  # Отсутствие ресурсов


DEFERRED_REASON_BLOCKED = "M3"  # Отсутствует готовность смежных команд


DONE_STATUS = "Done"


# Причины решений (ADR-022): код из ref_decision_reasons + старый код расхождений
# (M2/M3/M4) для совместимости контракта. Текст для задачи собирается отдельно.
REASON_PLANNED = "PLANNED"


REASON_ROLE_NOT_IN_STAFF = "ROLE_NOT_IN_STAFF"


REASON_ROLE_HOURS = "ROLE_HOURS_EXHAUSTED"


REASON_SKILL_UNAVAILABLE = "SKILL_UNAVAILABLE"


REASON_TEAM_SP = "TEAM_SP_EXHAUSTED"


REASON_BLOCKED = "BLOCKED_BY_DEFERRED"


REASON_ATOMIC = "INITIATIVE_ATOMIC"


REASON_PI_CLOSED = "PI_CLOSED"


REASON_ETC_REQUIRED = "ETC_REQUIRED"


REASON_NOT_FEASIBLE = "NOT_FEASIBLE_NEXT_PI"


CANCEL_REASON = "M4"  # «Превышение плана»: не помещается и в следующий квартал


# Семантика зависимостей (ADR-013, пересмотрена в ADR-028). Блокирующая задача
# передаёт результат блокируемой, когда ЗАКОНЧЕНА: по умолчанию `finish_start`.
# `start_start` (старт после старта предшественника) оставлен как явный режим.
DEPENDENCY_MODE_START_START = "start_start"
DEPENDENCY_MODE_FINISH_START = "finish_start"
DEPENDENCY_MODES = (DEPENDENCY_MODE_START_START, DEPENDENCY_MODE_FINISH_START)
DEFAULT_DEPENDENCY_MODE = DEPENDENCY_MODE_FINISH_START


# Атомарность инициатив (ADR-013). `greedy` — частичная инициатива допустима.
INITIATIVE_MODE_GREEDY = "greedy"


INITIATIVE_MODE_ATOMIC = "atomic"


INITIATIVE_MODES = (INITIATIVE_MODE_GREEDY, INITIATIVE_MODE_ATOMIC)


# Целевая функция (ADR-015): лексикографическая, без перестановок.
OBJECTIVE = "lexicographic: initiatives.priority_rung DESC, task_sequence.topo_order ASC, start_sprint ASC"


FORMULA_VERSION = "2026-10-03.1"


OBJECTIVE_NOTE = (
    "жадный обход без перестановок: deferred_next_pi значит «не влезло при уже "
    "принятых назначениях», а не «невыполнимо в принципе». Счётчики "
    "initiatives_complete/initiatives_partial в params показывают цену этого выбора"
)


# `plan_assignments.hours` — часы ИСПОЛНИТЕЛЯ, а не эквивалент работы (ADR-016).
EFFICIENCY_NOTE = (
    "hours = человеко-часы исполнителя: оставшуюся работу remaining_hours закрывают "
    "remaining_hours × v_engineer_role_coverage.efficiency часов (сейчас везде 1.00)"
)


KPI_TARGETS: dict[str, tuple[Decimal | None, Decimal | None]] = {
    "pi_predictability": (Decimal("80"), Decimal("100")),
    "say_do_ratio": (Decimal("90"), Decimal("105")),
    "bus_factor": (Decimal("2"), None),  # онбординг: «Bus Factor > 1»
}
