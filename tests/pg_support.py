"""Общие помощники PostgreSQL-тестов: сборка базовой схемы во временной схеме.

Базовые файлы `db/0*.sql` рассчитаны на порядок «схема → seed → 03 → 04 → 05»:
`03_substitutions.sql` ссылается на справочник `ref_result_options`, который
заполняет seed. Тесты работают без seed, поэтому нужные строки справочника
добавляются здесь перед `03_substitutions.sql`.
"""
from __future__ import annotations

from pathlib import Path

# Коды, на которые ссылается plan_decision_goal_map (db/03_substitutions.sql).
REFERENCE_ROWS_SQL = """
INSERT INTO ref_result_options (code, ord, label) VALUES
  ('NOT_IN_PI', 7, 'не будет взято в квартал'),
  ('CANCELLED', 8, 'Отменено заказчиком')
ON CONFLICT (code) DO NOTHING;
"""


def load_base_file(cursor, path: Path) -> None:
    """Выполнить базовый SQL-файл; перед 03_substitutions — строки справочника."""
    if path.name == "03_substitutions.sql":
        cursor.execute(REFERENCE_ROWS_SQL)
    cursor.execute(path.read_text())
