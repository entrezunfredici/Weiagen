"""``hermes odoo`` operator CLI — manage connection profiles.

Replaces the OpenClaw version's browser UI (``sdk-plugin/ui/bootstrap-modal-
odoo-profile.js``, ``bootstrap-modal-odoo-rights.js``, and the floating
"Profils Odoo" panel) with a plain argparse-driven CLI, following the same
``register_cli_command`` pattern as ``plugins/google_meet/cli.py``. A
dashboard UI (in the style of ``plugins/kanban/dashboard/``) is a possible
follow-up, not part of this first port.

Rights management (``right add/list/rm``) used to live here too, but moved
entirely to the ``rights`` plugin (``hermes rights right add/list/rm
--resource-type odoo_model --resource-id "<profile_id>:<model>"``) — see
``.agents/DECISIONS.md``, "rights-plugin: vendoring vs cross-plugin import".
This is a breaking CLI change, called out explicitly in
``.agents/CHANGELOG_AGENT.md`` and the repo root README.
"""

from __future__ import annotations

import argparse
import json

from w_main.errors_manager.errors import ConnectorError
from w_odoo.odoo_cli_for_config import OdooConfigExecutor

_config = OdooConfigExecutor()


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes odoo`` argparse tree."""
    subs = subparser.add_subparsers(dest="odoo_command")

    profile = subs.add_parser("profile", help="Manage Odoo connection profiles")
    profile_subs = profile.add_subparsers(dest="odoo_profile_command")

    p_add = profile_subs.add_parser("add", help="Create or update a connection profile")
    p_add.add_argument("id", help="Stable profile id used in tool calls, e.g. 'default'")
    p_add.add_argument("--label", help="Human-readable label (defaults to id)")
    p_add.add_argument("--base-url", required=True, help="Base URL of the Odoo instance")
    p_add.add_argument("--database", required=True, help="Odoo database name")
    p_add.add_argument("--login", required=True, help="Technical account login")
    p_add.add_argument("--password", required=True, help="Technical account password or API key")
    p_add.add_argument("--port", type=int, default=443, help="HTTPS port (default 443)")
    p_add.add_argument("--disabled", action="store_true", help="Create the profile disabled")

    profile_subs.add_parser("list", help="List connection profiles")

    p_rm = profile_subs.add_parser("rm", help="Delete a connection profile")
    p_rm.add_argument("id", help="Profile id to delete")

    # Read-only now — "add"/"rm" moved to the rights plugin, see module
    # docstring. Kept as a CLI convenience mirroring the agent-facing
    # odoo_list_rights tool (both go through OdooConfigExecutor's
    # read-only "list_rights" action).
    right = subs.add_parser("right", help="View configured Odoo rights (read-only — manage via `hermes rights`)")
    right_subs = right.add_subparsers(dest="odoo_right_command")
    r_list = right_subs.add_parser("list", help="List configured rights")
    r_list.add_argument("--profile-id", dest="profile_id", help="Filter by connection profile id")


def _print_result(result: dict) -> int:
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def _call(action: str, payload: dict) -> int:
    try:
        result = _config.execute(action, payload)
    except ConnectorError as exc:
        return _print_result(exc.to_dict())
    return _print_result(result)


def odoo_command(args: argparse.Namespace) -> int:
    sub = getattr(args, "odoo_command", None)

    if sub == "profile":
        psub = getattr(args, "odoo_profile_command", None)
        if psub == "add":
            return _call("save_profile", {
                "id": args.id,
                "label": args.label or args.id,
                "base_url": args.base_url,
                "database": args.database,
                "login": args.login,
                "password": args.password,
                "port": args.port,
                "enabled": not args.disabled,
            })
        if psub == "list":
            return _call("list_profiles", {})
        if psub == "rm":
            return _call("delete_profile", {"id": args.id})
        print("usage: hermes odoo profile {add,list,rm}")
        return 2

    if sub == "right":
        rsub = getattr(args, "odoo_right_command", None)
        if rsub == "list":
            return _call("list_rights", {"profile_id": args.profile_id})
        print("usage: hermes odoo right list [--profile-id ID]  (manage rights via `hermes rights`)")
        return 2

    print("usage: hermes odoo {profile,right} ...")
    return 2
