"""Итог часов обязан совпадать с входной ролевой сметой планировщика."""
from pathlib import Path

import openpyxl
import pytest

from etl import load


def test_empty_role_matrix_with_nonzero_task_blocks_seed(tmp_path):
    source = next(Path(__file__).resolve().parents[1].glob("*.xlsx"))
    workbook = openpyxl.load_workbook(source)
    sheet = load.Sheet(workbook.worksheets[0])
    title = sheet.find_block(load.C.BLOCK_MARKERS["estimates"])
    header = sheet.header_row(title)
    columns = sheet.columns(header)
    task_id = next(key for key in columns if key != "Роль")
    column = columns[task_id]
    for row in sheet.data_rows(header, stop_prefixes=("Итого",)):
        sheet.ws.cell(row, column).value = 0
    changed = tmp_path / "no_role_estimate.xlsx"
    workbook.save(changed)

    with pytest.raises(load.DataQualityError) as exc:
        load.build_seed_sql(changed)
    assert any(task_id in problem and "MISSING_ROLE_ESTIMATE" in problem
               for problem in exc.value.problems)
