"""AI-facing Odoo executor.

Provides bounded CRUD access to Odoo. All operations are gated by rights
resolved through the ``rights`` plugin (see ``rights_bridge.py``) — a
generic ``(role, resource_type="odoo_model", resource_id=f"{profile_id}:
{model}", field)`` deny-by-default check, not a model owned by this plugin
(see ``.agents/DECISIONS.md``, "rights-plugin: vendoring vs cross-plugin
import"). Secrets (passwords) are resolved automatically from the keyring.

Flow for each call:
  1. Load OdooProfile from data_manager (resolves password from keyring).
  2. Build OdooClient.
  3. For each requested field, call rights_bridge.check_field() with the
     caller's roles (resolved once per tool call — see tools.py/__init__.py).
  4. Only allowed fields are forwarded to OdooClient.
  5. If any allowed field requires confirmation and confirmed=False,
     raise ConfirmationRequiredError — the tool layer re-raises this as a
     CONFIRMATION_REQUIRED response; the AI re-calls with confirmed=true.
     In practice this is pre-empted by the plugin's pre_tool_call hook
     (see __init__.py), which escalates to Hermes's human-approval gate
     before the handler even runs — this check is defense-in-depth.
"""

from __future__ import annotations

import logging
from typing import Any

from w_main.errors_manager.errors import (
    AuthorizationError,
    ConfirmationRequiredError,
    NotFoundError,
    ValidationError,
)

from . import rights_bridge
from .odoo_client import OdooClient
from .odoo_html import normalize_html_values
from .odoo_profile import get_odoo_profile_or_none

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_client(profile_id: str) -> tuple[OdooClient, Any]:
    """Load profile, validate it, and return (OdooClient, profile)."""
    profile = get_odoo_profile_or_none(profile_id)
    if profile is None:
        raise NotFoundError(
            f"Connection profile '{profile_id}' not found",
            {"profile_id": profile_id},
        )
    if not profile.enabled:
        raise AuthorizationError(
            f"Connection profile '{profile_id}' is disabled",
            {"profile_id": profile_id},
        )
    client = OdooClient(
        url=profile.base_url,
        port=profile.port,
        database=profile.database,
        login=profile.login,
        password=profile.password,
    )
    return client, profile


def _check_field(
    profile_id: str,
    model: str,
    field: str,
    operation: str,
    roles: list[str],
) -> tuple[bool, bool]:
    """Return (allowed, require_confirmation) for a field/operation pair.

    Returns (False, False) when no right of these roles covers the field —
    deny by default. Delegates to rights_bridge (rights-plugin); never
    raises (unlike the old get_right_manager_for()-based check).
    """
    return rights_bridge.check_field(profile_id, model, field, operation, roles)


def _html_field_names(model: str, field_names: list[str], client: OdooClient) -> set[str]:
    """Return the subset of *field_names* that are ``html``-type on *model*.

    Best-effort: a schema lookup failure must not block the write, so this
    swallows errors and normalizes nothing rather than raising.
    """
    try:
        schema = client.get_model_schema(model)
    except Exception:
        return set()
    return {name for name in field_names if schema.get(name, {}).get("type") == "html"}


def _filter_fields(
    profile_id: str,
    model: str,
    fields: list[str],
    operation: str,
    roles: list[str],
) -> tuple[list[str], list[str], bool]:
    """Split fields into (allowed, denied, any_requires_confirmation)."""
    allowed, denied = [], []
    needs_confirm = False
    for field in fields:
        ok, confirm = _check_field(profile_id, model, field, operation, roles)
        if ok:
            allowed.append(field)
            if confirm:
                needs_confirm = True
        else:
            denied.append(field)
    return allowed, denied, needs_confirm


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class OdooAIExecutor:
    """Coordinates right checks and OdooClient calls for AI tool requests."""

    def execute(
        self, action: str, model: str, payload: dict[str, Any], *, roles: list[str] | None = None
    ) -> dict[str, Any]:
        profile_id: str = payload.get("profile_id", "")
        if not profile_id:
            raise ValidationError("payload.profile_id is required")

        if roles is None:
            # Every real call site (tools.py, __init__.py's pre_tool_call)
            # resolves roles from the caller's identity and passes them
            # explicitly — reaching this fallback means a caller forgot to,
            # which would silently under-authorize with just "everyone".
            # Log loudly rather than fail silently.
            logger.warning(
                "OdooAIExecutor.execute() called without roles — falling back to "
                "[rights_bridge.ROLE_EVERYONE]. This should not happen outside tests."
            )
            roles = [rights_bridge.ROLE_EVERYONE]

        if action == "odoo_list_models":
            client, _ = _build_client(profile_id)
            return self._list_models(client)

        if action == "odoo_list_fields":
            if not model:
                raise ValidationError("model is required for odoo_list_fields")
            client, _ = _build_client(profile_id)
            return self._list_fields(model, client)

        if action == "odoo_list_allowed_models":
            return self._list_allowed_models(profile_id, roles)

        if action == "odoo_list_allowed_fields":
            if not model:
                raise ValidationError("model is required for odoo_list_allowed_fields")
            client, _ = _build_client(profile_id)
            return self._list_allowed_fields(model, profile_id, roles, client)

        if not model:
            raise ValidationError("model is required")

        client, _ = _build_client(profile_id)

        if action == "odoo_read":
            return self._read(model, payload, profile_id, roles, client)
        if action == "odoo_create":
            return self._create(model, payload, profile_id, roles, client)
        if action in ("odoo_update", "odoo_write"):
            return self._update(model, payload, profile_id, roles, client)
        if action == "odoo_delete":
            return self._delete(model, payload, profile_id, roles, client)

        raise ValidationError(f"Unknown action '{action}'", {"action": action})

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def _read(
        self,
        model: str,
        payload: dict[str, Any],
        profile_id: str,
        roles: list[str],
        client: OdooClient,
    ) -> dict[str, Any]:
        requested = payload.get("fields") or ["id", "name"]
        domain = payload.get("domain") or []
        limit = int(payload.get("limit") or 25)
        confirmed: bool = bool(payload.get("confirmed", False))

        allowed, denied, needs_confirm = _filter_fields(profile_id, model, requested, "read", roles)

        if not allowed:
            raise AuthorizationError(
                "No readable fields allowed for this profile/model combination",
                {"model": model, "profile_id": profile_id, "denied_fields": denied},
            )
        if needs_confirm and not confirmed:
            raise ConfirmationRequiredError(
                "Read requires explicit confirmation",
                {"model": model, "profile_id": profile_id, "allowed_fields": allowed},
            )

        records = client.get(model, domain, allowed, limit)
        return {
            "ok": True,
            "records": records,
            "count": len(records),
            "allowed_fields": allowed,
            "denied_fields": denied,
        }

    def _create(
        self,
        model: str,
        payload: dict[str, Any],
        profile_id: str,
        roles: list[str],
        client: OdooClient,
    ) -> dict[str, Any]:
        values: dict[str, Any] = payload.get("values") or {}
        confirmed: bool = bool(payload.get("confirmed", False))

        allowed_values = {}
        denied_fields = []
        needs_confirm = False

        for field, value in values.items():
            ok, confirm = _check_field(profile_id, model, field, "create", roles)
            if ok:
                allowed_values[field] = value
                if confirm:
                    needs_confirm = True
            else:
                denied_fields.append(field)

        if not allowed_values:
            raise AuthorizationError(
                "No creatable fields allowed for this profile/model combination",
                {"model": model, "profile_id": profile_id, "denied_fields": denied_fields},
            )
        if needs_confirm and not confirmed:
            raise ConfirmationRequiredError(
                "Create requires explicit confirmation",
                {
                    "model": model,
                    "profile_id": profile_id,
                    "allowed_fields": list(allowed_values.keys()),
                },
            )

        html_fields = _html_field_names(model, list(allowed_values.keys()), client)
        allowed_values = normalize_html_values(allowed_values, html_fields)

        record_id = client.post(model, allowed_values)
        return {
            "ok": True,
            "record_id": record_id,
            "allowed_fields": list(allowed_values.keys()),
            "denied_fields": denied_fields,
        }

    def _update(
        self,
        model: str,
        payload: dict[str, Any],
        profile_id: str,
        roles: list[str],
        client: OdooClient,
    ) -> dict[str, Any]:
        record_ids = [payload["id"]] if "id" in payload else list(payload.get("ids", []))
        values: dict[str, Any] = payload.get("values") or {}
        confirmed: bool = bool(payload.get("confirmed", False))

        if not record_ids:
            raise ValidationError("payload.id or payload.ids is required for update")

        allowed_values = {}
        denied_fields = []
        needs_confirm = False

        for field, value in values.items():
            ok, confirm = _check_field(profile_id, model, field, "update", roles)
            if ok:
                allowed_values[field] = value
                if confirm:
                    needs_confirm = True
            else:
                denied_fields.append(field)

        if not allowed_values:
            raise AuthorizationError(
                "No updatable fields allowed for this profile/model combination",
                {"model": model, "profile_id": profile_id, "denied_fields": denied_fields},
            )
        if needs_confirm and not confirmed:
            raise ConfirmationRequiredError(
                "Update requires explicit confirmation",
                {"model": model, "profile_id": profile_id, "ids": record_ids},
            )

        html_fields = _html_field_names(model, list(allowed_values.keys()), client)
        allowed_values = normalize_html_values(allowed_values, html_fields)

        success = client.put(model, record_ids, allowed_values)
        return {
            "ok": True,
            "success": success,
            "updated_ids": record_ids,
            "allowed_fields": list(allowed_values.keys()),
            "denied_fields": denied_fields,
        }

    def _delete(
        self,
        model: str,
        payload: dict[str, Any],
        profile_id: str,
        roles: list[str],
        client: OdooClient,
    ) -> dict[str, Any]:
        record_ids = [payload["id"]] if "id" in payload else list(payload.get("ids", []))
        confirmed: bool = bool(payload.get("confirmed", False))

        if not record_ids:
            raise ValidationError("payload.id or payload.ids is required for delete")

        # Delete is checked against the wildcard field "*"
        allowed, needs_confirm = _check_field(profile_id, model, "*", "delete", roles)
        if not allowed:
            raise AuthorizationError(
                "Delete not allowed for this profile/model combination",
                {"model": model, "profile_id": profile_id},
            )
        if needs_confirm and not confirmed:
            raise ConfirmationRequiredError(
                "Delete requires explicit confirmation",
                {"model": model, "profile_id": profile_id, "ids": record_ids},
            )

        success = client.delete(model, record_ids)
        return {
            "ok": True,
            "success": success,
            "deleted_ids": record_ids,
        }

    # ------------------------------------------------------------------
    # Meta operations (no right check — informational only)
    # ------------------------------------------------------------------

    def _list_models(self, client: OdooClient) -> dict[str, Any]:
        ir_model = client.get_model("ir.model")
        models = ir_model.search_read([], ["model", "name"], order="model asc")
        return {
            "ok": True,
            "models": [{"model": m["model"], "name": m.get("name", "")} for m in models],
            "count": len(models),
        }

    def _list_fields(self, model: str, client: OdooClient) -> dict[str, Any]:
        schema = client.get_model_schema(model)
        fields = [
            {
                "name": name,
                "label": meta.get("string", name),
                "type": meta.get("type", "unknown"),
                "required": meta.get("required", False),
                "readonly": meta.get("readonly", False),
            }
            for name, meta in schema.items()
        ]
        return {"ok": True, "model": model, "fields": fields, "count": len(fields)}

    def _list_allowed_models(self, profile_id: str, roles: list[str]) -> dict[str, Any]:
        """Return only models these roles have rights on — no Odoo connection needed.

        Note: scoped to the calling identity's roles (via rights_bridge),
        not "everything this profile is configured for" like the old
        OdooRight-based version — an intended consequence of adding roles,
        see .agents/CHANGELOG_AGENT.md for the explicit callout.
        """
        pairs = rights_bridge.rights_for_profile(profile_id, roles)

        models: dict[str, dict] = {}
        for m, right in pairs:
            if m not in models:
                models[m] = {"read": False, "create": False, "update": False, "delete": False}
            if right["read"]:
                models[m]["read"] = True
            if right["create"]:
                models[m]["create"] = True
            if right["update"]:
                models[m]["update"] = True
            if right["delete"]:
                models[m]["delete"] = True

        result = [{"model": m, **ops} for m, ops in sorted(models.items())]
        return {"ok": True, "models": result, "count": len(result)}

    def _list_allowed_fields(
        self, model: str, profile_id: str, roles: list[str], client: OdooClient
    ) -> dict[str, Any]:
        """Return fields of a model filtered by these roles' rights, with Odoo schema metadata.

        Note: scoped to the calling identity's roles, same caveat as
        _list_allowed_models above.
        """
        rights = rights_bridge.rights_for_profile_and_model(profile_id, model, roles)

        if not rights:
            return {
                "ok": True,
                "model": model,
                "fields": [],
                "count": 0,
                "note": f"No rights configured for model '{model}' with profile '{profile_id}'",
            }

        schema = client.get_model_schema(model)

        # Collect allowed field names across all rights for this profile+model
        has_wildcard = any("*" in r["fields"] for r in rights)
        if has_wildcard:
            allowed_names = set(schema.keys())
        else:
            allowed_names = {f for r in rights for f in r["fields"] if f in schema}

        # Aggregate CRUD ops per field
        def _ops_for(field_name: str) -> dict:
            ops = {"read": False, "create": False, "update": False, "delete": False}
            for r in rights:
                if rights_bridge.applies_to_field(r, field_name):
                    if r["read"]:
                        ops["read"] = True
                    if r["create"]:
                        ops["create"] = True
                    if r["update"]:
                        ops["update"] = True
                    if r["delete"]:
                        ops["delete"] = True
            return ops

        fields = [
            {
                "name": name,
                "label": schema[name].get("string", name),
                "type": schema[name].get("type", "unknown"),
                "required": schema[name].get("required", False),
                "readonly": schema[name].get("readonly", False),
                **_ops_for(name),
            }
            for name in sorted(allowed_names)
        ]
        return {"ok": True, "model": model, "fields": fields, "count": len(fields)}
