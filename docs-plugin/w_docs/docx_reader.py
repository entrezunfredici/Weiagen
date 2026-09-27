"""DOCX reader using python-docx."""

from __future__ import annotations

from typing import Any


def read_docx(input_path: str) -> dict[str, Any]:
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(input_path)
    blocks: list[dict[str, Any]] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        if style.startswith("Heading"):
            try:
                level = int(style.split()[-1])
            except (ValueError, IndexError):
                level = 1
            blocks.append({"type": "heading", "level": level, "text": text})
        elif style in ("List Bullet", "List Bullet 2", "List Bullet 3"):
            blocks.append({"type": "bullet", "text": text})
        elif style in ("List Number", "List Number 2", "List Number 3"):
            blocks.append({"type": "numbered", "text": text})
        else:
            blocks.append({"type": "paragraph", "text": text})

    for table in doc.tables:
        headers = [cell.text.strip() for cell in table.rows[0].cells] if table.rows else []
        rows = [
            [cell.text.strip() for cell in row.cells]
            for row in table.rows[1:]
        ]
        blocks.append({"type": "table", "headers": headers, "rows": rows})

    title = doc.core_properties.title or ""
    return {"ok": True, "path": input_path, "title": title, "content": blocks}
