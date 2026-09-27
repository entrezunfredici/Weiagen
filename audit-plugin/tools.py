"""``audit_search`` agent tool — opt-in (``AUDIT_AGENT_TOOL_ENABLED=1``).

Off by default because it reveals *everyone's* tool activity to whoever is
talking to the agent: on a company-wide Slack workspace
(``SLACK_ALLOW_ALL_USERS=true``) that is any employee. Only enable it
together with a rights-plugin ``hermes_tool`` right that restricts
``audit_search`` to an admin/auditor role (see ``README.md``).

Handler signature is ``(args, **kwargs)``: Hermes core calls
``entry.handler(args, task_id=..., session_id=...)``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import audit_store
from tools.registry import tool_result

_MAX_LIMIT = 100


def agent_tool_enabled() -> bool:
    """Return True when ``AUDIT_AGENT_TOOL_ENABLED`` is set to a truthy value."""
    return os.environ.get("AUDIT_AGENT_TOOL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


AUDIT_SEARCH_SCHEMA = {
    "name": "audit_search",
    "description": (
        "Search the audit log of tool calls made through this agent: who called which tool, "
        "with which (redacted) arguments, and the outcome (ok, error, blocked by access rights, "
        "cancelled, timeout) — plus human approval decisions. Newest first. Use it to answer "
        "questions like 'who modified task X yesterday' or 'which calls were blocked today'. "
        "Tool results are never stored, only their size."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "Platform user id (e.g. a Slack member id 'U0123...')."},
            "platform": {"type": "string", "description": "e.g. 'slack', 'cli'."},
            "tool_name": {"type": "string", "description": "Exact tool name, or a prefix ending with '*' (e.g. 'odoo_sdk_*')."},
            "status": {
                "type": "string",
                "description": "Filter by outcome: ok, error, blocked, cancelled, timeout (tool calls) or once, session, always, deny (approvals).",
            },
            "since": {"type": "string", "description": "Relative ('30m', '24h', '7d') or ISO date ('2026-09-24'). Default: '7d'."},
            "limit": {"type": "integer", "description": f"Max events to return (default 20, max {_MAX_LIMIT})."},
        },
        "required": [],
    },
}


def _format_event(e: dict) -> dict:
    return {
        "id": e["id"],
        "time": datetime.fromtimestamp(e["ts"], tz=timezone.utc).isoformat(timespec="seconds"),
        "event": e["event"],
        "tool": e["tool_name"],
        "status": e["status"],
        "error": e["error_message"] or None,
        "user": f"{e['platform']}:{e['user_id']}" if e["user_id"] else None,
        "args": e["args"],
        "duration_ms": e["duration_ms"],
    }


def handle_audit_search(args: dict, **kwargs) -> str:
    """Return matching audit events as ``{"ok": true, "events": [...]}``."""
    try:
        since_ts = audit_store.parse_since(args.get("since") or "7d")
    except ValueError as exc:
        return tool_result({"ok": False, "error": {"code": "VALIDATION_ERROR", "message": str(exc)}})
    try:
        limit = int(args.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    events = audit_store.query_events(
        platform=args.get("platform") or None,
        user_id=args.get("user_id") or None,
        tool_name=args.get("tool_name") or None,
        status=args.get("status") or None,
        since_ts=since_ts,
        limit=max(1, min(limit, _MAX_LIMIT)),
    )
    return tool_result({"ok": True, "count": len(events), "events": [_format_event(e) for e in events]})


# (name, toolset, schema, handler, emoji) — same shape as odoo-plugin's ALL_TOOLS.
AUDIT_TOOLS = [
    ("audit_search", "audit", AUDIT_SEARCH_SCHEMA, handle_audit_search, "🧾"),
]
