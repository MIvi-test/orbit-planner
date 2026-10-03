"""Справочник ролей из сметы и профилей, конфликт парттаймера (DA-25)."""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from etl import config as C
from etl import load

SOURCE = Path(__file__).resolve().parents[1] / C.SOURCE_XLSX


def _engineer_cells(sheet):
    """Строки блока профилей: (номер строки, колонка id, колонка роли)."""
    for row in sheet.iter_rows():
        values = {str(cell.value).strip(): cell.column for cell in row if cell.value is not None}
        if "engineer_id" in values and "role" in values:
            header = row[0].row
            id_col, role_col = values["engineer_id"], values["role"]
            break
    else:
        pytest.skip("блок профилей не найден")
    rows = []
    for r in range(header + 1, sheet.max_row + 1):
        value = sheet.cell(r, id_col).value
        if value:
            rows.append((r, str(value).strip(), id_col, role_col))
    return rows


def _workbook_with(tmp_path: Path, change) -> Path:
    # data_only: пересохранение формул openpyxl теряет их вычисленные значения, а ETL (DA-23)
    # правильно отказывается читать формулу без сохранённого результата.
    workbook = openpyxl.load_workbook(SOURCE, data_only=True)
    sheet = workbook.worksheets[0]
    change(sheet, _engineer_cells(sheet))
    path = tmp_path / "changed.xlsx"
    workbook.save(path)
    return path


def test_role_missing_from_the_estimate_matrix_keeps_the_engineer(tmp_path) -> None:
    def change(sheet, rows):
        row, _eid, _id_col, role_col = rows[0]
        sheet.cell(row, role_col).value = "Скрам-мастер"

    path = _workbook_with(tmp_path, change)
    sql, counts, quality = load.build_seed_sql(path)
    assert quality["error"] == 0
    assert counts["engineers"] == 30            # сотрудник не потерян
    assert counts["roles"] == 22                # 21 сметная + 1 из профиля
    assert "Скрам-мастер" in sql and "ROLE_WITHOUT_ESTIMATE" in sql


def test_estimate_role_ids_do_not_shift_when_a_profile_role_is_added(tmp_path) -> None:
    def role_rows(sql: str) -> list[str]:
        start = sql.index("INSERT INTO roles")
        block = sql[start:sql.index(";\n", start)]
        return [line.strip().rstrip(",;") for line in block.splitlines()[1:]]

    baseline = role_rows(load.build_seed_sql(SOURCE)[0])

    def change(sheet, rows):
        row, _eid, _id_col, role_col = rows[0]
        sheet.cell(row, role_col).value = "Скрам-мастер"

    changed = role_rows(load.build_seed_sql(_workbook_with(tmp_path, change))[0])
    assert changed[: len(baseline)] == baseline          # сметные роли — те же id в том же порядке
    assert len(changed) == len(baseline) + 1 and "Скрам-мастер" in changed[-1]


def test_empty_role_is_a_blocking_error(tmp_path) -> None:
    def change(sheet, rows):
        row, _eid, _id_col, role_col = rows[0]
        sheet.cell(row, role_col).value = None

    with pytest.raises(load.DataQualityError) as exc:
        load.build_seed_sql(_workbook_with(tmp_path, change))
    assert any("не указана роль" in problem for problem in exc.value.problems)


def test_parttime_conflicting_attributes_block_the_load(tmp_path) -> None:
    def change(sheet, rows):
        counts: dict[str, list[tuple[int, int]]] = {}
        for row, eid, _id_col, role_col in rows:
            counts.setdefault(eid, []).append((row, role_col))
        row, role_col = next(items[1] for items in counts.values() if len(items) > 1)
        sheet.cell(row, role_col).value = "Скрам-мастер"

    with pytest.raises(load.DataQualityError) as exc:
        load.build_seed_sql(_workbook_with(tmp_path, change))
    assert any("различаются роль или грейд" in problem for problem in exc.value.problems)
