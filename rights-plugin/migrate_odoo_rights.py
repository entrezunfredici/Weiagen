"""One-off migration: legacy odoo-plugin ``OdooRight`` JSON -> ``AccessRight``.

Every existing ``OdooRight`` becomes one ``AccessRight`` bound to the
implicit ``"everyone"`` role — nobody had a per-identity role before this
plugin existed (odoo-plugin's authorization was scoped to
``(profile_id, odoo_model, field)`` only, with no notion of *who* was
asking), so binding to ``"everyone"`` is the exact backward-compatible
mapping: every identity keeps precisely the access it always implicitly had.

Idempotent by construction: each migrated right's id is
``f"migrated:{legacy_id}"`` — re-running upserts the same records rather
than duplicating them (``SDKTable.save()`` is an upsert by primary key).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from rights_w_main.errors_manager.errors import ServiceError

import models

logger = logging.getLogger(__name__)

_MIGRATED_ID_PREFIX = "migrated:"


def migrate_odoo_rights(*, source_path: str, dry_run: bool = False) -> list[dict[str, Any]]:
    """Read a legacy ``odoo-rights.json`` (list of ``OdooRight.to_record()``
    dicts) and upsert one ``AccessRight`` per entry.

    Returns the list of migrated entries (as plain dicts, the shape that
    would be/was passed to ``models.create_access_right``) whether or not
    ``dry_run`` is set — callers use the return value to report what
    happened either way. Returns ``[]`` (no error) if the source file
    doesn't exist — migrating "nothing to migrate" is a normal outcome, not
    a failure, since not every deployment necessarily has legacy data.
    """
    path = Path(source_path)
    if not path.exists():
        return []

    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ServiceError(
            "Unable to read legacy odoo-rights.json", {"path": str(path)}
        ) from exc
    if not isinstance(records, list):
        return []

    migrated: list[dict[str, Any]] = []
    for record in records:
        legacy_id = record.get("id")
        if not legacy_id:
            continue

        entry = {
            "id": f"{_MIGRATED_ID_PREFIX}{legacy_id}",
            "roles": ["everyone"],
            "resource_type": "odoo_model",
            "resource_id": f"{record.get('profile_id', '')}:{record.get('odoo_model', '')}",
            "fields": record.get("fields") or ["*"],
            "label": record.get("label") or f"migrated from OdooRight {legacy_id}",
            "create": bool(record.get("create", False)),
            "read": bool(record.get("read", True)),
            "update": bool(record.get("update", False)),
            "delete": bool(record.get("delete", False)),
            "require_confirmation": bool(record.get("require_confirmation", False)),
            "confirm_create": bool(record.get("confirm_create", False)),
            "confirm_read": bool(record.get("confirm_read", False)),
            "confirm_update": bool(record.get("confirm_update", False)),
            "confirm_delete": bool(record.get("confirm_delete", False)),
        }
        migrated.append(entry)

        if not dry_run:
            models.create_access_right(
                roles=entry["roles"],
                resource_type=entry["resource_type"],
                resource_id=entry["resource_id"],
                fields=entry["fields"],
                label=entry["label"],
                id=entry["id"],
                create=entry["create"],
                read=entry["read"],
                update=entry["update"],
                delete=entry["delete"],
                require_confirmation=entry["require_confirmation"],
                confirm_create=entry["confirm_create"],
                confirm_read=entry["confirm_read"],
                confirm_update=entry["confirm_update"],
                confirm_delete=entry["confirm_delete"],
            )

    return migrated


def maybe_migrate_odoo_rights_on_load() -> None:
    """Auto-migrate once at plugin load time, if there's legacy data and it
    hasn't been migrated yet. Called from ``__init__.py::register()``.

    Guarded by the presence of any already-migrated AccessRight (id prefix
    ``"migrated:"``) rather than a separate "have we ever run" flag file —
    simpler, and self-healing if the access-rights file is ever wiped.
    """
    # ODOO_RIGHTS_PATH is odoo-plugin's own env var (see that plugin's
    # __init__.py) — read directly here rather than coupling models.py to
    # it, since this migration path is the only thing in rights-plugin that
    # needs to know odoo-plugin's env var name at all.
    source_path = os.getenv("ODOO_RIGHTS_PATH", "")
    if not source_path or not Path(source_path).exists():
        return

    already_migrated = any(
        right.id.startswith(_MIGRATED_ID_PREFIX) for right in models.list_access_rights()
    )
    if already_migrated:
        return

    migrated = migrate_odoo_rights(source_path=source_path)
    if migrated:
        logger.info(
            "rights-plugin: auto-migrated %d legacy OdooRight entries from %s "
            "into AccessRight (role='everyone')",
            len(migrated), source_path,
        )
