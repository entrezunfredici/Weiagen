"""PPTX generator using python-pptx.

Payload schema:
  output_path : str           — chemin absolu vers le fichier .pptx à créer
  slides      : list[Slide]   — définitions des diapositives dans l'ordre

Slide layouts:
  { "layout": "title",      "title": "...", "subtitle": "..." }
  { "layout": "content",    "title": "...", "content": ["bullet1", "bullet2"] }
  { "layout": "two_column", "title": "...", "left": ["..."], "right": ["..."] }
  { "layout": "blank",      "body": "..." }

Layouts mappés sur les layouts standard du thème Office :
  0 → Title Slide      (titre centré + sous-titre)
  1 → Title and Content
  3 → Two Content      (deux colonnes)
  5 → Title Only
  6 → Blank
"""

from __future__ import annotations

import os

from pptx import Presentation
from pptx.util import Inches, Pt


_LAYOUT_TITLE = 0
_LAYOUT_CONTENT = 1
_LAYOUT_TWO_CONTENT = 3
_LAYOUT_TITLE_ONLY = 5
_LAYOUT_BLANK = 6


def _safe_layout(prs: Presentation, idx: int):
    """Retourne le layout à l'index demandé, ou le dernier disponible."""
    layouts = prs.slide_layouts
    return layouts[idx] if idx < len(layouts) else layouts[-1]


def _fill_text_frame(tf, items: list[str]) -> None:
    tf.clear()
    for i, item in enumerate(items):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.text = str(item)
        para.level = 0


def create_pptx(output_path: str, slides: list[dict]) -> dict:
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    prs = Presentation()

    for slide_def in slides:
        layout: str = slide_def.get("layout", "content")
        slide_title: str = slide_def.get("title", "")

        if layout == "title":
            sl = _safe_layout(prs, _LAYOUT_TITLE)
            slide = prs.slides.add_slide(sl)
            if slide.shapes.title:
                slide.shapes.title.text = slide_title
            # Sous-titre : placeholder idx=1
            for ph in slide.placeholders:
                if ph.placeholder_format.idx == 1:
                    ph.text = slide_def.get("subtitle", "")
                    break

        elif layout == "two_column":
            sl = _safe_layout(prs, _LAYOUT_TWO_CONTENT)
            slide = prs.slides.add_slide(sl)
            if slide.shapes.title:
                slide.shapes.title.text = slide_title
            # Récupérer les deux zones de contenu (idx 1 et 2)
            content_phs = sorted(
                [ph for ph in slide.placeholders if ph.placeholder_format.idx in (1, 2)],
                key=lambda ph: ph.placeholder_format.idx,
            )
            if len(content_phs) >= 2:
                _fill_text_frame(content_phs[0].text_frame, slide_def.get("left", []))
                _fill_text_frame(content_phs[1].text_frame, slide_def.get("right", []))
            elif len(content_phs) == 1:
                _fill_text_frame(
                    content_phs[0].text_frame,
                    slide_def.get("left", []) + slide_def.get("right", []),
                )

        elif layout == "blank":
            sl = _safe_layout(prs, _LAYOUT_BLANK)
            slide = prs.slides.add_slide(sl)
            body_text: str = slide_def.get("body", "")
            if body_text:
                txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.8), Inches(8.4), Inches(5.5))
                tf = txBox.text_frame
                tf.word_wrap = True
                tf.text = body_text

        else:  # "content" (défaut)
            sl = _safe_layout(prs, _LAYOUT_CONTENT)
            slide = prs.slides.add_slide(sl)
            if slide.shapes.title:
                slide.shapes.title.text = slide_title
            for ph in slide.placeholders:
                if ph.placeholder_format.idx == 1:
                    _fill_text_frame(ph.text_frame, slide_def.get("content", []))
                    break

    prs.save(output_path)
    return {"ok": True, "path": output_path, "slides_count": len(slides)}
