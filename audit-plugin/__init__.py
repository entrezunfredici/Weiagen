"""``audit`` Hermes plugin — append-only, hash-chained audit log of tool calls.

Records *who* called *which* tool with *which* (redacted) arguments and
*what happened* — including calls blocked by rights-plugin — into a local
SQLite file (``$HERMES_HOME/audit-plugin-data/audit.db``). Read back via
``hermes audit ...`` (CLI), the "Audit" dashboard tab, and optionally the
``audit_search`` agent tool (opt-in, see ``tools.py``).

Two observer hooks, both return ``None`` and never raise — an audit
failure must never block or alter a tool call:

- ``post_tool_call``: Hermes core emits it for **every** outcome of a tool
  call, not just successes — ``status`` is ``ok``/``error``/``blocked``/
  ``cancelled``/``timeout``, and a rights-plugin ``block`` directive shows
  up as ``status="blocked"``, ``error_type="plugin_block"`` (confirmed in
  ``agent/tool_executor.py`` of the pinned base image, see
  ``.agents/DECISIONS.md``, 2026-09-24). One hook therefore covers
  executed, failed and denied calls alike.
- ``post_approval_response``: the human (or auxiliary LLM) decision on an
  approval prompt — both rights-plugin ``approve`` directives and Hermes's
  own dangerous-command gate. Linked to its tool call by ``tool_call_id``.

Independent of rights-plugin on purpose (no import of it, see
``audit_identity.py``): auditing must survive rights-plugin being disabled.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Make audit_* modules importable as top-level modules — same sys.path trick
# as odoo-plugin/rights-plugin. Every top-level module of this plugin is
# prefixed `audit_` so it can never collide in sys.modules with another
# plugin's (rights-plugin already owns `identity`, `models`, `engine`...).
# ---------------------------------------------------------------------------
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from hermes_constants import get_hermes_home  # noqa: E402

_DATA_DIR = get_hermes_home() / "audit-plugin-data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("AUDIT_DB_PATH", str(_DATA_DIR / "audit.db"))

import audit_store  # noqa: E402
from audit_identity import resolve_session_owner  # noqa: E402
from audit_redact import redact_args_json, redact_message  # noqa: E402

# cli.py/tools.py MUST be relative imports — Hermes core has its own
# top-level `cli`/`tools` packages (see .agents/CONVENTIONS.md).
from .cli import audit_command, register_cli  # noqa: E402
from .tools import AUDIT_TOOLS, agent_tool_enabled  # noqa: E402


def _result_size(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, (str, bytes)):
        return len(result)
    try:
        return len(json.dumps(result, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001
        return 0


def _post_tool_call(tool_name: str = "", args: Any = None, result: Any = None,
                    task_id: str = "", session_id: str = "", tool_call_id: str = "",
                    turn_id: str = "", duration_ms: int = 0, status: str | None = None,
                    error_type: str | None = None, error_message: str | None = None,
                    **_: Any) -> None:
    """Append one ``tool_call`` event. Observer only: returns None, never raises.

    The tool *result* is never stored (it can hold business data: Odoo
    records, file contents...) — only its size. Arguments and the error
    message are redacted first (see audit_redact.py).
    """
    try:
        platform, user_id = resolve_session_owner(session_id)
        audit_store.append_event(
            event="tool_call",
            tool_name=tool_name,
            status=status or "ok",
            error_type=error_type or "",
            error_message=redact_message(error_message),
            duration_ms=duration_ms,
            session_id=session_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            turn_id=turn_id,
            platform=platform,
            user_id=user_id,
            args_json=redact_args_json(args),
            result_size=_result_size(result),
        )
    except Exception:  # noqa: BLE001
        logger.exception("audit-plugin: failed to record tool call %r", tool_name)


# request_tool_approval() labels plugin-rule approvals "<tool_name> (plugin
# approval rule)" (tools/approval.py) — recover the tool name from it.
_PLUGIN_RULE_COMMAND = re.compile(r"^<([^>]+)> \(plugin approval rule\)$")


def _post_approval_response(command: str = "", description: str = "", pattern_key: str = "",
                            session_key: str = "", surface: str = "", choice: str = "",
                            turn_id: str = "", tool_call_id: str = "", decided_by: str = "",
                            **_: Any) -> None:
    """Append one ``approval`` event (the decision, not the request). Never raises.

    ``status`` holds the decision as Hermes reports it: ``once``/``session``/
    ``always``/``deny``/``timeout``, or ``smart_approve``/``smart_deny``
    when the auxiliary LLM decided.
    """
    try:
        match = _PLUGIN_RULE_COMMAND.match(command or "")
        audit_store.append_event(
            event="approval",
            tool_name=match.group(1) if match else "",
            status=choice or "",
            tool_call_id=tool_call_id,
            turn_id=turn_id,
            args_json=redact_args_json({
                "command": command,
                "description": description,
                "pattern_key": pattern_key,
                "session_key": session_key,
                "surface": surface,
                "decided_by": decided_by or "human",
            }),
        )
    except Exception:  # noqa: BLE001
        logger.exception("audit-plugin: failed to record approval decision")


def register(ctx) -> None:
    """Register the ``hermes audit`` CLI, both observer hooks and (opt-in) the ``audit_search`` tool."""
    ctx.register_cli_command(
        name="audit",
        help="Query and verify the tool-call audit log",
        setup_fn=register_cli,
        handler_fn=audit_command,
        description="Search, summarize, verify (hash chain) and purge the audit log. See: hermes audit list --help",
    )
    ctx.register_hook("post_tool_call", _post_tool_call)
    ctx.register_hook("post_approval_response", _post_approval_response)

    if agent_tool_enabled():
        for name, toolset, schema, handler, emoji in AUDIT_TOOLS:
            ctx.register_tool(name=name, toolset=toolset, schema=schema, handler=handler, emoji=emoji)
