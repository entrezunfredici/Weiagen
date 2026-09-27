"""Plain-text → HTML normalization for Odoo ``html``-type fields.

Odoo html fields (``project.task.description``, ``mail.message.body``, ...)
render raw markup: a literal ``\\n`` in the payload shows up in the UI as the
two characters ``\\`` and ``n`` instead of a line break, because there is no
implicit text-to-HTML conversion on the Odoo side. AI-generated text mixes
plain ``\\n`` line breaks with occasional markdown/HTML — this module converts
the plain-text case to real ``<p>``/``<br/>`` markup while leaving anything
that already looks like HTML untouched, so the AI can still hand-write
``<b>``, ``<ul>``, ``<h2>``, etc. to style content.
"""

from __future__ import annotations

import html
import re

# Matches an opening tag for any block/inline element an AI is likely to write
# on purpose. Presence of one of these means "treat as HTML, don't touch it".
_HTML_TAG_RE = re.compile(
    r"<(p|br|div|ul|ol|li|h[1-6]|b|strong|i|em|u|a|table|thead|tbody|tr|td|th|"
    r"span|blockquote|code|pre|img|hr)\b",
    re.IGNORECASE,
)


def looks_like_html(value: str) -> bool:
    """True if *value* already contains recognizable HTML markup."""
    return bool(_HTML_TAG_RE.search(value))


def text_to_html(value: str) -> str:
    """Convert plain text into HTML paragraphs, preserving line breaks.

    Blank-line-separated blocks become ``<p>`` paragraphs; single ``\\n``
    within a block become ``<br/>``. Text is HTML-escaped since it is being
    treated as plain text, not markup. Values that already contain HTML tags
    are returned unchanged — the AI is expected to write real markup directly
    for anything beyond a line break.
    """
    if not value or looks_like_html(value):
        return value

    blocks = re.split(r"\n\s*\n", value.strip())
    paragraphs = []
    for block in blocks:
        lines = [html.escape(line) for line in block.split("\n")]
        paragraphs.append(f"<p>{'<br/>'.join(lines)}</p>")
    return "".join(paragraphs)


def normalize_html_values(
    values: dict, html_field_names: set
) -> dict:
    """Return a copy of *values* with every field in *html_field_names* normalized.

    Non-string values and fields not in *html_field_names* pass through
    untouched.
    """
    if not html_field_names:
        return values

    converted = dict(values)
    for name in html_field_names:
        value = converted.get(name)
        if isinstance(value, str):
            converted[name] = text_to_html(value)
    return converted
