"""XLSX reader using openpyxl."""

from __future__ import annotations

from typing import Any


def read_xlsx(input_path: str, sheet_names: list[str] | None = None) -> dict[str, Any]:
    import openpyxl

    wb = openpyxl.load_workbook(input_path, data_only=True)

    target_sheets = sheet_names if sheet_names else wb.sheetnames
    sheets = []
    for name in target_sheets:
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([str(cell) if cell is not None else "" for cell in row])
        sheets.append({"name": name, "rows": rows})

    return {"ok": True, "path": input_path, "sheets": sheets}
