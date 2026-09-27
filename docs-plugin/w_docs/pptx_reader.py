"""PPTX reader using python-pptx."""

from __future__ import annotations

from typing import Any


def read_pptx(input_path: str) -> dict[str, Any]:
    from pptx import Presentation
    from pptx.util import Pt

    prs = Presentation(input_path)
    slides: list[dict[str, Any]] = []

    for i, slide in enumerate(prs.slides):
        texts: list[str] = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                line = "".join(run.text for run in para.runs).strip()
                if line:
                    texts.append(line)
        title_shape = slide.shapes.title
        title = title_shape.text.strip() if title_shape and title_shape.has_text_frame else ""
        slides.append({"slide": i + 1, "title": title, "text": texts})

    return {"ok": True, "path": input_path, "slide_count": len(slides), "slides": slides}
