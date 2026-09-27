"""Config executor — CRUD for OdooProfile, plus live Odoo meta queries.

Right *management* (create/list/delete) is generalized through the
``rights`` plugin (``hermes rights right add/list/rm --resource-type
odoo_model`` is the generic CLI equivalent) — see ``.agents/DECISIONS.md``,
"rights-plugin: vendoring vs cross-plugin import". This executor's own
``save_right``/``delete_right`` actions still exist (backing the
odoo-plugin *dashboard*'s Rights section, which keeps the richer live
Odoo-model-dropdown UX — see ``.agents/DECISIONS.md``, the dashboard
extension entry) but delegate to ``rights_bridge`` instead of owning the
data themselves; every write lands as a generic ``AccessRight`` bound to
role "everyone", identically to what ``hermes rights right add
--resource-type odoo_model ...`` would produce. The plain CLI
(``odoo-plugin/cli.py``'s ``hermes odoo right``) stays read-only —
``hermes rights right add/rm`` is the only *CLI* path for writes, this
executor's write actions are dashboard-only.

``list_rights`` reshapes rights-plugin's generic ``AccessRight`` rows
(``resource_type="odoo_model"``) back into the ``OdooRight``-shaped dicts
the ``odoo_list_rights``/``odoo_config_validate`` agent tools' schemas
already document, so their output contract doesn't change even though the
underlying storage did.
"""

from __future__ import annotations

from typing import Any

from w_main.errors_manager.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)

from . import rights_bridge
from .odoo_client import OdooClient
from .odoo_profile import (
    OdooProfile,
    create_odoo_profile,
    delete_odoo_profile,
    get_odoo_profile_or_none,
    get_odoo_profiles,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_client(profile_id: str) -> OdooClient:
    profile = get_odoo_profile_or_none(profile_id)
    if profile is None:
        raise NotFoundError(f"Profile '{profile_id}' not found", {"profile_id": profile_id})
    if not profile.enabled:
        raise AuthorizationError(f"Profile '{profile_id}' is disabled", {"profile_id": profile_id})
    return OdooClient(
        url=profile.base_url,
        port=profile.port,
        database=profile.database,
        login=profile.login,
        password=profile.password,
    )


def _profile_to_dict(p: OdooProfile) -> dict[str, Any]:
    return {
        "id": p.id,
        "label": p.label,
        "base_url": p.base_url,
        "database": p.database,
        "login": p.login,
        "enabled": p.enabled,
        "port": p.port,
        # password intentionally omitted (secret)
    }


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class OdooConfigExecutor:
    """Handles config operations: profile & right CRUD, live Odoo meta queries."""

    def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Profiles
        if action == "list_profiles":
            return self._list_profiles()
        if action == "get_profile":
            return self._get_profile(payload)
        if action == "save_profile":
            return self._save_profile(payload)
        if action == "delete_profile":
            return self._delete_profile(payload)

        # Rights — dashboard-only writes, delegated to rights_bridge (see
        # module docstring). The plain `hermes odoo right` CLI stays
        # read-only; `hermes rights right add/rm` is the CLI write path.
        if action == "list_rights":
            return self._list_rights(payload)
        if action == "save_right":
            return self._save_right(payload)
        if action == "delete_right":
            return self._delete_right(payload)

        # Live Odoo meta (requires an active profile connection)
        if action == "list_odoo_models":
            return self._list_odoo_models(payload)
        if action == "list_odoo_fields":
            return self._list_odoo_fields(payload)

        raise ValidationError(f"Unknown action '{action}'", {"action": action})

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def _list_profiles(self) -> dict[str, Any]:
        profiles = get_odoo_profiles()
        return {
            "ok": True,
            "profiles": [_profile_to_dict(p) for p in profiles],
            "count": len(profiles),
        }

    def _get_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = payload.get("id") or payload.get("profile_id")
        if not profile_id:
            raise ValidationError("payload.id is required")
        profile = get_odoo_profile_or_none(str(profile_id))
        if profile is None:
            raise NotFoundError(f"Profile '{profile_id}' not found", {"id": profile_id})
        return {"ok": True, "profile": _profile_to_dict(profile)}

    def _save_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = payload.get("id")
        if not profile_id:
            raise ValidationError("payload.id is required")
        if not payload.get("base_url") or not payload.get("database") or not payload.get("login"):
            raise ValidationError("base_url, database and login are required")

        profile = create_odoo_profile(
            id=str(profile_id),
            label=str(payload.get("label") or profile_id),
            base_url=str(payload["base_url"]).strip(),
            database=str(payload["database"]).strip(),
            login=str(payload["login"]).strip(),
            password=str(payload.get("password") or ""),
            enabled=bool(payload.get("enabled", True)),
            port=int(payload.get("port") or 443),
        )
        return {"ok": True, "profile": _profile_to_dict(profile)}

    def _delete_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = payload.get("id") or payload.get("profile_id")
        if not profile_id:
            raise ValidationError("payload.id is required")
        deleted = delete_odoo_profile(str(profile_id))
        return {"ok": True, "deleted": deleted}

    # ------------------------------------------------------------------
    # Rights (dashboard-only writes — see module docstring)
    # ------------------------------------------------------------------

    def _list_rights(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = payload.get("profile_id")
        rights = rights_bridge.all_odoo_rights()
        if profile_id:
            rights = [r for r in rights if r["profile_id"] == str(profile_id)]
        return {
            "ok": True,
            "rights": rights,
            "count": len(rights),
        }

    def _save_right(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload.get("profile_id") or not payload.get("odoo_model"):
            raise ValidationError("profile_id and odoo_model are required")

        # fields accepts a list or a comma-separated string
        raw_fields = payload.get("fields", ["*"])
        if isinstance(raw_fields, str):
            fields: list[str] = [f.strip() for f in raw_fields.split(",") if f.strip()]
        else:
            fields = list(raw_fields)
        if not fields:
            fields = ["*"]

        right = rights_bridge.create_right(
            profile_id=str(payload["profile_id"]),
            model=str(payload["odoo_model"]).strip(),
            fields=fields,
            label=str(payload.get("label") or ""),
            id=payload.get("id") or None,
            create=bool(payload.get("create", False)),
            read=bool(payload.get("read", True)),
            update=bool(payload.get("update", False)),
            delete=bool(payload.get("delete", False)),
            require_confirmation=bool(payload.get("require_confirmation", False)),
            confirm_create=bool(payload.get("confirm_create", False)),
            confirm_read=bool(payload.get("confirm_read", False)),
            confirm_update=bool(payload.get("confirm_update", False)),
            confirm_delete=bool(payload.get("confirm_delete", False)),
        )
        return {"ok": True, "right": right}

    def _delete_right(self, payload: dict[str, Any]) -> dict[str, Any]:
        right_id = payload.get("id")
        if not right_id:
            raise ValidationError("payload.id is required")
        deleted = rights_bridge.delete_right(str(right_id))
        return {"ok": True, "deleted": deleted}

    # ------------------------------------------------------------------
    # Live Odoo meta
    # ------------------------------------------------------------------

    def _list_odoo_models(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = payload.get("profile_id")
        if not profile_id:
            raise ValidationError("payload.profile_id is required")
        client = _build_client(str(profile_id))
        ir_model = client.get_model("ir.model")
        models = ir_model.search_read([], ["model", "name"], order="model asc")
        return {
            "ok": True,
            "models": [{"model": m["model"], "name": m.get("name", "")} for m in models],
            "count": len(models),
        }

    def _list_odoo_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = payload.get("profile_id")
        model = payload.get("model")
        if not profile_id or not model:
            raise ValidationError("payload.profile_id and payload.model are required")
        client = _build_client(str(profile_id))
        schema = client.get_model_schema(str(model))
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
