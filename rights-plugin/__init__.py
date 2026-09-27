"""``rights`` Hermes plugin — generic deny-by-default authorization.

Replaces odoo-plugin's ``OdooRight`` entirely (see ``.agents/DECISIONS.md``,
"rights-plugin: vendoring vs cross-plugin import"). Two responsibilities:

1. Identity → role bindings (``models.RoleBinding``), platform-agnostic.
2. Role → resource rights (``models.AccessRight``), the generalized
   ``(role, resource_type, resource_id, fields) -> CRUD(+execute) +
   confirmation`` rule set, evaluated by ``engine.check_right()``.

Consumed two ways:

- **By other plugins** (``odoo-plugin`` first) via ``rights_plugin_api`` —
  the stable public contract, imported as a sibling-directory module (see
  that file's docstring for the exact cross-plugin mechanism).
- **Directly by this plugin's own hooks**, registered below:
  ``pre_tool_call`` gates any Hermes tool call (built-in, other plugin's, or
  MCP-provided — the hook fires uniformly for all of them) under
  ``resource_type="hermes_tool"`` (operation="execute") — except the
  built-in ``cronjob`` tool, redirected to ``resource_type="hermes_cron"``
  with a real create/read/update/delete derived from its ``action``
  argument (see ``_CRONJOB_ACTION_TO_OPERATION`` below; ``hermes_cron`` has
  no dedicated Hermes hook of its own, this is the only enforcement point
  available). ``pre_llm_call`` injects the resolved identity into every
  turn's context so an MCP tool whose own schema wants an identity
  parameter can be given one — never an enforcement mechanism, MCP-side
  RBAC (if any) is each MCP service's own responsibility. For an EXTERNAL
  MCP microservice (a separate process/host, never a Hermes plugin — see
  ``token_signer.py``), a plain-text identity string isn't enough: the LLM
  is the only transport between Hermes and that service and can't be
  trusted not to garble or fabricate role names, so ``pre_llm_call`` also
  injects one signed, opaque token per configured external MCP
  (``token_signer.issue_mcp_identity_tokens`` — one key per MCP, see
  ``models.McpSigningKey``) that each MCP's own tool schema can declare a
  parameter for — the LLM only ever relays it, it never holds a signing key.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Make models/engine/identity importable as top-level modules — same
# sys.path trick odoo-plugin/__init__.py uses for w_main/w_odoo
# (see the comment there). None of these three names collide with anything
# in Hermes core's own top-level namespace (confirmed by inspecting the
# editable-install module map on a real Hermes container — see
# .agents/DECISIONS.md).
# ---------------------------------------------------------------------------
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

# ---------------------------------------------------------------------------
# Data directory + env vars — must be set before models.py (or anything
# importing it) is imported anywhere, since it reads these at module load
# time to build its SDKTables.
# ---------------------------------------------------------------------------
from hermes_constants import get_hermes_home  # noqa: E402

_DATA_DIR = get_hermes_home() / "rights-plugin-data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("RIGHTS_ROLE_BINDINGS_PATH", str(_DATA_DIR / "role-bindings.json"))
os.environ.setdefault("RIGHTS_ACCESS_RIGHTS_PATH", str(_DATA_DIR / "access-rights.json"))
os.environ.setdefault("RIGHTS_DIRECTORY_ENTRIES_PATH", str(_DATA_DIR / "directory-entries.json"))

import directory  # noqa: E402
import engine  # noqa: E402
import models  # noqa: E402
import token_signer  # noqa: E402
from identity import resolve_identity  # noqa: E402
from migrate_odoo_rights import maybe_migrate_odoo_rights_on_load  # noqa: E402

# cli.py MUST be a relative import from here, like odoo-plugin/tools.py and
# odoo-plugin/cli.py — Hermes core has its own top-level `cli` package
# (`hermes_cli`'s sibling), a bare `from cli import ...` would resolve to
# that instead of this plugin's own cli.py. See .agents/CONVENTIONS.md for
# the identical hazard already documented for odoo-plugin.
from .cli import register_cli, rights_command  # noqa: E402


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

# The "cronjob" built-in tool (tools/cronjob_tools.py) is a single unified
# entry point for all cron management — `cronjob(action=..., ...)` — so
# unlike every other tool, it has a real CRUD verb per call, available
# right here in `args`. Gated as resource_type="hermes_cron" instead of
# the generic "hermes_tool"/execute path every other tool gets — see
# .agents/DECISIONS.md (2026-08-19) for why "hermes_cron" existed as a
# dead placeholder before this and how this mapping was derived from
# Hermes's own real source (confirmed: no dedicated cron hook exists in
# VALID_HOOKS, so this is the only enforcement point available). No
# per-job granularity (resource_id is always "*") — this is a coarse
# capability ("can this identity create/read/update/delete cron jobs at
# all"), not a per-job ACL, matching what was asked for.
_CRONJOB_ACTION_TO_OPERATION: Dict[str, str] = {
    "create": "create",
    "list": "read",
    "update": "update",
    "pause": "update",
    "resume": "update",
    "remove": "delete",
}


def _pre_tool_call(tool_name: str = "", args: Dict[str, Any] | None = None,
                    session_id: str | None = None, **_: Any) -> Dict[str, Any] | None:
    """Gate any Hermes tool call.

    Every tool except "cronjob" is gated under resource_type="hermes_tool",
    operation="execute" (a bare tool call has no natural CRUD verb — see
    rights_w_main/right_manager/right_manager.py's synthetic "execute"
    operation). "cronjob" calls are redirected to resource_type=
    "hermes_cron" with a real CRUD operation derived from args["action"]
    (see _CRONJOB_ACTION_TO_OPERATION above) — unmapped/unknown actions
    default to "read", the least destructive verb.

    Safety property (``hermes_tool`` only): only evaluates tool calls at
    all once at least one ``hermes_tool`` AccessRight exists **for any
    tool** (see engine.has_any_right_configured — NOT scoped to the one
    tool being called, see its docstring for why: a per-resource_id check
    here means narrowing an existing "*" right down to one specific tool
    silently leaves every *other* tool ungated forever, a real bug caught
    2026-08-19, see .agents/DECISIONS.md). Before that first right exists
    anywhere, no tool call is gated — enabling this plugin with zero
    configured rights must never start denying every built-in Hermes tool
    (shell_exec, etc.) by surprise. The moment an operator adds their
    first hermes_tool right, deny-by-default applies to every tool, not
    just the one that now has a right.

    ``hermes_cron`` doesn't get this bootstrap leniency at all, even the
    corrected per-resource_type version (see .agents/DECISIONS.md,
    2026-08-19): a cron job can plant a persistent, auto-executing prompt
    — materially more sensitive than a single tool call — so "nobody has
    configured a hermes_cron right yet" must mean denied, not ungated,
    from the very first call.
    """
    if tool_name == "cronjob":
        resource_type, resource_id = "hermes_cron", "*"
        action = str((args or {}).get("action", "")).strip().lower()
        operation = _CRONJOB_ACTION_TO_OPERATION.get(action, "read")
    else:
        resource_type, resource_id, operation = "hermes_tool", tool_name, "execute"
        if not engine.has_any_right_configured(resource_type):
            return None

    identity = resolve_identity(session_id=session_id)
    decision = engine.check_right(
        roles=identity.roles, resource_type=resource_type, resource_id=resource_id, operation=operation
    )

    if decision.allowed and not decision.require_confirmation:
        return None
    if not decision.allowed:
        return {"action": "block", "message": f"Blocked by rights-plugin: {decision.reason}"}
    return {
        "action": "approve",
        "message": decision.reason,
        "rule_key": f"rights:{resource_type}:{resource_id}:{operation}",
    }


def _pre_llm_call(session_id: str | None = None, platform: str | None = None,
                   sender_id: str | None = None, **_: Any) -> Dict[str, Any] | None:
    """Inject the resolved identity into every turn's context. Never blocks.

    Also opportunistically keeps the Slack member directory fresh (see
    directory.py) — this hook already fires once per turn, so it's a
    convenient, dependency-free place to check staleness without a real
    background job (Hermes's plugin API has no cron-registration hook).
    ``ensure_fresh`` is guaranteed never to raise (it's a no-op unless the
    cache is actually stale, default TTL 24h, and swallows its own
    failures) — see its docstring — so this never adds latency or risk to a
    normal turn.

    One opaque line per active, configured MCP signing key is appended
    (``token_signer.issue_mcp_identity_tokens`` — see that module's
    docstring for why a plain-text identity isn't enough for an EXTERNAL MCP
    microservice, and why there can be more than one: a turn doesn't know in
    advance which external MCP tool, if any, the model is about to call, so
    every active key signs its own token). Guaranteed never to raise and
    returns an empty list when no key is configured yet (see the "MCP
    signing keys" section of the dashboard/CLI) — no extra lines are then
    appended, same "never break a turn by surprise" contract as the identity
    line above.
    """
    directory.ensure_fresh("slack")

    identity = resolve_identity(session_id=session_id, platform=platform, external_user_id=sender_id)
    context_lines = [
        f"[identity] platform={identity.platform} user={identity.external_user_id} "
        f"roles={','.join(identity.roles)}"
    ]

    tokens = token_signer.issue_mcp_identity_tokens(
        platform=identity.platform, external_user_id=identity.external_user_id, roles=identity.roles
    )
    for entry in tokens:
        context_lines.append(
            f"[mcp_identity_token kid={entry['kid']}"
            f"{' label=' + entry['label'] if entry['label'] else ''}] {entry['token']} — opaque, "
            f"signed. Use it ONLY as the identity/caller-token argument of a tool named "
            f"mcp__{entry['kid']}__* (the MCP server named '{entry['kid']}') — never for a tool "
            "from a different MCP server, even one that also takes a caller-token argument: each "
            "kid's token is signed for that one server only and every other server will reject it. "
            "Pass it UNCHANGED. Never edit, shorten, or fabricate this value."
        )

    return {"context": "\n".join(context_lines)}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    """Register the ``hermes rights`` CLI and the pre_tool_call/pre_llm_call hooks.

    Also runs two one-off, idempotent self-heal passes — a hiccup in
    either is logged, not raised: neither must ever prevent the plugin
    itself (and therefore odoo-plugin, which hard-depends on it) from
    loading:

    - Auto-migration of odoo-plugin's legacy ``OdooRight`` data (if any)
      into ``AccessRight`` rows bound to the "everyone" role — see
      migrate_odoo_rights.py.
    - Correction of any hermes_tool/hermes_cron right saved before
      2026-08-20 with a non-``["*"]`` ``fields`` value (silently 100%
      inert — see models.normalize_hermes_resource_fields and
      .agents/DECISIONS.md).
    """
    try:
        maybe_migrate_odoo_rights_on_load()
    except Exception:
        logger.exception("rights-plugin: auto-migration of legacy OdooRight data failed")

    try:
        fixed = models.normalize_hermes_resource_fields()
        if fixed:
            logger.warning(
                "rights-plugin: corrected %d hermes_tool/hermes_cron right(s) with a stale, "
                "non-wildcard 'fields' value that made them silently inert (see "
                ".agents/DECISIONS.md, 'Garde-fous d'amorçage de pre_tool_call')",
                fixed,
            )
    except Exception:
        logger.exception("rights-plugin: hermes_tool/hermes_cron fields self-heal failed")

    ctx.register_cli_command(
        name="rights",
        help="Manage generic identity→role bindings and deny-by-default access rights",
        setup_fn=register_cli,
        handler_fn=rights_command,
        description=(
            "Configure identity→role bindings and role→resource access rights "
            "used across every plugin/tool that delegates to rights-plugin. "
            "See: hermes rights role bind --help"
        ),
    )
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
