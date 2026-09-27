"""Resolve a Hermes caller into a generic (platform, external_user_id, roles) identity.

Two resolution paths, matching the two hook contexts that call into this
module:

- ``pre_llm_call`` gets ``platform``/``sender_id`` directly as kwargs
  (confirmed in Hermes core, ``agent/turn_context.py``) — no lookup needed.
- ``pre_tool_call`` only gets ``session_id``/``task_id`` — this module
  resolves it via ``hermes_state.SessionDB(read_only=True).get_session(...)``
  (confirmed: returns a dict with ``source``/``user_id`` keys, or ``None``,
  never raises — see ``.agents/DECISIONS.md``).

If neither resolves to a usable ``(platform, external_user_id)`` pair (e.g.
a cron-triggered session with no session row, or a session missing
``user_id``), the identity falls back to a pseudo-identity carrying only
``ROLE_AUTOMATION``. This is a deliberate, safe default: automation-triggered
tool calls are governable the same way as any other (see
``rights_plugin/__init__.py``'s ``pre_tool_call`` hook), just under a
distinct role an operator can configure narrowly rather than silently
inheriting whichever human happened to create the cron.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hermes_state import SessionDB

import models

ROLE_EVERYONE = "everyone"
ROLE_AUTOMATION = "automation"

_AUTOMATION_PLATFORM = "automation"
_AUTOMATION_USER_ID = "cron"


@dataclass(slots=True)
class Identity:
    platform: str
    external_user_id: str
    roles: list[str] = field(default_factory=list)


def _resolve_platform_and_user(
    *, session_id: str | None, platform: str | None, external_user_id: str | None
) -> tuple[str, str] | None:
    """Return (platform, external_user_id) if resolvable, else None."""
    if platform and external_user_id:
        return platform, external_user_id

    if session_id:
        # read_only=True: this is a lookup-only call site (a hook), never a
        # writer — avoids taking the SessionDB write lock from every tool
        # call / turn across every Hermes process sharing the same state.db.
        session = SessionDB(read_only=True).get_session(session_id)
        if session:
            resolved_platform = session.get("source")
            resolved_user_id = session.get("user_id")
            if resolved_platform and resolved_user_id:
                return resolved_platform, resolved_user_id

    return None


def resolve_identity(
    *,
    session_id: str | None = None,
    platform: str | None = None,
    external_user_id: str | None = None,
) -> Identity:
    """Resolve the calling identity and its roles.

    Roles always include ``ROLE_EVERYONE`` (every resolved identity holds
    it, on top of whatever ``RoleBinding.roles`` says) and, when no identity
    resolves at all, ``ROLE_AUTOMATION`` instead of any binding lookup.
    """
    resolved = _resolve_platform_and_user(
        session_id=session_id, platform=platform, external_user_id=external_user_id
    )

    if resolved is None:
        return Identity(
            platform=_AUTOMATION_PLATFORM,
            external_user_id=_AUTOMATION_USER_ID,
            roles=[ROLE_AUTOMATION, ROLE_EVERYONE],
        )

    resolved_platform, resolved_user_id = resolved
    binding = models.get_role_binding_for_identity(resolved_platform, resolved_user_id)
    roles = sorted(set((binding.roles if binding else [])) | {ROLE_EVERYONE})
    return Identity(platform=resolved_platform, external_user_id=resolved_user_id, roles=roles)
