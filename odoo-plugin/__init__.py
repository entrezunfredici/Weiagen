"""``odoo`` Hermes plugin — Odoo connector (deny-by-default CRUD).

Office document generation (xlsx/docx/pptx, ``w_docs``) moved to the
separate ``docs`` plugin on 2026-09-24 (see ``.agents/DECISIONS.md``).

Ported from an OpenClaw plugin (see ``../sdk-plugin`` before it's removed, or
git history afterwards). The business logic (``w_main``, ``w_odoo``)
is unchanged; only the integration layer is new:

* Tools call straight into Python (no subprocess/JSON-stdio bridge).
* User confirmation for risky writes goes through Hermes's native
  ``pre_tool_call`` -> human-approval-gate mechanism instead of a bespoke
  90s REST poll against a companion Express service.
* Profile/right management is a ``hermes odoo`` CLI instead of a browser panel.

See ``README.md`` in this directory for the full picture.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Make w_main / w_odoo importable as top-level packages.
#
# Hermes loads this __init__.py via importlib with
# submodule_search_locations=[plugin_dir] (see hermes_cli/plugins.py::
# _load_directory_module), which lets *relative* imports (`from . import
# tools`) resolve as submodules of this plugin — but w_main/w_odoo were
# written for OpenClaw, where they're invoked as `python -m w_odoo.cli`
# with `cwd` set to this directory, so they use plain top-level absolute
# imports (`from w_main.data_manager import ...`). Adding this directory to
# sys.path lets those absolute imports resolve unmodified, so w_main/
# w_odoo stay byte-for-byte identical to the OpenClaw version.
# ---------------------------------------------------------------------------
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

# ---------------------------------------------------------------------------
# Redirect w_odoo's data files from OpenClaw's /workspace/... defaults to
# a directory under this Hermes profile's HERMES_HOME. Must happen before
# w_odoo/w_main.data_manager are imported (they read these env vars at
# module load time to build their SDKTable file paths).
#
# NOT under plugins/odoo/ (this directory itself): in the Docker deployment
# plugins/odoo is bind-mounted read-only straight from the weiagen_hermes repo
# (see ../docker-compose.yml), so profiles/rights/secrets need a directory
# that isn't inside the mounted plugin source.
# ---------------------------------------------------------------------------
from hermes_constants import get_hermes_home  # noqa: E402

_DATA_DIR = get_hermes_home() / "odoo-plugin-data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("ODOO_PROFILES_FILE_PATH", str(_DATA_DIR / "odoo-profiles.json"))
os.environ.setdefault("ODOO_RIGHTS_PATH", str(_DATA_DIR / "odoo-rights.json"))
os.environ.setdefault("ODOO_PLUGIN_KEYRING_PATH", str(_DATA_DIR / "odoo-keyring.json"))

from w_odoo import rights_bridge  # noqa: E402
# rights_bridge itself already logs a warning at import time if rights-plugin
# isn't found/enabled (it doesn't know it's specifically odoo-plugin asking,
# but the message is accurate either way) — no need to duplicate it here.

# Relative imports: this plugin's own cli.py/tools.py, loaded as submodules
# of the hermes_plugins.odoo package (see hermes_cli/plugins.py::
# _load_directory_module). MUST stay relative — a bare `from tools import
# ...` resolves to Hermes core's own top-level `tools` package
# (tools/registry.py etc.) instead of this plugin's tools.py, since both are
# named "tools". w_main/w_odoo don't have this problem (no name
# collision with anything in Hermes core), which is why those alone use the
# sys.path/absolute-import trick above instead of relative imports.
from .cli import odoo_command, register_cli  # noqa: E402
from .tools import ALL_TOOLS, CONFIRMABLE_TOOLS  # noqa: E402


def _fields_for_call(tool_name: str, args: Dict[str, Any]) -> tuple[list[str], str]:
    """Return (fields-to-check, operation) for a CONFIRMABLE_TOOLS call.

    Mirrors the field selection ``w_odoo.odoo_cli_for_ai.OdooAIExecutor``
    itself uses per action, so the pre-flight confirmation check agrees with
    what the handler will actually authorize.
    """
    if tool_name == "odoo_sdk_read":
        return list(args.get("fields") or ["id", "name"]), "read"
    if tool_name == "odoo_sdk_create":
        return list((args.get("values") or {}).keys()), "create"
    if tool_name == "odoo_sdk_update":
        return list((args.get("values") or {}).keys()), "update"
    if tool_name == "odoo_sdk_delete":
        return ["*"], "delete"
    return [], ""


def _pre_tool_call(
    tool_name: str = "", args: Dict[str, Any] | None = None,
    session_id: str | None = None, **_: Any,
) -> Dict[str, Any] | None:
    """Escalate to Hermes's native human-approval gate for confirmable Odoo writes.

    Returns an ``{"action": "approve", ...}`` directive when any field
    touched by the call is bound to a rights-plugin right (for this
    caller's roles) with ``require_confirmation`` (or the per-operation
    ``confirm_*`` flag) set. Hermes's dispatch layer
    (``hermes_cli.plugins.resolve_pre_tool_block``) is what actually
    blocks and waits for a human decision — this hook only has to say
    *whether* that's needed, replacing the old ``requestUiConfirmation()``
    REST-poll loop entirely.

    Note ``session_id`` used to be silently swallowed by ``**_`` here — now
    used to resolve the caller's identity/roles via rights_bridge.
    """
    if tool_name not in CONFIRMABLE_TOOLS or not isinstance(args, dict):
        return None

    profile_id = args.get("profile_id")
    model = args.get("model")
    if not profile_id or not model:
        return None

    fields, operation = _fields_for_call(tool_name, args)
    if not fields:
        return None

    identity = rights_bridge.get_identity(session_id)

    for field in fields:
        allowed, require_confirmation = rights_bridge.check_field(
            profile_id, model, field, operation, identity.roles
        )
        if allowed and require_confirmation:
            return {
                "action": "approve",
                "message": (
                    f"Hermes wants to {operation} on Odoo model '{model}' "
                    f"(profile '{profile_id}') — this right requires confirmation."
                ),
                "rule_key": f"odoo:{operation}:{model}",
            }
    return None


def register(ctx) -> None:
    for name, toolset, schema, handler, emoji in ALL_TOOLS:
        ctx.register_tool(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            emoji=emoji,
        )

    ctx.register_cli_command(
        name="odoo",
        help="Manage Odoo connection profiles and rights",
        setup_fn=register_cli,
        handler_fn=odoo_command,
        description=(
            "Configure Odoo connection profiles and deny-by-default rights "
            "used by the odoo_sdk_* tools. See: hermes odoo profile add --help"
        ),
    )

    ctx.register_hook("pre_tool_call", _pre_tool_call)
