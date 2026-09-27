"""Live catalog of Hermes's own registered tools (built-in + plugin + MCP),
used only to populate the dashboard's tool picker for `hermes_tool` rights
— purely a UX convenience, never consulted by engine.py's authorization
decisions (same status as directory.py's Slack member cache or
platforms.py's connected-platform list).

Reads Hermes core's real ``tools.registry.registry`` singleton directly.
Confirmed safe to import in both the real gateway and dashboard processes
(``hermes_cli/web_server.py`` imports the real ``tools`` package well
before ever mounting a plugin dashboard — see .agents/DECISIONS.md, the
"false-alarm 'tools' package collision" entry, which investigated exactly
this). In this plugin's own test environment, ``tools.registry`` is
stubbed with only ``tool_result`` (see tests/conftest.py) — no ``registry``
singleton — so the import here fails there by design, and
``list_hermes_tools()`` degrades to an empty list rather than raising.
Wrapped in try/except throughout: this module must never crash the
dashboard just because Hermes's real registry shape changes upstream.
"""

from __future__ import annotations

from typing import Any


def list_hermes_tools() -> list[dict[str, Any]]:
    """Every tool Hermes currently has registered, as plain dicts
    ``{name, toolset, description}``. Returns ``[]`` if the real registry
    isn't reachable (test environment) or anything about its shape ever
    changes upstream — never raises.
    """
    try:
        from tools.registry import registry
    except Exception:
        return []

    try:
        result = []
        for name in registry.get_all_tool_names():
            entry = registry.get_entry(name)
            result.append({
                "name": name,
                "toolset": (entry.toolset if entry else "") or "",
                "description": (entry.description if entry else "") or "",
            })
        return result
    except Exception:
        return []
