"""Slack workspace member fetch — ``users.list``, stdlib only.

Talks to Slack's Web API directly via ``urllib`` (no new dependency — this
plugin has zero third-party requirements by design, see ``requirements.txt``)
using whatever bot token is handed to it. Doesn't know or care where that
token comes from — see ``directory.py`` for how it's read from
``SLACK_BOT_TOKEN``, the same environment variable Hermes's own Slack
platform adapter already gets from ``../docker-compose*.yml``. This module
owns no Slack credentials of its own.

``_urlopen`` is a module-level indirection purely so tests can monkeypatch
it without touching real sockets — production code never overrides it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from rights_w_main.errors_manager.errors import ServiceError

_USERS_LIST_URL = "https://slack.com/api/users.list"
_PAGE_LIMIT = 200
_TIMEOUT_SECONDS = 10

_urlopen = urllib.request.urlopen


def fetch_slack_members(token: str) -> list[dict[str, Any]]:
    """Return every non-bot, non-deleted workspace member as a plain dict:
    ``{external_user_id, display_name, real_name, email}``. Paginates via
    Slack's cursor-based ``users.list``. Raises ``ServiceError`` on any
    Slack-reported error (bad token, missing ``users:read`` scope, rate
    limit, network failure) — the caller (``directory.py::sync_now``)
    decides whether that's fatal (explicit CLI/dashboard sync) or swallowed
    (the best-effort lazy refresh on every turn).
    """
    members: list[dict[str, Any]] = []
    cursor = ""
    while True:
        params = {"limit": str(_PAGE_LIMIT)}
        if cursor:
            params["cursor"] = cursor
        url = f"{_USERS_LIST_URL}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with _urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ServiceError(f"Unable to reach Slack: {exc}", {"url": _USERS_LIST_URL}) from exc
        except json.JSONDecodeError as exc:
            raise ServiceError("Slack returned a non-JSON response", {"url": _USERS_LIST_URL}) from exc

        if not payload.get("ok"):
            raise ServiceError(
                f"Slack users.list failed: {payload.get('error', 'unknown_error')}",
                {"slack_error": payload.get("error")},
            )

        for member in payload.get("members", []):
            if member.get("deleted") or member.get("is_bot") or member.get("id") == "USLACKBOT":
                continue
            profile = member.get("profile") or {}
            members.append({
                "external_user_id": member["id"],
                "display_name": profile.get("display_name") or profile.get("real_name") or member.get("name", member["id"]),
                "real_name": profile.get("real_name", ""),
                "email": profile.get("email", ""),
            })

        cursor = (payload.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            break

    return members
