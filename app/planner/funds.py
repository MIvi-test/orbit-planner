"""Фонд часов и SP: единственное место, где ресурсы списываются и возвращаются."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_DOWN

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
        self._budget: dict[tuple[str, str], Decimal] = {
            (engineer.engineer_id, team_id): rate * self.fte
            for engineer in inputs.engineers
            for team_id, rate in engineer.orbits.items()
        }
        self._spent: dict[tuple[str, str, int], Decimal] = defaultdict(Decimal)
        self.used_sp: dict[tuple[str, int], Decimal] = defaultdict(Decimal)

    def sprint_factor(self, sprint_no: int) -> Decimal:
        """Доля фонда полного спринта, которую даёт спринт `sprint_no`."""
        return self.factors.get(sprint_no, Decimal("1"))

    # ---- часы ------------------------------------------------------------
    def orbit_left(self, engineer_id: str, team_id: str, sprint_no: int) -> Decimal:
        budget = (
            self._budget.get((engineer_id, team_id), Decimal("0"))
            * self.sprint_factor(sprint_no)
        )
        return budget - self._spent[(engineer_id, team_id, sprint_no)]

    def total_left(self, engineer_id: str, sprint_no: int) -> Decimal:
        engineer = self.engineers[engineer_id]
        spent = sum(
            (self._spent[(engineer_id, team_id, sprint_no)] for team_id in engineer.orbits),
            Decimal("0"),
        )
        return (
            engineer.total_capacity_rate * self.fte * self.sprint_factor(sprint_no) - spent
        )

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
    task_team: str, role_id: int, sprint_no: int, funds: _Funds, by_role: dict[int, list[str]]
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
    own.sort(key=lambda item: (-item[0], -item[1], item[2]))
    loans.sort(key=lambda item: (-item[0], item[1]))
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
) -> tuple[list[Assignment], int, int] | None:
    """Разложить остаток задачи по спринтам и людям, начиная со `start_sprint`.

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

    assignments: list[Assignment] = []
    remaining = dict(needed)
    for sprint_no in range(start_sprint, sprint_count + 1):
        for role_id in sorted(remaining):
            need = remaining[role_id]
            if need <= 0:
                continue
            for engineer_id in _candidate_engineers(task.team_id, role_id, sprint_no, funds, by_role):
                # efficiency: смету закрывают ЧАСЫ ИСПОЛНИТЕЛЯ, а не сметы.
                efficiency = coverage.get((engineer_id, role_id), Decimal("1"))
                taken_from = _spend_from(
                    funds.engineers[engineer_id], task.team_id, sprint_no, need * efficiency, funds
                )
                if not taken_from:
                    continue
                for taken, home in taken_from:
                    assignments.append(
                        Assignment(task.task_id, sprint_no, engineer_id, role_id, taken, home,
                                   task.team_id, taken / efficiency)
                    )
                    need -= taken / efficiency
                remaining[role_id] = need
                if need <= 0:
                    break
        if all(hours <= 0 for hours in remaining.values()):
            used = [row.sprint_no for row in assignments]
            return assignments, min(used), max(used)

    funds.free(assignments)
    return None


def _sp_flow(
    task: TaskInput, start_sprint: int, funds: _Funds, capacity: Decimal, sprint_count: int
) -> dict[int, Decimal] | None:
    """Story Points задачи как поток по спринтам (ADR-020).

    Команда за спринт закрывает не больше `available_sp_per_sprint × factor`.
    Задача, начатая в спринте `start_sprint`, списывает SP с ёмкости команды
    начиная с него: сколько свободно в этом спринте, остаток — в следующих.
    Так задача с SP больше ёмкости одного спринта растягивается, а не
    переносится навсегда — ровно как требует пример онбординга с DB-202
    («алгоритм должен растянуть эту задачу минимум на 2 спринта»).

    В спринте старта у команды должна быть хоть какая-то свободная ёмкость:
    задача не может «начаться» там, где команде взять её не из чего.
    Возвращает {спринт: SP} или None, если SP не укладываются в квартал.
    """
    need = task.sp_to_plan
    if need <= 0:
        return {}

    def free(sprint_no: int) -> Decimal:
        left = capacity * funds.sprint_factor(sprint_no) - funds.used_sp[(task.team_id, sprint_no)]
        return left.quantize(Decimal("0.01"), rounding=ROUND_DOWN) if left > 0 else Decimal("0")

    if free(start_sprint) <= 0:
        return None
    shares: dict[int, Decimal] = {}
    for sprint_no in range(start_sprint, sprint_count + 1):
        available = free(sprint_no)
        if available <= 0:
            continue
        take = min(available, need)
        shares[sprint_no] = take
        need -= take
        if need <= 0:
            return shares
    return None
