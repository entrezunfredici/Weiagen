"""Config executor — CRUD for RoleBinding/AccessRight, plus check/whoami introspection.

Mirrors odoo-plugin's ``w_odoo/odoo_cli_for_config.py::OdooConfigExecutor``
pattern (``execute(action, payload) -> dict``, ``ConnectorError`` subclasses
for structured failures) so the CLI layer (``cli.py``) stays a thin argparse
shim, same as ``odoo-plugin/cli.py``.
"""

from __future__ import annotations

import secrets
from typing import Any

from rights_w_main.errors_manager.errors import ValidationError

import directory
import models
import platforms
import token_signer
import tools_catalog
from engine import check_right
from identity import resolve_identity
from migrate_odoo_rights import migrate_odoo_rights

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _role_binding_to_dict(b: models.RoleBinding) -> dict[str, Any]:
    return {
        "id": b.id,
        "platform": b.platform,
        "external_user_id": b.external_user_id,
        "roles": b.roles,
        "label": b.label,
    }


def _role_to_dict(r: models.Role) -> dict[str, Any]:
    return {"id": r.id, "label": r.label, "description": r.description}


def _access_right_to_dict(r: models.AccessRight) -> dict[str, Any]:
    return {
        "id": r.id,
        "label": r.label,
        "roles": r.roles,
        "resource_type": r.resource_type,
        "resource_id": r.resource_id,
        "fields": r.fields,
        "create": r.create,
        "read": r.read,
        "update": r.update,
        "delete": r.delete,
        "execute": r.execute,
        "require_confirmation": r.require_confirmation,
        "confirm_create": r.confirm_create,
        "confirm_read": r.confirm_read,
        "confirm_update": r.confirm_update,
        "confirm_delete": r.confirm_delete,
        "confirm_execute": r.confirm_execute,
    }


def _parse_fields(raw) -> list[str]:
    """Accept a list or a comma-separated string — same convention as
    odoo-plugin's _save_right()."""
    if raw is None:
        return ["*"]
    if isinstance(raw, str):
        fields = [f.strip() for f in raw.split(",") if f.strip()]
    else:
        fields = list(raw)
    return fields or ["*"]


def _parse_roles(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        roles = [r.strip() for r in raw.split(",") if r.strip()]
    else:
        roles = list(raw)
    return roles


def _mask_secret(secret: str) -> str:
    """Show only the last 4 characters — enough for an operator to recognize
    which secret they're looking at without the full value round-tripping
    through every list/get response. Full value is only ever returned once,
    right after create/update (see _save_mcp_signing_key) or via the
    explicit "reveal" action — never through the default listing."""
    if not secret:
        return ""
    if len(secret) <= 4:
        return "•" * len(secret)
    return "•" * (len(secret) - 4) + secret[-4:]


def _mcp_signing_key_to_dict(k: models.McpSigningKey, *, reveal: bool = False) -> dict[str, Any]:
    return {
        "id": k.id,
        "label": k.label,
        "alg": k.alg,
        "active": k.active,
        "created_at": k.created_at,
        "secret": k.secret if reveal else _mask_secret(k.secret),
    }


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class RightsConfigExecutor:
    """Handles config operations: role-binding & access-right CRUD, check/whoami introspection."""

    def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Role bindings
        if action == "bind_role":
            return self._bind_role(payload)
        if action == "unbind_role":
            return self._unbind_role(payload)
        if action == "list_role_bindings":
            return self._list_role_bindings(payload)

        # Access rights
        if action == "save_right":
            return self._save_right(payload)
        if action == "list_rights":
            return self._list_rights(payload)
        if action == "delete_right":
            return self._delete_right(payload)

        # Introspection
        if action == "check_right":
            return self._check_right(payload)
        if action == "whoami":
            return self._whoami(payload)

        # Migration
        if action == "migrate_odoo_rights":
            return self._migrate_odoo_rights(payload)

        # Identity directory (Slack member pick-list, see directory.py)
        if action == "list_directory":
            return self._list_directory(payload)
        if action == "sync_directory":
            return self._sync_directory(payload)

        # Connected platforms (see platforms.py)
        if action == "list_platforms":
            return self._list_platforms(payload)

        # Role catalog (see models.Role) — distinct names from bind_role/
        # save_right on purpose, no ambiguity with either CRUD surface.
        if action == "list_roles":
            return self._list_roles(payload)
        if action == "save_role":
            return self._save_role(payload)
        if action == "delete_role":
            return self._delete_role(payload)

        # Hermes tool catalog (see tools_catalog.py) — read-only, backs the
        # dashboard's tool picker for hermes_tool rights.
        if action == "list_hermes_tools":
            return self._list_hermes_tools(payload)

        # MCP signing keys (see models.McpSigningKey / token_signer.py) —
        # one key per EXTERNAL MCP microservice, distinct from every CRUD
        # surface above.
        if action == "list_mcp_signing_keys":
            return self._list_mcp_signing_keys(payload)
        if action == "save_mcp_signing_key":
            return self._save_mcp_signing_key(payload)
        if action == "delete_mcp_signing_key":
            return self._delete_mcp_signing_key(payload)
        if action == "reveal_mcp_signing_key":
            return self._reveal_mcp_signing_key(payload)

        raise ValidationError(f"Unknown action '{action}'", {"action": action})

    # ------------------------------------------------------------------
    # Role bindings
    # ------------------------------------------------------------------

    def _bind_role(self, payload: dict[str, Any]) -> dict[str, Any]:
        platform = payload.get("platform")
        user_id = payload.get("external_user_id") or payload.get("user_id") or payload.get("user")
        if not platform or not user_id:
            raise ValidationError("platform and user_id are required")
        binding = models.bind_role(
            str(platform), str(user_id), _parse_roles(payload.get("roles")),
            label=str(payload.get("label") or ""),
        )
        return {"ok": True, "role_binding": _role_binding_to_dict(binding)}

    def _unbind_role(self, payload: dict[str, Any]) -> dict[str, Any]:
        platform = payload.get("platform")
        user_id = payload.get("external_user_id") or payload.get("user_id") or payload.get("user")
        if not platform or not user_id:
            raise ValidationError("platform and user_id are required")
        deleted = models.unbind_role(str(platform), str(user_id))
        return {"ok": True, "deleted": deleted}

    def _list_role_bindings(self, payload: dict[str, Any]) -> dict[str, Any]:
        platform = payload.get("platform")
        bindings = models.role_bindings_for_platform(str(platform)) if platform else models.list_role_bindings()
        user_id = payload.get("external_user_id") or payload.get("user_id") or payload.get("user")
        if user_id:
            bindings = [b for b in bindings if b.external_user_id == str(user_id)]
        return {
            "ok": True,
            "role_bindings": [_role_binding_to_dict(b) for b in bindings],
            "count": len(bindings),
        }

    # ------------------------------------------------------------------
    # Access rights
    # ------------------------------------------------------------------

    def _save_right(self, payload: dict[str, Any]) -> dict[str, Any]:
        roles = _parse_roles(payload.get("roles"))
        if not roles or not payload.get("resource_type") or not payload.get("resource_id"):
            raise ValidationError("roles, resource_type and resource_id are required")

        right = models.create_access_right(
            roles=roles,
            resource_type=str(payload["resource_type"]),
            resource_id=str(payload["resource_id"]),
            fields=_parse_fields(payload.get("fields")),
            label=str(payload.get("label") or ""),
            id=payload.get("id") or None,
            create=bool(payload.get("create", False)),
            read=bool(payload.get("read", True)),
            update=bool(payload.get("update", False)),
            delete=bool(payload.get("delete", False)),
            execute=bool(payload.get("execute", False)),
            require_confirmation=bool(payload.get("require_confirmation", False)),
            confirm_create=bool(payload.get("confirm_create", False)),
            confirm_read=bool(payload.get("confirm_read", False)),
            confirm_update=bool(payload.get("confirm_update", False)),
            confirm_delete=bool(payload.get("confirm_delete", False)),
            confirm_execute=bool(payload.get("confirm_execute", False)),
        )
        return {"ok": True, "right": _access_right_to_dict(right)}

    def _list_rights(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = payload.get("role")
        resource_type = payload.get("resource_type")
        resource_id = payload.get("resource_id")

        rights = models.list_access_rights()
        if role:
            # Filter semantics: "rights that include this role" — a right
            # can now be bound to several, so this is a membership check,
            # not equality.
            rights = [r for r in rights if r.applies_to_role(str(role))]
        if resource_type:
            rights = [r for r in rights if r.resource_type == str(resource_type)]
        if resource_id:
            rights = [r for r in rights if r.resource_id == str(resource_id)]

        return {
            "ok": True,
            "rights": [_access_right_to_dict(r) for r in rights],
            "count": len(rights),
        }

    def _delete_right(self, payload: dict[str, Any]) -> dict[str, Any]:
        right_id = payload.get("id")
        if not right_id:
            raise ValidationError("payload.id is required")
        deleted = models.delete_access_right(str(right_id))
        return {"ok": True, "deleted": deleted}

    # ------------------------------------------------------------------
    # Introspection (debug — no side effects)
    # ------------------------------------------------------------------

    def _check_right(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload.get("resource_type") or not payload.get("resource_id") or not payload.get("operation"):
            raise ValidationError("resource_type, resource_id and operation are required")
        roles = _parse_roles(payload.get("roles")) or ["everyone"]
        decision = check_right(
            roles=roles,
            resource_type=str(payload["resource_type"]),
            resource_id=str(payload["resource_id"]),
            operation=str(payload["operation"]),
            field=payload.get("field"),
        )
        confirmed = bool(payload.get("confirmed", False))
        return {
            "ok": True,
            "allowed": decision.allowed,
            "require_confirmation": decision.require_confirmation,
            "is_ready": decision.is_ready(confirmed=confirmed),
            "reason": decision.reason,
        }

    def _whoami(self, payload: dict[str, Any]) -> dict[str, Any]:
        platform = payload.get("platform")
        user_id = payload.get("external_user_id") or payload.get("user_id") or payload.get("user")
        session_id = payload.get("session_id")
        if not session_id and not (platform and user_id):
            raise ValidationError("either session_id, or platform+user_id, are required")
        identity = resolve_identity(
            session_id=session_id,
            platform=str(platform) if platform else None,
            external_user_id=str(user_id) if user_id else None,
        )
        return {
            "ok": True,
            "platform": identity.platform,
            "external_user_id": identity.external_user_id,
            "roles": identity.roles,
        }

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _migrate_odoo_rights(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = payload.get("path")
        if not path:
            raise ValidationError("payload.path is required")
        dry_run = bool(payload.get("dry_run", False))
        migrated = migrate_odoo_rights(source_path=str(path), dry_run=dry_run)
        return {"ok": True, "dry_run": dry_run, "migrated": migrated, "count": len(migrated)}

    # ------------------------------------------------------------------
    # Identity directory (read-only pick-list, see directory.py)
    # ------------------------------------------------------------------

    def _list_directory(self, payload: dict[str, Any]) -> dict[str, Any]:
        platform = str(payload.get("platform") or "slack")
        # Best-effort — never raises. A stale/missing token must not make
        # the dashboard's role-binding tab unusable, only fall back to
        # whatever was last cached (possibly nothing).
        directory.ensure_fresh(platform)
        entries = directory.list_cached(platform)
        return {
            "ok": True,
            "platform": platform,
            "directory": entries,
            "count": len(entries),
            "synced_at": models.directory_last_synced_at(platform),
        }

    def _sync_directory(self, payload: dict[str, Any]) -> dict[str, Any]:
        platform = str(payload.get("platform") or "slack")
        entries = directory.sync_now(platform)  # raises on failure — explicit action, loud on purpose
        return {"ok": True, "platform": platform, "directory": entries, "count": len(entries)}

    # ------------------------------------------------------------------
    # Connected platforms (read-only, see platforms.py)
    # ------------------------------------------------------------------

    def _list_platforms(self, payload: dict[str, Any]) -> dict[str, Any]:
        include_unconfigured = bool(payload.get("include_unconfigured", False))
        result = platforms.all_platforms() if include_unconfigured else platforms.connected_platforms()
        return {"ok": True, "platforms": result, "count": len(result)}

    # ------------------------------------------------------------------
    # Role catalog (see models.Role)
    # ------------------------------------------------------------------

    def _list_roles(self, payload: dict[str, Any]) -> dict[str, Any]:
        roles = models.list_roles()
        return {"ok": True, "roles": [_role_to_dict(r) for r in roles], "count": len(roles)}

    def _save_role(self, payload: dict[str, Any]) -> dict[str, Any]:
        role_id = payload.get("id")
        if not role_id:
            raise ValidationError("payload.id is required")
        role = models.create_role(
            str(role_id),
            label=str(payload.get("label") or ""),
            description=str(payload.get("description") or ""),
        )
        return {"ok": True, "role": _role_to_dict(role)}

    def _delete_role(self, payload: dict[str, Any]) -> dict[str, Any]:
        role_id = payload.get("id")
        if not role_id:
            raise ValidationError("payload.id is required")
        role_id = str(role_id)
        # Informational only — roles are opaque strings, not a hard foreign
        # key, so a still-referenced role is deletable on purpose (just
        # surfaced here so an operator doesn't do it by accident).
        still_referenced = {
            "role_bindings": sum(1 for b in models.list_role_bindings() if role_id in b.roles),
            "rights": sum(1 for r in models.list_access_rights() if r.applies_to_role(role_id)),
        }
        deleted = models.delete_role(role_id)
        return {"ok": True, "deleted": deleted, "still_referenced_by": still_referenced}

    # ------------------------------------------------------------------
    # Hermes tool catalog (read-only, see tools_catalog.py)
    # ------------------------------------------------------------------

    def _list_hermes_tools(self, payload: dict[str, Any]) -> dict[str, Any]:
        tools = tools_catalog.list_hermes_tools()
        return {"ok": True, "tools": tools, "count": len(tools)}

    # ------------------------------------------------------------------
    # MCP signing keys (see models.McpSigningKey / token_signer.py)
    # ------------------------------------------------------------------

    def _list_mcp_signing_keys(self, payload: dict[str, Any]) -> dict[str, Any]:
        keys = models.list_mcp_signing_keys()
        return {
            "ok": True,
            "mcp_signing_keys": [_mcp_signing_key_to_dict(k) for k in keys],
            "count": len(keys),
            "supported_algs": list(token_signer.SUPPORTED_ALGS),
        }

    def _save_mcp_signing_key(self, payload: dict[str, Any]) -> dict[str, Any]:
        kid = payload.get("id")
        if not kid:
            raise ValidationError("payload.id (kid) is required")
        kid = str(kid)

        alg = str(payload.get("alg") or "HS256").upper()
        if alg not in token_signer.SUPPORTED_ALGS:
            raise ValidationError(
                f"Unsupported alg '{alg}' (supported: {', '.join(token_signer.SUPPORTED_ALGS)})",
                {"alg": alg, "supported": list(token_signer.SUPPORTED_ALGS)},
            )

        # A blank secret means "keep the existing one" on an edit (rotating
        # the secret is a deliberate, explicit action — typing a new value),
        # or "auto-generate one" the first time this kid is created, so an
        # operator never has to think up their own random string.
        submitted_secret = payload.get("secret")
        if submitted_secret:
            secret = str(submitted_secret)
        else:
            existing = models.get_mcp_signing_key_or_none(kid)
            secret = existing.secret if existing else secrets.token_urlsafe(32)

        key = models.create_mcp_signing_key(
            kid, secret,
            label=str(payload.get("label") or ""),
            alg=alg,
            active=bool(payload.get("active", True)),
        )
        # Revealed here on purpose — this response is the one moment an
        # operator can copy the full secret to share out-of-band with the
        # external MCP team (list/get responses mask it, see _mask_secret).
        return {"ok": True, "mcp_signing_key": _mcp_signing_key_to_dict(key, reveal=True)}

    def _delete_mcp_signing_key(self, payload: dict[str, Any]) -> dict[str, Any]:
        kid = payload.get("id")
        if not kid:
            raise ValidationError("payload.id is required")
        deleted = models.delete_mcp_signing_key(str(kid))
        return {"ok": True, "deleted": deleted}

    def _reveal_mcp_signing_key(self, payload: dict[str, Any]) -> dict[str, Any]:
        kid = payload.get("id")
        if not kid:
            raise ValidationError("payload.id is required")
        key = models.get_mcp_signing_key_or_none(str(kid))
        if key is None:
            raise ValidationError(f"No MCP signing key with id '{kid}'", {"id": kid})
        return {"ok": True, "mcp_signing_key": _mcp_signing_key_to_dict(key, reveal=True)}
