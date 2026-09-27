"""``hermes audit`` operator CLI — list, stats, verify, purge.

Same ``register_cli``/``<name>_command`` pattern as rights-plugin's and
odoo-plugin's ``cli.py``, printing JSON results.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import audit_store


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes audit`` argparse tree."""
    subs = subparser.add_subparsers(dest="audit_command")

    ls = subs.add_parser("list", help="List audit events, newest first")
    ls.add_argument("--user", dest="user_id", help="Platform user id, e.g. a Slack member id")
    ls.add_argument("--platform", help="e.g. 'slack', 'cli'")
    ls.add_argument("--tool", dest="tool_name", help="Exact tool name, or a prefix ending with '*'")
    ls.add_argument("--status", help="ok, error, blocked, cancelled, timeout, or an approval choice")
    ls.add_argument("--event", choices=["tool_call", "approval"], help="Event kind")
    ls.add_argument("--since", help="'30m', '24h', '7d', '2w' or an ISO date")
    ls.add_argument("--limit", type=int, default=50)

    st = subs.add_parser("stats", help="Counts by status and most called tools")
    st.add_argument("--since", help="'30m', '24h', '7d', '2w' or an ISO date")

    subs.add_parser("verify", help="Check the hash chain for edited or deleted events")

    pg = subs.add_parser("purge", help="Delete events older than N days (moves the chain anchor)")
    pg.add_argument("--older-than-days", dest="older_than_days", type=int, required=True)
    pg.add_argument("--yes", action="store_true", help="Confirm the deletion")


def _print(result: dict) -> int:
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds") if ts else None


def audit_command(args: argparse.Namespace) -> int:
    """Dispatch a parsed ``hermes audit ...`` command and return its exit code."""
    sub = getattr(args, "audit_command", None)
    try:
        if sub == "list":
            events = audit_store.query_events(
                platform=args.platform, user_id=args.user_id, tool_name=args.tool_name,
                status=args.status, event=args.event,
                since_ts=audit_store.parse_since(args.since), limit=args.limit,
            )
            for e in events:
                e["time"] = _iso(e["ts"])
            return _print({"ok": True, "count": len(events), "events": events})
        if sub == "stats":
            result = audit_store.stats(since_ts=audit_store.parse_since(args.since))
            result["oldest"] = _iso(result.pop("oldest_ts"))
            return _print({"ok": True, **result})
        if sub == "verify":
            return _print(audit_store.verify_chain())
        if sub == "purge":
            if args.older_than_days < 1:
                return _print({"ok": False, "error": "--older-than-days must be >= 1"})
            if not args.yes:
                return _print({"ok": False, "error": "refusing to delete without --yes"})
            return _print({"ok": True, "deleted": audit_store.purge_older_than(args.older_than_days)})
    except ValueError as exc:
        return _print({"ok": False, "error": str(exc)})
    print("usage: hermes audit {list,stats,verify,purge} ...")
    return 2
