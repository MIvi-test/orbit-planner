"""Bounded intent routing; data operations remain server-side."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Intent:
    name: str
    clarification: str | None = None


def classify(question: str, *, has_snapshot: bool,
             focus: tuple[str, str] | None, metric_codes: set[str],
             has_scenario: bool, has_previous_run: bool = False) -> Intent:
    text = question.casefold()
    if re.search(r"что изменилось|изменени[яй]|сравн.*прогон|новый прогон", text):
        return (Intent("changes") if has_snapshot and has_previous_run else
                Intent("changes", "Выберите второй прогон через обновление контекста чата.")
                if has_snapshot else Intent("changes", "Сначала выберите PI и прогон."))
    if re.search(r"сравн.*(?:мер|найм|перевод|обуч|пакет)|найм.*перевод|эффект.*(?:найм|перевод|обуч)", text):
        if not has_snapshot:
            return Intent("compare_measures", "Сначала выберите PI и прогон для расчёта мер.")
        if not has_scenario:
            return Intent("compare_measures", "Задайте меры с ролями, ставками, спринтами и навыками; "
                          "сравнение рассчитывается через сценарный API этого чата.")
        return Intent("compare_measures")
    if re.search(r"как (?:работает|устроен|начать|система)|что такое|чем отличается|правил[оа]|зачем", text):
        if not re.search(r"мо[яию]|мои|именно|у нас|эт[ауи] задач|эт[ауи] команд", text):
            return Intent("system_help")
    mentioned = [code for code in metric_codes
                 if re.search(r"(?<![\w])" + re.escape(code.casefold()) + r"(?![\w])", text)]
    if len(mentioned) == 1:
        return (Intent("metric_explanation") if has_snapshot else
                Intent("metric_explanation", "Для значения KPI выберите PI и прогон; правило могу объяснить без них."))
    if focus:
        return Intent("task_explanation" if focus[0] == "task" else "team_analysis")
    if re.search(r"мо[яию]|мои|у нас|команд|задач|план|дефицит|прогон", text):
        return (Intent("overview") if has_snapshot else
                Intent("overview", "Для разбора вашего плана выберите PI и прогон."))
    return Intent("system_help")


def operation(intent: Intent) -> str:
    common = ("Ответь на вопрос по переданным данным и истории. Не выдумывай числа или проверенный "
              "эффект мер. В summary/explanation не пиши чисел: для численного вывода верни "
              "fact_refs как массив {evidence_id, field}, где field — точный путь к числу "
              "в переданном JSON факта; сервер подставит значение. "
              "При неоднозначности верни needs_clarification. "
              "Верни JSON с status, summary, explanation, clarification, fact_refs.")
    details = {
        "system_help": "Объясни действующие правила и порядок работы по документации; прогон не обязателен.",
        "overview": "Опиши основные ограничения и масштаб плана по полному обзору снимка.",
        "team_analysis": "Объясни положение выбранной команды и последствия для неё.",
        "task_explanation": "Разбери решение и цепочку причин выбранной задачи.",
        "metric_explanation": "Отдели факт от прогноза, укажи период и знаменатель из снимка и правила.",
        "compare_measures": "Сравни только сохранённые сценарные результаты; не складывай эффекты мер.",
        "changes": "Отдели наблюдаемую разницу прогонов от предполагаемой причины.",
    }
    return details[intent.name] + " " + common
