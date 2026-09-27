"""XLSX generator using openpyxl.

Payload schema:
  output_path : str           — chemin absolu vers le fichier .xlsx à créer
  sheets      : list[Sheet]   — liste de feuilles de calcul

Sheet:
  name              : str                     — nom de la feuille (défaut "Sheet")
  headers           : list[str]               — ligne d'en-tête (optionnel)
  rows              : list[list[Any]]         — données
  freeze_top_row    : bool                    — geler la 1ʳᵉ ligne (défaut false)
  auto_filter       : bool                    — activer l'auto-filtre sur les en-têtes (défaut false)
  column_widths     : dict[str, float]        — largeurs fixes par lettre de colonne, ex. {"A": 20}
"""

from __future__ import annotations

import os
from typing import Any

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


_HEADER_FILL = PatternFill("solid", fgColor="D9E1F2")
_HEADER_FONT = Font(bold=True)


def create_xlsx(output_path: str, sheets: list[dict]) -> dict:
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    wb = openpyxl.Workbook()
    # Retirer la feuille par défaut
    wb.remove(wb.active)  # type: ignore[arg-type]

    if not sheets:
        sheets = [{"name": "Sheet1"}]

    for sheet_def in sheets:
        name: str = sheet_def.get("name", "Sheet")
        headers: list[str] = sheet_def.get("headers", [])
        rows: list[list[Any]] = sheet_def.get("rows", [])
        freeze_top_row: bool = sheet_def.get("freeze_top_row", False)
        auto_filter: bool = sheet_def.get("auto_filter", False)
        column_widths: dict[str, float] = sheet_def.get("column_widths", {})

        ws = wb.create_sheet(title=name[:31])  # Excel limite les noms à 31 caractères

        if headers:
            ws.append(headers)
            for cell in ws[1]:
                cell.font = _HEADER_FONT
                cell.fill = _HEADER_FILL

            if freeze_top_row:
                ws.freeze_panes = "A2"

            if auto_filter and headers:
                ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

        for row in rows:
            ws.append([v if v is not None else "" for v in row])

        # Largeur des colonnes : fixe si spécifiée, sinon auto
        for col_idx, col_cells in enumerate(ws.columns, start=1):
            letter = get_column_letter(col_idx)
            if letter in column_widths:
                ws.column_dimensions[letter].width = column_widths[letter]
            else:
                max_len = max(
                    (len(str(c.value)) for c in col_cells if c.value is not None),
                    default=6,
                )
                ws.column_dimensions[letter].width = min(max_len + 2, 50)

    wb.save(output_path)
    return {"ok": True, "path": output_path, "sheets": [s.get("name", "Sheet") for s in sheets]}
