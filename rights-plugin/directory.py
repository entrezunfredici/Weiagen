"""Cached identity directory ("who is who" per platform) — sync + staleness.

Purely a UX convenience for the dashboard's role-binding form (pick a name
instead of copy/pasting a raw platform user id) — never consulted by
``engine.py``'s authorization decisions. See ``models.DirectoryEntry``.

There is no Hermes plugin API to register a periodic background job (only
``pre_tool_call``/``pre_llm_call`` hooks and CLI commands — see
``__init__.py`` and ``.agents/DECISIONS.md``), and near-real-time freshness
was explicitly said not to matter ("ça change pas beaucoup"). So refresh is
**lazy**: every read of the cache (the dashboard's ``GET /directory``, and
this plugin's own ``pre_llm_call`` hook, which already fires once per turn)
opportunistically checks staleness against a TTL (default 24h) and, only
when stale, does one real sync before serving whatever is cached — cheap on
every turn that isn't stale (one timestamp comparison, no network call).

Two entry points, deliberately different in how loud they are:

- ``sync_now()`` — always does a real sync, raises on failure. Used by the
  explicit "sync" action (CLI, dashboard "Refresh now" button) — a
  misconfigured token/scope should be an obvious, visible error there.
- ``ensure_fresh()`` — best-effort, swallows every exception (logs a
  warning). Used by the lazy paths above, where a Slack hiccup must never
  block a chat turn or make the dashboard's role-binding tab unusable.

Platform-agnostic on paper (mirrors the rest of this plugin) but only
"slack" is actually wired up today — ``_SYNC_FUNCS`` is the extension point
for a future platform.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

from rights_w_main.errors_manager.errors import ConfigurationError

import models
import slack_directory

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60  # 1 day — "ça change pas beaucoup"


def _sync_slack() -> list[dict[str, Any]]:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise ConfigurationError(
            "SLACK_BOT_TOKEN is not set — can't sync the Slack directory",
            {"platform": "slack"},
        )
    # Module-qualified, not `from slack_directory import fetch_slack_members`
    # at the top of this file — tests monkeypatch
    # slack_directory.fetch_slack_members, which only affects lookups made
    # through the module object itself, not an already-bound local name.
    return slack_directory.fetch_slack_members(token)


# Platform -> "fetch the current live member list" function. Each function
# takes no arguments (reads whatever credentials it needs from the
# environment itself, same convention as _sync_slack above) and returns a
# list of {external_user_id, display_name, real_name, email} dicts.
_SYNC_FUNCS: dict[str, Callable[[], list[dict[str, Any]]]] = {
    "slack": _sync_slack,
}


def _entry_to_dict(entry: models.DirectoryEntry) -> dict[str, Any]:
    return {
        "platform": entry.platform,
        "external_user_id": entry.external_user_id,
        "display_name": entry.display_name,
        "real_name": entry.real_name,
        "email": entry.email,
        "synced_at": entry.synced_at,
    }


def sync_now(platform: str) -> list[dict[str, Any]]:
    """Force a real sync for *platform* right now. Raises on failure
    (unknown platform, missing token, Slack API error) — callers that want
    best-effort behavior should use ``ensure_fresh`` instead."""
    sync_func = _SYNC_FUNCS.get(platform)
    if sync_func is None:
        raise ConfigurationError(
            f"No directory sync is implemented for platform '{platform}'",
            {"platform": platform, "supported": sorted(_SYNC_FUNCS)},
        )
    members = sync_func()
    entries = models.replace_directory_entries(platform, members)
    return [_entry_to_dict(e) for e in entries]


def ensure_fresh(platform: str, *, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> None:
    """Best-effort: sync *platform* only if the cache is older than
    *max_age_seconds* (or has never been synced). Never raises — a Slack
    hiccup here must never block a chat turn (called from pre_llm_call) or
    break the dashboard's role-binding tab (called from its GET route). The
    whole body is inside the try/except, not just the sync call: even the
    staleness check itself touches the data file and could raise (e.g. a
    corrupted JSON file) — that must be swallowed here too, not just a
    failed Slack call."""
    if platform not in _SYNC_FUNCS:
        return
    try:
        last_synced = models.directory_last_synced_at(platform)
        if last_synced and (time.time() - last_synced) <= max_age_seconds:
            return
        sync_now(platform)
    except Exception:
        logger.warning("rights-plugin: best-effort directory sync failed for platform=%s", platform, exc_info=True)


def list_cached(platform: str | None = None) -> list[dict[str, Any]]:
    """Whatever is currently cached — never triggers a sync itself."""
    return [_entry_to_dict(e) for e in models.list_directory_entries(platform)]
