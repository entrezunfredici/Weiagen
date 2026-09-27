"""Dashboard backend routes for the odoo plugin — profiles + rights CRUD.

Mounted by Hermes's dashboard web server at ``/api/plugins/odoo`` (see
``hermes_cli/web_server.py::_mount_plugin_api_routes``). The host handles
session auth for every ``/api/...`` request before this module's handlers
ever run — no auth code needed here (confirmed against the host's own
``plugin_api.py`` docstring convention, e.g. ``plugins/kanban/dashboard/``).

Runs in the **dashboard's own process**, separate from the gateway process
that loads ``../__init__.py`` (the agent-facing tool plugin). Nothing set up
there (sys.path, HERMES_HOME-derived data paths) carries over here — this
file repeats that bootstrap independently so both processes agree on where
profiles/rights/secrets live.
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

_DATA_DIR = get_hermes_home() / "odoo-plugin-data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("ODOO_PROFILES_FILE_PATH", str(_DATA_DIR / "odoo-profiles.json"))
os.environ.setdefault("ODOO_RIGHTS_PATH", str(_DATA_DIR / "odoo-rights.json"))
os.environ.setdefault("ODOO_PLUGIN_KEYRING_PATH", str(_DATA_DIR / "odoo-keyring.json"))

from fastapi import APIRouter, HTTPException, Query  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from w_main.errors_manager.errors import ConnectorError  # noqa: E402
from w_odoo.odoo_cli_for_ai import OdooAIExecutor  # noqa: E402
from w_odoo.odoo_cli_for_config import OdooConfigExecutor  # noqa: E402
from w_odoo.odoo_profile import get_odoo_profile_or_none  # noqa: E402

router = APIRouter()

_config = OdooConfigExecutor()
_ai = OdooAIExecutor()

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


class ProfileBody(BaseModel):
    id: str
    label: Optional[str] = None
    base_url: str
    database: str
    login: str
    password: Optional[str] = None
    port: int = 443
    enabled: bool = True


class RightBody(BaseModel):
    id: Optional[str] = None
    profile_id: str
    odoo_model: str
    fields: str = "*"
    label: Optional[str] = ""
    create: bool = False
    read: bool = True
    update: bool = False
    delete: bool = False
    require_confirmation: bool = False
    confirm_create: bool = False
    confirm_read: bool = False
    confirm_update: bool = False
    confirm_delete: bool = False


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

@router.get("/profiles")
def list_profiles():
    return _handle(lambda: _config.execute("list_profiles", {}))


@router.post("/profiles")
def save_profile(payload: ProfileBody):
    password = payload.password or ""
    if not password:
        # Editing an existing profile without retyping the password keeps
        # the current one — _profile_to_dict() never returns it to the
        # browser, so we resolve it server-side instead of round-tripping it.
        existing = get_odoo_profile_or_none(payload.id)
        if existing is not None:
            password = existing.password

    def _call():
        return _config.execute("save_profile", {
            "id": payload.id,
            "label": payload.label or payload.id,
            "base_url": payload.base_url,
            "database": payload.database,
            "login": payload.login,
            "password": password,
            "port": payload.port,
            "enabled": payload.enabled,
        })

    return _handle(_call)


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str):
    return _handle(lambda: _config.execute("delete_profile", {"id": profile_id}))


# ---------------------------------------------------------------------------
# Rights
# ---------------------------------------------------------------------------

@router.get("/rights")
def list_rights(profile_id: Optional[str] = Query(None)):
    return _handle(lambda: _config.execute("list_rights", {"profile_id": profile_id or ""}))


@router.post("/rights")
def save_right(payload: RightBody):
    return _handle(lambda: _config.execute("save_right", payload.model_dump()))


@router.delete("/rights/{right_id}")
def delete_right(right_id: str):
    return _handle(lambda: _config.execute("delete_right", {"id": right_id}))


@router.get("/models")
def list_models(profile_id: str = Query(...)):
    # Live introspection (ir.model) against the connected Odoo instance, not
    # scoped to existing rights — this is what populates the model dropdown
    # when *creating* a right, before any right for that model exists yet.
    #
    # Unlike the other endpoints (local JSON file ops only), this one makes a
    # real JSON-RPC call to a third-party Odoo server, so bad credentials, a
    # wrong database name, or a network/DNS failure are expected outcomes —
    # not just ConnectorError (config-layer validation). _ai.execute() itself
    # doesn't wrap those in a ConnectorError (see odoo_cli_for_ai.py), so
    # _handle()'s ConnectorError-only catch would let them escape as an
    # opaque FastAPI 500 with no message for the dropdown to show.
    def _call():
        try:
            return _ai.execute("odoo_list_models", "", {"profile_id": profile_id})
        except ConnectorError:
            raise
        except Exception as exc:
            # odoolib.JsonRPCException.__str__ returns repr(self.error), which
            # includes the full Odoo-server-side traceback under
            # error["data"]["debug"] — unusable as a UI message. The
            # human-readable part is error["data"]["message"] (falls back to
            # error["message"], then plain str(exc) for non-JsonRPC failures
            # like DNS/connection errors that never reach the Odoo server).
            detail = str(exc)
            error_payload = getattr(exc, "error", None)
            if isinstance(error_payload, dict):
                data = error_payload.get("data") or {}
                detail = data.get("message") or error_payload.get("message") or detail
            raise HTTPException(status_code=502, detail=f"Could not reach Odoo: {detail}")

    return _handle(_call)
