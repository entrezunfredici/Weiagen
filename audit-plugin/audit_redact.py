"""Redact tool arguments before they are written to the audit log.

Two layers, both always applied to what gets stored:

1. **Key-based**: any dict key that looks like a secret (``password``,
   ``token``, ``api_key``, ``authorization``...) has its value replaced by
   ``"[REDACTED]"``, at any nesting depth. This is what catches the signed
   MCP identity token rights-plugin injects (passed as a ``caller_token``/
   ``*_token`` argument) and Odoo credentials.
2. **Content-based**: every remaining string value goes through Hermes's
   own ``agent.redact.redact_sensitive_text`` when it is importable (it is
   in a real Hermes process — the same redactor Hermes uses for its
   approval hooks), which catches secrets inlined in free text, e.g. a
   ``curl -H "Authorization: Bearer ..."`` shell command. Outside Hermes
   (unit tests) this layer is skipped silently.

Then everything is size-capped: long strings are truncated, and the final
JSON is capped so a single huge argument (a file body passed to
``write_file``) can't bloat the log.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

REDACTED = "[REDACTED]"
MAX_STRING_CHARS = 500
MAX_ARGS_JSON_CHARS = 4000
MAX_DEPTH = 6

_SENSITIVE_KEY = re.compile(
    # `auth` only as a whole word segment: a bare substring match would
    # also redact harmless keys like Odoo's `author_id`.
    r"password|passwd|passphrase|secret|token|api[_-]?key|apikey|authorization|"
    r"(^|[_-])auth($|[_-])|credential|private[_-]?key|cookie|session[_-]?key|signature",
    re.IGNORECASE,
)

try:  # pragma: no cover - only importable inside a real Hermes process
    from agent.redact import redact_sensitive_text as _hermes_redact
except Exception:  # noqa: BLE001 - any import failure means "not available"
    _hermes_redact = None


def _redact_text(text: str) -> str:
    if _hermes_redact is not None:
        try:
            text = _hermes_redact(text, force=True)
        except Exception:  # noqa: BLE001 - redaction must never break auditing
            pass
    if len(text) > MAX_STRING_CHARS:
        text = f"{text[:MAX_STRING_CHARS]}…[+{len(text) - MAX_STRING_CHARS} chars]"
    return text


def is_sensitive_key(key: str) -> bool:
    """Return True when a dict key name looks like it holds a secret."""
    return bool(_SENSITIVE_KEY.search(str(key)))


def redact_value(value: Any, *, depth: int = 0, text_fn: Callable[[str], str] = _redact_text) -> Any:
    """Return a redacted, size-capped copy of *value* (JSON-compatible types only)."""
    if depth > MAX_DEPTH:
        return "[…]"
    if isinstance(value, dict):
        return {
            str(k): (REDACTED if is_sensitive_key(k) else redact_value(v, depth=depth + 1, text_fn=text_fn))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_value(v, depth=depth + 1, text_fn=text_fn) for v in value]
    if isinstance(value, str):
        return text_fn(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return text_fn(repr(value))


def redact_args_json(args: Any) -> str:
    """Redact *args* and serialize it to a JSON string of at most ``MAX_ARGS_JSON_CHARS``."""
    if args is None:
        return "{}"
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {"_raw": args}
    encoded = json.dumps(redact_value(args), ensure_ascii=False, default=str)
    if len(encoded) > MAX_ARGS_JSON_CHARS:
        encoded = json.dumps(
            {"_truncated": True, "_preview": encoded[:MAX_ARGS_JSON_CHARS]}, ensure_ascii=False
        )
    return encoded


def redact_message(message: Any) -> str:
    """Redact and cap a free-text message (e.g. a tool error message)."""
    return _redact_text(str(message)) if message else ""
