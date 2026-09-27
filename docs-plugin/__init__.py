"""``docs`` Hermes plugin — create and read office documents (xlsx, docx, pptx).

Split out of ``odoo-plugin`` on 2026-09-24 (see ``.agents/DECISIONS.md``):
document generation never depended on Odoo, and bundling it there meant
enabling an Odoo connector just to produce a spreadsheet. ``w_docs/`` is
moved as-is (byte-for-byte, still the OpenClaw-era code); only the
integration layer (``tools.py``) and the output-path policy
(``docs_paths.py``) are new.

Generated files go to Hermes's document cache by default and every result
carries a ``MEDIA:<path>`` tag, so the agent can attach the file to its
reply (Slack upload) — see ``docs_paths.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make w_docs / docs_paths importable as top-level modules — same sys.path
# trick as the other plugins. `w_docs` no longer exists in odoo-plugin, so
# the name is unique in the Hermes process; `docs_paths` is prefixed for
# the same reason audit-plugin prefixes its modules (sys.modules is global).
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

# tools.py MUST be a relative import — Hermes core has its own top-level
# `tools` package (see .agents/CONVENTIONS.md).
from .tools import DOCS_TOOLS  # noqa: E402


def register(ctx) -> None:
    """Register the six ``docs_*`` tools (toolset ``docs``)."""
    for name, toolset, schema, handler, emoji in DOCS_TOOLS:
        ctx.register_tool(name=name, toolset=toolset, schema=schema, handler=handler, emoji=emoji)
