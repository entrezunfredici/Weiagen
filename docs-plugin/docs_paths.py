"""Where generated documents may be written, and how they reach the user.

Two problems with the pre-2026-09-24 tools (when they still lived in
odoo-plugin), both fixed here — see ``.agents/DECISIONS.md``, 2026-09-24:

1. **Files never reached the user.** They were written to an arbitrary
   path inside the container (the skill's examples used ``/workspace/...``)
   and nothing sent them anywhere. Hermes's gateway turns a
   ``MEDIA:<absolute path>`` tag in the agent's final reply into a native
   attachment (Slack upload included — ``gateway/platforms/base.py``,
   ``.xlsx``/``.docx``/``.pptx`` are in its ``SUPPORTED_DOCUMENT_TYPES``),
   and ``$HERMES_HOME/cache/documents`` is one of the roots it *always*
   accepts, even in ``HERMES_MEDIA_DELIVERY_STRICT`` mode. So documents are
   written there by default, and every tool result carries the ready-made
   ``MEDIA:`` tag.
2. **Writes anywhere the ``hermes`` user can write.** An ``output_path``
   of ``/opt/data/config.yaml.xlsx`` is harmless, but nothing stopped a
   prompt-injected call from overwriting a real file whose name happens to
   end in ``.docx``/``.xlsx``/``.pptx`` anywhere on the volume. Writes are
   now confined to the document cache plus operator-declared roots
   (``DOCS_OUTPUT_DIRS``). Reading stays unrestricted: the readers only
   parse office files, and files users upload on Slack land in the same
   cache anyway.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from hermes_constants import get_hermes_dir

GENERATED_SUBDIR = "generated"
_SAFE_STEM = re.compile(r"[^\w. -]+")  # \w is Unicode-aware: keeps accented letters


class OutputPathError(ValueError):
    """Raised when a requested output path is outside the allowed roots or malformed."""


def default_output_dir() -> Path:
    """Return ``<Hermes document cache>/generated`` — always deliverable via ``MEDIA:``."""
    return get_hermes_dir("cache/documents", "document_cache") / GENERATED_SUBDIR


def allowed_output_roots() -> list[Path]:
    """Return the resolved directories documents may be written under.

    The default output directory, plus every absolute path listed in
    ``DOCS_OUTPUT_DIRS`` (comma- or ``os.pathsep``-separated). Relative
    entries are ignored rather than resolved against an unpredictable cwd.
    A file written under an extra root is only attachable if the gateway
    also accepts it (non-strict mode, or ``HERMES_MEDIA_ALLOW_DIRS``).
    """
    roots = [default_output_dir()]
    for chunk in os.environ.get("DOCS_OUTPUT_DIRS", "").split(os.pathsep):
        for raw in chunk.split(","):
            raw = raw.strip()
            if raw and Path(raw).expanduser().is_absolute():
                roots.append(Path(raw).expanduser())
    return [r.resolve(strict=False) for r in roots]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _default_filename(kind: str, extension: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{kind}-{stamp}-{secrets.token_hex(2)}{extension}"


def resolve_output_path(output_path: str | None, *, extension: str, kind: str) -> Path:
    """Return the absolute path a new document should be written to.

    - empty/missing ``output_path`` → auto-named file in the default dir;
    - a bare file name or a relative path → placed in the default dir
      (sub-directories kept, ``..`` rejected);
    - an absolute path → accepted only if it resolves inside an allowed
      root (symlinks resolved first, so a link can't point outside).

    The extension is enforced (appended when missing, rejected when it is a
    different one) so a call can never produce e.g. ``config.yaml``.
    Raises :class:`OutputPathError` otherwise.
    """
    extension = extension.lower()
    raw = (output_path or "").strip()
    if not raw:
        candidate = default_output_dir() / _default_filename(kind, extension)
    else:
        requested = Path(raw).expanduser()
        if not requested.is_absolute():
            if ".." in requested.parts:
                raise OutputPathError(f"relative output_path must not contain '..': {raw!r}")
            requested = default_output_dir() / requested
        candidate = requested

    suffix = candidate.suffix.lower()
    if not suffix:
        candidate = candidate.with_name(candidate.name + extension)
    elif suffix != extension:
        raise OutputPathError(f"output_path must end with {extension!r}, got {candidate.name!r}")

    stem = _SAFE_STEM.sub("_", candidate.stem).strip(" .") or kind
    candidate = candidate.with_name(stem + extension)

    resolved = candidate.resolve(strict=False)
    if not any(_is_within(resolved, root) for root in allowed_output_roots()):
        roots = ", ".join(str(r) for r in allowed_output_roots())
        raise OutputPathError(
            f"output_path {str(resolved)!r} is outside the allowed output directories ({roots}). "
            "Omit output_path (or pass just a file name) to use the default directory."
        )
    return resolved


def media_tag(path: Path | str) -> str:
    """Return the ``MEDIA:<path>`` tag Hermes turns into a file attachment."""
    return f"MEDIA:{path}"
