"""Dashboard backend routes for the rights plugin — role bindings + access rights CRUD.

Mounted by Hermes's dashboard web server at ``/api/plugins/rights`` (see
``hermes_cli/web_server.py::_mount_plugin_api_routes`` — same mechanism
already used by ``odoo-plugin/dashboard/plugin_api.py``, no auth code
needed here, the host's dashboard middleware already gates every
``/api/...`` request).

Runs in the **dashboard's own process**, separate from the gateway process
that loads ``../__init__.py`` (the agent-facing tool plugin + hooks).
Nothing set up there (sys.path, HERMES_HOME-derived data paths) carries
over here — this file repeats that bootstrap independently, same pattern as
``odoo-plugin/dashboard/plugin_api.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from hermes_constants import get_hermes_home  # noqa: E402

_DATA_DIR = get_hermes_home() / "rights-plugin-data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("RIGHTS_ROLE_BINDINGS_PATH", str(_DATA_DIR / "role-bindings.json"))
os.environ.setdefault("RIGHTS_ACCESS_RIGHTS_PATH", str(_DATA_DIR / "access-rights.json"))
os.environ.setdefault("RIGHTS_DIRECTORY_ENTRIES_PATH", str(_DATA_DIR / "directory-entries.json"))

from fastapi import APIRouter, HTTPException, Query  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from config_executor import RightsConfigExecutor  # noqa: E402
from rights_w_main.errors_manager.errors import ConnectorError  # noqa: E402

router = APIRouter()

_config = RightsConfigExecutor()

_STATUS_BY_CODE = {
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 400,
    "AUTHORIZATION_DENIED": 403,
    "CONFIRMATION_REQUIRED": 409,
    "CONFIGURATION_ERROR": 400,
}


def _handle(fn):
    try:
        return fn()
    except ConnectorError as exc:
        raise HTTPException(status_code=_STATUS_BY_CODE.get(exc.code, 500), detail=exc.message)


class RoleBindingBody(BaseModel):
    platform: str
    user: str
    roles: str = ""
    label: Optional[str] = ""


class DirectorySyncBody(BaseModel):
    platform: str = "slack"


class RoleBody(BaseModel):
    id: str
    label: Optional[str] = ""
    description: Optional[str] = ""


class McpSigningKeyBody(BaseModel):
    id: str
    label: Optional[str] = ""
    alg: str = "HS256"
    secret: Optional[str] = None  # omit to auto-generate (new key) or keep unchanged (edit)
    active: bool = True


class RightBody(BaseModel):
    id: Optional[str] = None
    roles: str  # comma-separated, same wire convention as RoleBindingBody.roles
    resource_type: str
    resource_id: str
    fields: str = "*"
    label: Optional[str] = ""
    create: bool = False
    read: bool = True
    update: bool = False
    delete: bool = False
    execute: bool = False
    require_confirmation: bool = False
    confirm_create: bool = False
    confirm_read: bool = False
    confirm_update: bool = False
    confirm_delete: bool = False
    confirm_execute: bool = False


# ---------------------------------------------------------------------------
# Role catalog (see ../models.Role) — backs both the "Roles" section and the
# tag pickers in the role-binding/right forms.
# ---------------------------------------------------------------------------

@router.get("/roles")
def list_roles():
    return _handle(lambda: _config.execute("list_roles", {}))


@router.post("/roles")
def save_role(payload: RoleBody):
    return _handle(lambda: _config.execute("save_role", payload.model_dump()))


@router.delete("/roles/{role_id}")
def delete_role(role_id: str):
    return _handle(lambda: _config.execute("delete_role", {"id": role_id}))


# ---------------------------------------------------------------------------
# Role bindings
# ---------------------------------------------------------------------------

@router.get("/role-bindings")
def list_role_bindings(platform: Optional[str] = Query(None), user: Optional[str] = Query(None)):
    return _handle(lambda: _config.execute("list_role_bindings", {"platform": platform, "user": user}))


@router.post("/role-bindings")
def bind_role(payload: RoleBindingBody):
    return _handle(lambda: _config.execute("bind_role", payload.model_dump()))


@router.delete("/role-bindings")
def unbind_role(platform: str = Query(...), user: str = Query(...)):
    # Query params, not a composite path id (f"{platform}:{user}") — avoids
    # any ambiguity around ':' in a URL path segment for identities that
    # might contain one themselves.
    return _handle(lambda: _config.execute("unbind_role", {"platform": platform, "user": user}))


# ---------------------------------------------------------------------------
# Access rights
# ---------------------------------------------------------------------------

@router.get("/rights")
def list_rights(
    role: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
):
    return _handle(lambda: _config.execute("list_rights", {
        "role": role, "resource_type": resource_type, "resource_id": resource_id,
    }))


@router.post("/rights")
def save_right(payload: RightBody):
    return _handle(lambda: _config.execute("save_right", payload.model_dump()))


@router.delete("/rights/{right_id}")
def delete_right(right_id: str):
    return _handle(lambda: _config.execute("delete_right", {"id": right_id}))


# ---------------------------------------------------------------------------
# Hermes tool catalog (see ../tools_catalog.py) — backs the tool picker in
# the RightForm's hermes_tool section.
# ---------------------------------------------------------------------------

@router.get("/hermes-tools")
def list_hermes_tools():
    return _handle(lambda: _config.execute("list_hermes_tools", {}))


# ---------------------------------------------------------------------------
# Identity directory (Slack member pick-list for the role-binding form —
# see ../directory.py)
# ---------------------------------------------------------------------------

@router.get("/directory")
def list_directory(platform: str = Query("slack")):
    # Best-effort lazy refresh happens inside — this never fails just
    # because Slack is momentarily unreachable, it serves whatever is
    # cached (possibly empty on a fresh install with no sync yet).
    return _handle(lambda: _config.execute("list_directory", {"platform": platform}))


@router.post("/directory/sync")
def sync_directory(payload: DirectorySyncBody):
    # Unlike GET /directory, this is the explicit "Refresh now" action —
    # failures (missing SLACK_BOT_TOKEN, bad scope, Slack outage) surface
    # as a real error to the dashboard on purpose.
    return _handle(lambda: _config.execute("sync_directory", {"platform": payload.platform}))


# ---------------------------------------------------------------------------
# Connected platforms (see ../platforms.py) — backs the role-binding form's
# platform picker
# ---------------------------------------------------------------------------

@router.get("/platforms")
def list_platforms(include_unconfigured: bool = Query(False)):
    return _handle(lambda: _config.execute("list_platforms", {"include_unconfigured": include_unconfigured}))


# ---------------------------------------------------------------------------
# MCP signing keys (see ../models.McpSigningKey / ../token_signer.py) — one
# key per EXTERNAL MCP microservice. GET/list responses mask the secret
# (last 4 chars only); the full value is only ever returned by POST (create/
# update) or the explicit "reveal" route.
# ---------------------------------------------------------------------------

@router.get("/mcp-signing-keys")
def list_mcp_signing_keys():
    return _handle(lambda: _config.execute("list_mcp_signing_keys", {}))


@router.post("/mcp-signing-keys")
def save_mcp_signing_key(payload: McpSigningKeyBody):
    return _handle(lambda: _config.execute("save_mcp_signing_key", payload.model_dump()))


@router.delete("/mcp-signing-keys/{kid}")
def delete_mcp_signing_key(kid: str):
    return _handle(lambda: _config.execute("delete_mcp_signing_key", {"id": kid}))


@router.post("/mcp-signing-keys/{kid}/reveal")
def reveal_mcp_signing_key(kid: str):
    return _handle(lambda: _config.execute("reveal_mcp_signing_key", {"id": kid}))


# ---------------------------------------------------------------------------
# Introspection (debug — no side effects)
# ---------------------------------------------------------------------------

@router.get("/check")
def check_right(
    roles: str = Query(...),
    resource_type: str = Query(...),
    resource_id: str = Query(...),
    operation: str = Query(...),
    field: Optional[str] = Query(None),
    confirmed: bool = Query(False),
):
    return _handle(lambda: _config.execute("check_right", {
        "roles": roles, "resource_type": resource_type, "resource_id": resource_id,
        "operation": operation, "field": field, "confirmed": confirmed,
    }))
