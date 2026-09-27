"""DOCX generator using python-docx.

Payload schema:
  output_path : str           — chemin absolu vers le fichier .docx à créer
  title       : str           — titre principal du document (optionnel)
  content     : list[Block]   — blocs de contenu dans l'ordre

Block types:
  { "type": "heading",       "level": 1–4,    "text": "..." }
  { "type": "paragraph",     "text": "..." }
  { "type": "bullet_list",   "items": ["..."] }
  { "type": "numbered_list", "items": ["..."] }
  { "type": "table",         "headers": ["..."], "rows": [["..."]] }
  { "type": "page_break" }
"""

from __future__ import annotations

import os

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.oxml import OxmlElement


def create_docx(output_path: str, content: list[dict], title: str | None = None) -> dict:
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = Document()

    if title:
        doc.add_heading(title, level=0)

    for block in content:
        block_type: str = block.get("type", "paragraph")

        if block_type == "heading":
            level = max(1, min(int(block.get("level", 1)), 4))
            doc.add_heading(block.get("text", ""), level=level)

        elif block_type == "paragraph":
            doc.add_paragraph(block.get("text", ""))

        elif block_type == "bullet_list":
            for item in block.get("items", []):
                doc.add_paragraph(str(item), style="List Bullet")

        elif block_type == "numbered_list":
            for item in block.get("items", []):
                doc.add_paragraph(str(item), style="List Number")

        elif block_type == "table":
            headers: list[str] = block.get("headers", [])
            rows: list[list] = block.get("rows", [])
            col_count = max(
                len(headers),
                max((len(r) for r in rows), default=0),
                1,
            )
            table = doc.add_table(rows=0, cols=col_count)
            table.style = "Table Grid"

            if headers:
                hdr_row = table.add_row()
                for i, h in enumerate(headers[:col_count]):
                    cell = hdr_row.cells[i]
                    cell.text = str(h)
                    run = cell.paragraphs[0].runs
                    if run:
                        run[0].font.bold = True

            for row_data in rows:
                tr = table.add_row()
                for i, val in enumerate(row_data[:col_count]):
                    tr.cells[i].text = str(val) if val is not None else ""

        elif block_type == "page_break":
            doc.add_page_break()

    doc.save(output_path)
    return {"ok": True, "path": output_path}
