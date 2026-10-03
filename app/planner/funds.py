"""Фонд часов и SP: единственное место, где ресурсы списываются и возвращаются."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal, ROUND_DOWN
from typing import Any

from app.planner.constants import MIN_CHUNK_HH
from app.planner.model import Assignment, EngineerInput, Inputs, TaskInput


# ---------------------------------------------------------------------------
#  ФОНД ЧАСОВ: единственное место, где часы считаются
# ---------------------------------------------------------------------------
class _Funds:
    """Часы по орбитам и занятость людей и команд.

    «Орбита с приоритетом» (ADR-001): сначала тратится бюджет своей орбиты,
    невыбранный остаток чужой орбиты уходит в заём. Инвариант
    `ENGINEER_OVERLOAD` проверяет СУММУ по всем орбитам, а сумма ставок равна
    `total_capacity_rate`, поэтому расход «по орбитам» заведомо не превышает
    общий фонд — но общий фонд всё равно проверяется отдельно: данные могут
    оказаться несогласованными, и падать об это не хочется.
    """

    def __init__(self, inputs: Inputs) -> None:
        self.fte = Decimal(inputs.fte_hours_per_sprint)
        # Множитель фонда по спринтам читается из календаря. Нет ключа —
        # считаем спринт полным: дефолт для тестовых календарей.
        self.factors: dict[int, Decimal] = dict(inputs.sprint_factors)
        self.engineers: dict[str, EngineerInput] = {e.engineer_id: e for e in inputs.engineers}
        self.preferred = inputs.preferred_engineers
        self.sprint_orbit_rates = inputs.sprint_orbit_rates
        self._spent: dict[tuple[str, str, int], Decimal] = defaultdict(Decimal)
        self.used_sp: dict[tuple[str, int], Decimal] = defaultdict(Decimal)

    def sprint_factor(self, sprint_no: int) -> Decimal:
        """Доля фонда полного спринта, которую даёт спринт `sprint_no`."""
        return self.factors.get(sprint_no, Decimal("1"))

    # ---- часы ------------------------------------------------------------
    def orbit_left(self, engineer_id: str, team_id: str, sprint_no: int) -> Decimal:
        rate = self.sprint_orbit_rates.get(
            (engineer_id, team_id, sprint_no),
            self.engineers[engineer_id].orbits.get(team_id, Decimal(0)),
        )
        budget = rate * self.fte * self.sprint_factor(sprint_no)
        return budget - self._spent[(engineer_id, team_id, sprint_no)]

    def total_left(self, engineer_id: str, sprint_no: int) -> Decimal:
        engineer = self.engineers[engineer_id]
        spent = sum(
            (self._spent[(engineer_id, team_id, sprint_no)] for team_id in engineer.orbits),
            Decimal("0"),
        )
        rate = sum((self.sprint_orbit_rates.get((engineer_id, team_id, sprint_no), orbit_rate)
                    for team_id, orbit_rate in engineer.orbits.items()), Decimal(0))
        return min(engineer.total_capacity_rate, rate) * self.fte * self.sprint_factor(sprint_no) - spent

    def spend(self, engineer_id: str, team_id: str, sprint_no: int, hours: Decimal) -> None:
        self._spent[(engineer_id, team_id, sprint_no)] += hours

    def free(self, assignments: list[Assignment]) -> None:
        for row in assignments:
            self._spent[(row.engineer_id, row.home_team_id, row.sprint_no)] -= row.hours

    # ---- SP --------------------------------------------------------------
    def take_sp(self, team_id: str, sprint_no: int, sp: Decimal) -> None:
        self.used_sp[(team_id, sprint_no)] += sp

    def release_sp(self, team_id: str, sprint_no: int, sp: Decimal) -> None:
        self.used_sp[(team_id, sprint_no)] -= sp


def _candidate_engineers(
    task_team: str, role_id: int, sprint_no: int, funds: _Funds, by_role: dict[int, list[str]],
    preferred: frozenset[str] = frozenset(),
) -> list[str]:
    """Кого можно поставить на роль: свои орбиты первыми, потом заёмщики.

    Порядок внутри групп — по убыванию свободных часов орбиты (у заёмщиков —
    по общему остатку), затем по `engineer_id`: без этого один и тот же вход
    давал бы разные планы. «Своя орбита» значит «у инженера есть бюджет этой
    команды в этом спринте»: бюджет орбиты заранее не резервируется, но и в заём
    не отдаётся раньше, чем свои задачи получат шанс (ADR-015).
    """
    own: list[tuple[Decimal, Decimal, str]] = []
    loans: list[tuple[Decimal, str]] = []
    for engineer_id in by_role.get(role_id, ()):
        engineer = funds.engineers[engineer_id]
        left = funds.total_left(engineer_id, sprint_no)
        if left <= 0:
            continue
        if task_team in engineer.orbits:
            own.append((funds.orbit_left(engineer_id, task_team, sprint_no), left, engineer_id))
        else:
            loans.append((left, engineer_id))
    own.sort(key=lambda item: (item[2] not in preferred, -item[0], -item[1], item[2]))
    loans.sort(key=lambda item: (item[1] not in preferred, -item[0], item[1]))
    return [item[2] for item in own] + [item[1] for item in loans]


def _spend_from(
    engineer: EngineerInput, task_team: str, sprint_no: int, need: Decimal, funds: _Funds
) -> list[tuple[Decimal, str]]:
    """Списать часы с доступных орбит человека, своё ядро — первым."""
    order = [task_team] if task_team in engineer.orbits else []  # своё ядро — первым
    order.extend(
        sorted(
            (team_id for team_id in engineer.orbits if team_id != task_team),
            key=lambda team_id: (
                -funds.orbit_left(engineer.engineer_id, team_id, sprint_no),
                team_id,
            ),
        )
    )

    taken_from: list[tuple[Decimal, str]] = []
    for team_id in order:
        if need <= 0:
            break
        left = min(
            funds.orbit_left(engineer.engineer_id, team_id, sprint_no),
            funds.total_left(engineer.engineer_id, sprint_no),
        )
        if left <= 0:
            continue
        take = min(left, need)
        if take <= 0:
            continue
        funds.spend(engineer.engineer_id, team_id, sprint_no, take)
        taken_from.append((take, team_id))
        need -= take
    return taken_from


def _allocate_task(
    task: TaskInput,
    start_sprint: int,
    funds: _Funds,
    by_role: dict[int, list[str]],
    sprint_count: int,
    coverage: dict[tuple[str, int], Decimal],
    sp_free: Callable[[int], Decimal] | None = None,
    log: list[dict[str, Any]] | None = None,
) -> tuple[list[Assignment], int, int] | None:
    """Разложить остаток задачи по спринтам и людям, начиная со `start_sprint`.

    `log` (диагностика, DA-16) получает по записи на спринт: свободные SP команды, бюджет
    работы по SP, размещённую работу и признак «работу ограничила ёмкость SP»; в конце —
    запись `summary` с недоразмещённым остатком по ролям. Числа в объяснении отказа берутся
    отсюда, а не пересчитываются отдельно.

    `sp_free(sprint_no)` — свободная ёмкость команды в SP в этом спринте. Если она
    передана и у задачи есть SP, часы и SP идут ВМЕСТЕ (ADR-029): за спринт
    выполняется не больше доли работы `свободные SP / SP задачи`, поэтому доля SP
    в спринте — ровно доля выполненных в нём часов, а спринт без часов не списывает
    SP и наоборот. Без `sp_free` (диагностика отказа) ограничение — только часы.

    Механика распределения часов (ADR-015, ревью M2, пункт 5):

    * роли внутри одного спринта закрываются ПАРАЛЛЕЛЬНО и независимо: цикл идёт
      по ролям, каждая берёт столько часов, сколько дают свободные исполнители;
    * одну роль в одном спринте могут закрывать НЕСКОЛЬКО человек — на каждого
      пишется своя строка `plan_assignments`;
    * часы роли, не поместившиеся в спринт, переезжают в следующий: задача
      растягивается (`end_sprint > start_sprint`);
    * окно задачи — `[min, max]` ФАКТИЧЕСКИ использованных спринтов; разрывы
      внутри окна не запрещены (задача ждёт конкретную роль), но подсвечиваются
      инвариантом `WINDOW_HAS_GAP` как warning;
    * если до конца квартала часы не нашлись, ВСЕ сделанные списания
      откатываются (`funds.free`): задача уйдёт в перенос, её часы вернутся
      в фонд — пробные назначения не «залипают»;
    * `efficiency` умножает потребность: чтобы закрыть смету `remaining_hours`,
      исполнителю нужно `remaining_hours × efficiency` СВОИХ часов (сейчас
      в данных везде `1.00`, поэтому формула вырождается в тождество).

    Возвращает (назначения, ПЕРВЫЙ использованный спринт, последний). Первый
    использованный, а не запрошенный: иначе задача «стартовала» бы в спринте,
    где по ней не сделано ни одного часа, и SP уехали бы не туда.
    """
    needed = task.needed
    if not needed:
        return None

    total_work = sum(needed.values(), Decimal("0"))
    sp_total = task.sp_to_plan
    capped = sp_free is not None and sp_total > 0
    assignments: list[Assignment] = []
    remaining = dict(needed)
    for sprint_no in range(start_sprint, sprint_count + 1):
        budget: Decimal | None = None
        if capped:
            free_sp = sp_free(sprint_no)  # type: ignore[misc]
            if free_sp <= 0:
                if log is not None:
                    log.append({"sprint": sprint_no, "free_sp": Decimal("0"), "no_free_sp": True})
                continue  # команде нечем оплатить работу в этом спринте
            budget = total_work * free_sp / sp_total
        sprint_work = Decimal("0")
        for role_id in sorted(remaining):
            need = remaining[role_id]
            if need <= 0:
                continue
            for engineer_id in _candidate_engineers(
                task.team_id, role_id, sprint_no, funds, by_role,
                funds.preferred.get((task.task_id, role_id), frozenset()),
            ):
                want = need
                if budget is not None:
                    room = budget - sprint_work
                    if room < MIN_CHUNK_HH and room < need:
                        break  # остаток бюджета спринта меньше значимого куска работы
                    want = min(need, room)
                # efficiency: смету закрывают ЧАСЫ ИСПОЛНИТЕЛЯ, а не сметы.
                efficiency = coverage.get((engineer_id, role_id), Decimal("1"))
                taken_from = _spend_from(
                    funds.engineers[engineer_id], task.team_id, sprint_no, want * efficiency, funds
                )
                if not taken_from:
                    continue
                for taken, home in taken_from:
                    assignments.append(
                        Assignment(task.task_id, sprint_no, engineer_id, role_id, taken, home,
                                   task.team_id, taken / efficiency)
                    )
                    need -= taken / efficiency
                    sprint_work += taken / efficiency
                remaining[role_id] = need
                if need <= 0:
                    break
        if log is not None:
            log.append({
                "sprint": sprint_no,
                "free_sp": sp_free(sprint_no) if capped else None,  # type: ignore[misc]
                "budget_work": budget,
                "work": sprint_work,
                "sp_limited": budget is not None and budget - sprint_work < MIN_CHUNK_HH
                and any(hours > 0 for hours in remaining.values()),
            })
        if all(hours <= 0 for hours in remaining.values()):
            used = [row.sprint_no for row in assignments]
            return assignments, min(used), max(used)

    if log is not None:
        log.append({"summary": True, "unplaced": {role: hours for role, hours in remaining.items() if hours > 0},
                    "total_work": total_work, "placed_work": sum(
                        (row.work_hours or row.hours for row in assignments), Decimal("0"))})
    funds.free(assignments)
    return None


def _sp_shares(
    task: TaskInput, rows: list[Assignment], sp_free: Callable[[int], Decimal]
) -> dict[int, Decimal] | None:
    """Доли SP по спринтам пропорционально выполненной в них работе (ADR-029).

    Работа спринта — сумма `work_hours` его назначений. Доли округляются вниз до
    сотой, недостающие сотые раздаются по наибольшим остаткам, но только туда, где
    у команды ещё есть место; иначе `None` (кандидат старта отвергается, и задача
    пробуется позже). Сумма долей ровно равна SP к планированию: так требует
    инвариант `SP_SHARES_MISMATCH`.
    """
    sp_total = task.sp_to_plan
    if sp_total <= 0:
        return {}
    work: dict[int, Decimal] = defaultdict(Decimal)
    for row in rows:
        work[row.sprint_no] += row.work_hours if row.work_hours is not None else row.hours
    total = sum(work.values(), Decimal("0"))
    if total <= 0:
        return None
    cent = Decimal("0.01")
    raw = {sprint_no: sp_total * hours / total for sprint_no, hours in work.items()}
    shares = {sprint_no: value.quantize(cent, rounding=ROUND_DOWN) for sprint_no, value in raw.items()}
    steps = int((sp_total - sum(shares.values(), Decimal("0"))) / cent)
    by_leftover = sorted(raw, key=lambda sprint_no: (-(raw[sprint_no] - shares[sprint_no]), sprint_no))
    while steps > 0:
        progressed = False
        for sprint_no in by_leftover:
            if steps == 0:
                break
            if shares[sprint_no] + cent <= sp_free(sprint_no):
                shares[sprint_no] += cent
                steps -= 1
                progressed = True
        if not progressed:
            return None
    return {sprint_no: value for sprint_no, value in sorted(shares.items()) if value > 0}
