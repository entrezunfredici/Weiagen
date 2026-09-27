"""Stable public contract for other plugins to consume rights-plugin.

This is the ONE module other plugins should import from — everything else
in this plugin (``models``, ``engine``, ``identity``, ``config_executor``,
``cli``) is an internal implementation detail that may change without
notice. Any change to the names/signatures re-exported here is a change to
a public interface and must be signalled explicitly before being made (see
``.agents/AGENT.md``).

Consumers locate this module as a sibling-directory import — see
``odoo-plugin/w_odoo/rights_bridge.py`` for the exact mechanism (a
deterministic ``sys.path`` insertion of the ``rights`` plugin directory,
resolved relative to the caller's own plugin directory, not relying on
rights-plugin having already been imported/loaded first).

Usage (from a consumer plugin)::

    try:
        from rights_plugin_api import check_right, resolve_identity
        RIGHTS_AVAILABLE = True
    except ImportError:
        RIGHTS_AVAILABLE = False

    identity = resolve_identity(session_id=session_id)
    decision = check_right(
        roles=identity.roles,
        resource_type="odoo_model",
        resource_id=f"{profile_id}:{model}",
        operation="read",
        field="name",
    )
    if not decision.allowed:
        ...  # deny
"""

from __future__ import annotations

from typing import Any

from engine import check_right, has_any_right_for
from identity import ROLE_AUTOMATION, ROLE_EVERYONE, Identity, resolve_identity
from rights_w_main.right_manager.right_manager import Operation, RightDecision

import models


def _right_to_dict(r: models.AccessRight) -> dict[str, Any]:
    return {
        "id": r.id,
        "label": r.label,
        "roles": list(r.roles),
        "resource_id": r.resource_id,
        "fields": list(r.fields),
        "create": r.create,
        "read": r.read,
        "update": r.update,
        "delete": r.delete,
        "require_confirmation": r.require_confirmation,
        "confirm_create": r.confirm_create,
        "confirm_read": r.confirm_read,
        "confirm_update": r.confirm_update,
        "confirm_delete": r.confirm_delete,
    }


def list_rights_for_resource_type(resource_type: str) -> list[dict[str, Any]]:
    """Return every AccessRight for a resource_type, across ALL roles — an
    unscoped, diagnostic view (not an authorization decision). For
    consumers building operator-facing introspection (e.g. odoo-plugin's
    ``odoo_list_rights``/``odoo_config_validate`` tools, which reported
    every configured right regardless of caller identity even before
    rights-plugin existed — this preserves that exact behavior rather than
    introducing a new information leak).
    """
    return [_right_to_dict(r) for r in models.rights_for_resource_type(resource_type)]


def list_rights_for_roles(roles: list[str], resource_type: str) -> list[dict[str, Any]]:
    """Return every AccessRight, as a plain dict (not the internal model
    class — this module never leaks its own classes across the plugin
    boundary beyond the dataclasses re-exported below), whose role is one
    of ``roles`` and whose resource_type matches.

    For consumers that need to enumerate rights themselves rather than
    check one resource at a time — e.g. odoo-plugin's
    odoo_sdk_list_allowed_models/_fields, which need to know every
    resource_id (``f"{profile_id}:{model}"``) a set of roles has any right
    on before it can group them by model.
    """
    return [_right_to_dict(r) for r in models.rights_for_roles_and_resource_type(roles, resource_type)]


def create_right(
    *,
    roles: list[str],
    resource_type: str,
    resource_id: str,
    fields: list[str] | None = None,
    label: str = "",
    id: str | None = None,
    create: bool = False,
    read: bool = True,
    update: bool = False,
    delete: bool = False,
    execute: bool = False,
    require_confirmation: bool = False,
    confirm_create: bool = False,
    confirm_read: bool = False,
    confirm_update: bool = False,
    confirm_delete: bool = False,
    confirm_execute: bool = False,
) -> dict[str, Any]:
    """Create or update an AccessRight (upsert by id). Thin wrapper around
    ``models.create_access_right`` — the write-side counterpart to
    ``check_right``/``list_rights_for_*``, needed so a consumer plugin's own
    dashboard (e.g. odoo-plugin's) can manage rights scoped to its own
    resource_type without going through the ``hermes rights`` CLI.

    ``roles`` (plural, a list) since 2026-08-18 — a right can apply to
    several roles at once (see ``.agents/DECISIONS.md``). Signalled
    public-interface change: the previous singular ``role: str`` parameter
    is gone, no compatibility shim (mirrors the earlier removal of
    ``hermes odoo right add/rm`` without an alias).
    """
    right = models.create_access_right(
        roles=list(roles), resource_type=resource_type, resource_id=resource_id,
        fields=fields, label=label, id=id,
        create=create, read=read, update=update, delete=delete, execute=execute,
        require_confirmation=require_confirmation,
        confirm_create=confirm_create, confirm_read=confirm_read,
        confirm_update=confirm_update, confirm_delete=confirm_delete,
        confirm_execute=confirm_execute,
    )
    return _right_to_dict(right)


def delete_right(right_id: str) -> bool:
    """Delete an AccessRight by id. Returns True if it existed."""
    return models.delete_access_right(right_id)


__all__ = [
    "ROLE_AUTOMATION",
    "ROLE_EVERYONE",
    "Identity",
    "Operation",
    "RightDecision",
    "check_right",
    "create_right",
    "delete_right",
    "has_any_right_for",
    "list_rights_for_resource_type",
    "list_rights_for_roles",
    "resolve_identity",
]
