"""Bridges odoo-plugin's CRUD authorization checks to rights-plugin.

odoo-plugin no longer owns its own rights model (``OdooRight`` is gone —
see ``.agents/DECISIONS.md``, "rights-plugin: vendoring vs cross-plugin
import"). Every check in this module delegates to the sibling ``rights``
plugin via its stable public contract, ``rights_plugin_api``.

Cross-plugin mechanism: Hermes plugins load in isolated ``importlib``
namespaces with no built-in cross-plugin service registry, so this module
locates the ``rights`` plugin directory as a **sibling** of this plugin's
own directory and inserts it into ``sys.path`` itself — deliberately *not*
relying on rights-plugin having already been imported/loaded first
(load-order independence), the same way ``odoo-plugin/__init__.py`` already
inserts its own directory for ``w_main``/``w_odoo`` to
resolve.

Two sibling directory names are tried, since this repo's folder name
(``rights-plugin/``, in a local checkout or this repo's own test runs)
differs from the Hermes plugin name it's mounted/baked under in a real
deployment (``.../plugins/odoo`` -> ``.../plugins/rights``, matching
``plugin.yaml``'s ``name: rights`` — see ``docker-compose.yml``/
``Dockerfile``, which rename ``odoo-plugin/`` -> ``plugins/odoo`` the same
way).

If rights-plugin isn't installed/enabled, every check here **fails
closed** (``RIGHTS_AVAILABLE = False`` -> deny) — this is documented as a
hard operational requirement: rights-plugin must always be enabled
alongside odoo-plugin, see ``../README.md``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from w_main.errors_manager.errors import ConfigurationError

logger = logging.getLogger(__name__)

_ODOO_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_RIGHTS_PLUGIN_DIR_CANDIDATES = (
    _ODOO_PLUGIN_DIR.parent / "rights",         # deployed: plugins/odoo, plugins/rights
    _ODOO_PLUGIN_DIR.parent / "rights-plugin",  # this repo's own checkout/tests
)
for _candidate in _RIGHTS_PLUGIN_DIR_CANDIDATES:
    if _candidate.is_dir():
        if str(_candidate) not in sys.path:
            # append, not insert(0): `rights_plugin_api` is a name unique to
            # this repo (nothing else on sys.path can shadow it), so
            # priority doesn't matter for resolving it. It DOES matter for
            # `tests` — neither odoo-plugin/tests/ nor rights-plugin/tests/
            # has an __init__.py (see tests/pytest.ini for why), so once
            # both directories are on sys.path in the same process, `tests`
            # becomes an implicit namespace package merging both, and
            # submodule lookups (`tests.conftest`) resolve against whichever
            # portion sys.path lists first. odoo-plugin/tests/conftest.py
            # already inserts ODOO_PLUGIN_DIR at position 0 before this
            # module is ever imported; appending here keeps that portion
            # first so odoo-plugin's own test run finds its own conftest.py,
            # not rights-plugin's — insert(0) here previously shadowed it
            # and broke `pytest tests/` under odoo-plugin/ whenever
            # rights-plugin/ was checked out alongside it (i.e. always, in
            # this repo and in CI).
            sys.path.append(str(_candidate))
        break

try:
    from rights_plugin_api import (
        ROLE_EVERYONE,
        Identity,
        check_right,
        create_right as _create_right_api,
        delete_right as _delete_right_api,
        list_rights_for_resource_type,
        list_rights_for_roles,
        resolve_identity,
    )
    RIGHTS_AVAILABLE = True
except ImportError:
    ROLE_EVERYONE = "everyone"
    Identity = None  # type: ignore[assignment,misc]
    check_right = None  # type: ignore[assignment]
    _create_right_api = None  # type: ignore[assignment]
    _delete_right_api = None  # type: ignore[assignment]
    list_rights_for_resource_type = None  # type: ignore[assignment]
    list_rights_for_roles = None  # type: ignore[assignment]
    resolve_identity = None  # type: ignore[assignment]
    RIGHTS_AVAILABLE = False
    logger.warning(
        "odoo-plugin: rights-plugin not found (tried %s) — all Odoo CRUD "
        "will be denied until it is installed and enabled (see ../README.md).",
        ", ".join(str(c) for c in _RIGHTS_PLUGIN_DIR_CANDIDATES),
    )


def get_identity(session_id: str | None) -> "Identity":
    """Resolve the calling identity for a given session_id.

    Returns a rights-plugin ``Identity`` (``.platform``, ``.external_user_id``,
    ``.roles``) even when rights-plugin is unavailable — a degraded
    zero-roles stand-in in that case, so callers never need a separate
    availability check before reading ``.roles``.
    """
    if not RIGHTS_AVAILABLE:
        return _DegradedIdentity()
    return resolve_identity(session_id=session_id)


class _DegradedIdentity:
    """Stand-in for rights_plugin_api.Identity when rights-plugin is absent.

    ``roles`` is empty on purpose: with no rights-plugin to consult, every
    check_field() call below returns (False, False) regardless of roles, so
    this never grants anything — it only exists so callers can uniformly
    read ``identity.roles`` without an availability check first.
    """

    platform = "unavailable"
    external_user_id = "unavailable"
    roles: list[str] = []


def check_field(
    profile_id: str, model: str, field: str, operation: str, roles: list[str]
) -> tuple[bool, bool]:
    """Return (allowed, require_confirmation) for a field/operation pair.

    Deny-by-default: returns (False, False) whenever rights-plugin is
    unavailable, or no right of these roles covers the field — same
    contract odoo_cli_for_ai.py's callers already expect from the old
    get_right_manager_for()-based _check_field, just never raising.
    """
    if not RIGHTS_AVAILABLE:
        return False, False
    decision = check_right(
        roles=roles,
        resource_type="odoo_model",
        resource_id=f"{profile_id}:{model}",
        operation=operation,
        field=field,
    )
    return decision.allowed, decision.require_confirmation


def applies_to_field(right: dict[str, Any], field_name: str) -> bool:
    """True if a right dict (from rights_for_profile/_and_model) covers field_name."""
    return "*" in right["fields"] or field_name in right["fields"]


def rights_for_profile(profile_id: str, roles: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """(model, right_dict) pairs for every AccessRight covering this profile,
    across the given roles. Empty list when rights-plugin is unavailable.

    ``resource_id`` is odoo-plugin's own convention, ``f"{profile_id}:{model}"``
    — rights-plugin treats it as opaque, so the split back into
    (profile_id, model) happens here, not there.
    """
    if not RIGHTS_AVAILABLE:
        return []
    prefix = f"{profile_id}:"
    pairs = []
    for right in list_rights_for_roles(roles, "odoo_model"):
        resource_id = right["resource_id"]
        if resource_id.startswith(prefix):
            model = resource_id[len(prefix):]
            pairs.append((model, right))
    return pairs


def rights_for_profile_and_model(profile_id: str, model: str, roles: list[str]) -> list[dict[str, Any]]:
    """Rights (across the given roles) covering one specific (profile, model)."""
    return [right for right_model, right in rights_for_profile(profile_id, roles) if right_model == model]


def _reshape_one(right: dict[str, Any]) -> dict[str, Any]:
    """Reshape one generic AccessRight dict (rights-plugin's shape) into the
    OdooRight-shaped dict odoo-plugin's tools/dashboard already document
    and expect (profile_id/odoo_model split back out of resource_id)."""
    profile_id, _, model = right["resource_id"].partition(":")
    return {
        "id": right["id"],
        "label": right["label"],
        "profile_id": profile_id,
        "odoo_model": model,
        "fields": right["fields"],
        "create": right["create"],
        "read": right["read"],
        "update": right["update"],
        "delete": right["delete"],
        "require_confirmation": right["require_confirmation"],
        "confirm_create": right["confirm_create"],
        "confirm_read": right["confirm_read"],
        "confirm_update": right["confirm_update"],
        "confirm_delete": right["confirm_delete"],
    }


def all_odoo_rights() -> list[dict[str, Any]]:
    """Every AccessRight for resource_type="odoo_model", across ALL roles —
    unscoped diagnostic view, reshaped into OdooRight-shaped dicts.

    Used only by odoo_cli_for_config.py's read-only ``list_rights`` action
    (backing the ``odoo_list_rights``/``odoo_config_validate`` tools) —
    those were never scoped to a calling identity even before rights-plugin
    existed, so this preserves that, unlike rights_for_profile/_and_model
    above which ARE role-scoped (used for actual authorization decisions).
    """
    if not RIGHTS_AVAILABLE:
        return []
    return [_reshape_one(r) for r in list_rights_for_resource_type("odoo_model")]


def create_right(
    profile_id: str,
    model: str,
    *,
    fields: list[str],
    label: str = "",
    id: str | None = None,
    create: bool = False,
    read: bool = True,
    update: bool = False,
    delete: bool = False,
    require_confirmation: bool = False,
    confirm_create: bool = False,
    confirm_read: bool = False,
    confirm_update: bool = False,
    confirm_delete: bool = False,
) -> dict[str, Any]:
    """Create/update an AccessRight for this (profile, model), bound to the
    "everyone" role — mirrors the old OdooRight semantics (no per-identity
    scoping existed before rights-plugin, so every OdooRight-shaped write
    from odoo-plugin's own CLI/dashboard stays bound to "everyone").

    Unlike the read helpers above, this **raises** (ConfigurationError) when
    rights-plugin is unavailable rather than silently no-op'ing — a write
    that appears to succeed but didn't would be a much worse failure mode
    than a loud error at the call site (dashboard/CLI already surface
    ConnectorError subclasses as a clear message to the operator).
    """
    if not RIGHTS_AVAILABLE:
        raise ConfigurationError(
            "rights-plugin is not installed/enabled — cannot save this right",
            {"profile_id": profile_id, "odoo_model": model},
        )
    right = _create_right_api(
        roles=[ROLE_EVERYONE], resource_type="odoo_model", resource_id=f"{profile_id}:{model}",
        fields=fields, label=label, id=id,
        create=create, read=read, update=update, delete=delete,
        require_confirmation=require_confirmation,
        confirm_create=confirm_create, confirm_read=confirm_read,
        confirm_update=confirm_update, confirm_delete=confirm_delete,
    )
    return _reshape_one(right)


def delete_right(right_id: str) -> bool:
    """Delete an AccessRight by id. Returns False (not an error) when
    rights-plugin is unavailable — deleting something that can't be reached
    is indistinguishable from it already being gone, from the caller's
    point of view."""
    if not RIGHTS_AVAILABLE:
        return False
    return _delete_right_api(right_id)
