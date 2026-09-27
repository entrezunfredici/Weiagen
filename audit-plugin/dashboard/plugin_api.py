"""Dashboard backend routes for the audit plugin — read-only.

Mounted by Hermes's dashboard web server at ``/api/plugins/audit`` (same
mechanism as rights-plugin/odoo-plugin's ``plugin_api.py``; no auth code
here, the host's dashboard middleware already gates every ``/api/...``
request).

Runs in the **dashboard's own process**, separate from the gateway that
loads ``../__init__.py`` — so it repeats the ``sys.path``/``AUDIT_DB_PATH``
bootstrap itself (see ``.agents/CONVENTIONS.md``). Deliberately exposes no
write/purge route: deleting audit events stays a CLI-only, explicit
operator action (``hermes audit purge --yes``).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from hermes_constants import get_hermes_home  # noqa: E402

_DATA_DIR = get_hermes_home() / "audit-plugin-data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("AUDIT_DB_PATH", str(_DATA_DIR / "audit.db"))

from fastapi import APIRouter, HTTPException, Query  # noqa: E402

import audit_store  # noqa: E402

router = APIRouter()


def _since(value: Optional[str]) -> Optional[float]:
    try:
        return audit_store.parse_since(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


def _iso(ts: Optional[float]) -> Optional[str]:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds") if ts else None


@router.get("/events")
def list_events(
    user: Optional[str] = None,
    platform: Optional[str] = None,
    tool: Optional[str] = None,
    status: Optional[str] = None,
    event: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Return matching audit events, newest first."""
    events = audit_store.query_events(
        platform=platform or None, user_id=user or None, tool_name=tool or None,
        status=status or None, event=event or None, since_ts=_since(since),
        limit=limit, offset=offset,
    )
    for e in events:
        e["time"] = _iso(e["ts"])
    return {"events": events}


@router.get("/stats")
def get_stats(since: Optional[str] = None):
    """Return counts by status and the most called tools."""
    result = audit_store.stats(since_ts=_since(since))
    result["oldest"] = _iso(result.pop("oldest_ts"))
    result["retention_days"] = audit_store.retention_days()
    return result


@router.get("/verify")
def verify():
    """Walk the hash chain and report the first broken link, if any."""
    return audit_store.verify_chain()
