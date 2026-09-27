"""Resolve a Hermes ``session_id`` to the ``(platform, user_id)`` that owns it.

Deliberately independent of rights-plugin (see ``.agents/DECISIONS.md``,
2026-09-24): the audit log must keep working, and keep recording *who*,
even when rights-plugin is disabled or broken — that is precisely when an
audit trail matters most. Same lookup rights-plugin's ``identity.py`` does
(``hermes_state.SessionDB(read_only=True).get_session``, returns a dict
with ``source``/``user_id`` or ``None``), without the role resolution:
roles are a rights-plugin concept and can be re-derived from
``(platform, user_id)`` later.

Named ``audit_identity`` (not ``identity``) on purpose: rights-plugin
already puts a top-level ``identity`` module on ``sys.path`` in the same
Hermes process — a second one with the same name would silently resolve
to whichever loaded first (``sys.modules`` is a global cache by name).
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict

logger = logging.getLogger(__name__)

# A session's owner never changes, so caching is safe; bounded so a
# long-running gateway doesn't grow it forever.
_CACHE_MAX = 512
_cache: "OrderedDict[str, tuple[str, str]]" = OrderedDict()
_cache_lock = threading.Lock()


def resolve_session_owner(session_id: str | None) -> tuple[str, str]:
    """Return ``(platform, user_id)`` for *session_id*, or ``("", "")`` if unknown.

    Never raises: an audit hook must not break a tool call because the
    session database is momentarily unavailable.
    """
    if not session_id:
        return "", ""
    with _cache_lock:
        if session_id in _cache:
            _cache.move_to_end(session_id)
            return _cache[session_id]
    try:
        from hermes_state import SessionDB

        session = SessionDB(read_only=True).get_session(session_id)
    except Exception:  # noqa: BLE001
        logger.debug("audit-plugin: session lookup failed for %s", session_id, exc_info=True)
        return "", ""
    if not session:
        return "", ""
    owner = (str(session.get("source") or ""), str(session.get("user_id") or ""))
    if owner[0] and owner[1]:
        with _cache_lock:
            _cache[session_id] = owner
            while len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
    return owner


def clear_cache() -> None:
    """Forget every cached session owner (used by tests)."""
    with _cache_lock:
        _cache.clear()
