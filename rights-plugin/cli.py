"""``hermes rights`` operator CLI — manage identity→role bindings and access rights.

Same ``register_cli``/``<name>_command``/``_call``/``_print_result`` pattern
as ``odoo-plugin/cli.py`` — one argparse tree, dispatched to a config
executor (``config_executor.RightsConfigExecutor``).
"""

from __future__ import annotations

import argparse
import json

from rights_w_main.errors_manager.errors import ConnectorError

from config_executor import RightsConfigExecutor

_config = RightsConfigExecutor()


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes rights`` argparse tree."""
    subs = subparser.add_subparsers(dest="rights_command")

    role = subs.add_parser("role", help="Manage identity→role bindings")
    role_subs = role.add_subparsers(dest="rights_role_command")

    ro_bind = role_subs.add_parser("bind", help="Create or replace the role binding for one identity")
    ro_bind.add_argument("--platform", required=True, help="e.g. 'slack', 'telegram', 'cli'")
    ro_bind.add_argument("--user", required=True, dest="user", help="Platform-specific external user id")
    ro_bind.add_argument("--roles", required=True, help="Comma-separated role names, e.g. 'admin,finance'")
    ro_bind.add_argument("--label", default="", help="Human-readable note, e.g. a real name")

    ro_unbind = role_subs.add_parser("unbind", help="Remove the role binding for one identity")
    ro_unbind.add_argument("--platform", required=True)
    ro_unbind.add_argument("--user", required=True, dest="user")

    ro_list = role_subs.add_parser("list", help="List role bindings")
    ro_list.add_argument("--platform", help="Filter by platform")
    ro_list.add_argument("--user", dest="user", help="Filter by external user id")

    catalog = role_subs.add_parser("catalog", help="Manage the role catalog (names/labels, independent of who holds them or what they grant)")
    catalog_subs = catalog.add_subparsers(dest="rights_role_catalog_command")

    cat_create = catalog_subs.add_parser("create", help="Create or update a role catalog entry")
    cat_create.add_argument("--id", required=True, help="The role slug itself, e.g. 'admin' — same string used in role bind/right add")
    cat_create.add_argument("--label", default="", help="Human-readable name")
    cat_create.add_argument("--description", default="", help="Optional longer description")

    catalog_subs.add_parser("list", help="List role catalog entries")

    cat_rm = catalog_subs.add_parser("rm", help="Delete a role catalog entry (does not touch bindings/rights still referencing it)")
    cat_rm.add_argument("id", help="Role id to delete")

    right = subs.add_parser("right", help="Manage deny-by-default access rights")
    right_subs = right.add_subparsers(dest="rights_right_command")

    r_add = right_subs.add_parser("add", help="Create or update an access right")
    r_add.add_argument("--id", help="Right id (generated if omitted)")
    r_add.add_argument("--roles", required=True, help="Comma-separated role names this right applies to, e.g. 'admin,finance'")
    r_add.add_argument("--resource-type", required=True, dest="resource_type", help="e.g. 'odoo_model', 'hermes_tool'")
    r_add.add_argument("--resource-id", required=True, dest="resource_id", help="e.g. '1:project.task', 'shell_exec', '*'")
    r_add.add_argument("--fields", default="*", help="Comma-separated field list, or '*' for all fields")
    r_add.add_argument("--label", default="", help="Human-readable label")
    r_add.add_argument("--create", action="store_true")
    r_add.add_argument("--read", dest="read", action="store_true", default=True)
    r_add.add_argument("--no-read", dest="read", action="store_false")
    r_add.add_argument("--update", action="store_true")
    r_add.add_argument("--delete", action="store_true")
    r_add.add_argument("--execute", action="store_true", help="Allow bare tool-call gating (resource_type=hermes_tool)")
    r_add.add_argument("--require-confirmation", action="store_true", help="Require human approval before any allowed op runs")
    r_add.add_argument("--confirm-create", action="store_true", dest="confirm_create")
    r_add.add_argument("--confirm-read", action="store_true", dest="confirm_read")
    r_add.add_argument("--confirm-update", action="store_true", dest="confirm_update")
    r_add.add_argument("--confirm-delete", action="store_true", dest="confirm_delete")
    r_add.add_argument("--confirm-execute", action="store_true", dest="confirm_execute")

    r_list = right_subs.add_parser("list", help="List configured access rights")
    r_list.add_argument("--role", help="Filter by role")
    r_list.add_argument("--resource-type", dest="resource_type", help="Filter by resource type")
    r_list.add_argument("--resource-id", dest="resource_id", help="Filter by resource id")

    r_rm = right_subs.add_parser("rm", help="Delete an access right")
    r_rm.add_argument("id", help="Right id to delete")

    check = subs.add_parser("check", help="Debug: evaluate a (roles, resource, operation) decision — no side effects")
    check.add_argument("--roles", required=True, help="Comma-separated role names to check")
    check.add_argument("--resource-type", required=True, dest="resource_type")
    check.add_argument("--resource-id", required=True, dest="resource_id")
    check.add_argument("--operation", required=True, choices=["create", "read", "update", "delete", "execute"])
    check.add_argument("--field", default=None, help="Field to check (defaults to '*')")
    check.add_argument("--confirmed", action="store_true", help="Simulate an already-confirmed call")

    whoami = subs.add_parser("whoami", help="Resolve an identity and its roles — no side effects")
    whoami.add_argument("--platform", help="e.g. 'slack' (use with --user)")
    whoami.add_argument("--user", dest="user", help="External user id (use with --platform)")
    whoami.add_argument("--session-id", dest="session_id", help="Resolve via a live Hermes session id instead")

    migrate = subs.add_parser(
        "migrate-odoo-rights",
        help="Migrate a legacy odoo-plugin odoo-rights.json into AccessRight rows bound to role 'everyone'",
    )
    migrate.add_argument("--path", required=True, help="Path to the legacy odoo-rights.json file")
    migrate.add_argument("--dry-run", action="store_true", dest="dry_run", help="Report what would be migrated without writing")

    directory = subs.add_parser(
        "directory",
        help="Cached identity directory (e.g. Slack workspace members) used as a pick-list by the dashboard",
    )
    directory_subs = directory.add_subparsers(dest="rights_directory_command")

    d_sync = directory_subs.add_parser("sync", help="Force a real sync now (raises loudly on failure)")
    d_sync.add_argument("--platform", default="slack", help="Defaults to 'slack' (the only platform wired up today)")

    d_list = directory_subs.add_parser("list", help="Show the cached directory — no sync triggered")
    d_list.add_argument("--platform", default="slack", help="Defaults to 'slack'")

    plat = subs.add_parser(
        "platforms",
        help="List Hermes messaging platforms that look configured on this deployment",
    )
    plat.add_argument(
        "--all", dest="include_unconfigured", action="store_true",
        help="Also list platforms Hermes knows about but that aren't configured here",
    )

    subs.add_parser(
        "tools",
        help="List every tool Hermes currently has registered (built-in + plugin + MCP) — debug, no side effects",
    )

    mcp_key = subs.add_parser(
        "mcp-key",
        help="Manage signing keys for MCP identity tokens (one per EXTERNAL MCP microservice, see token_signer.py)",
    )
    mcp_key_subs = mcp_key.add_subparsers(dest="rights_mcp_key_command")

    mk_add = mcp_key_subs.add_parser("add", help="Create or update a signing key (upsert by --id/kid)")
    mk_add.add_argument("--id", required=True, dest="id", help="The kid — referenced directly in the token header, e.g. 'rag_mcp'")
    mk_add.add_argument("--label", default="", help="Human-readable name, e.g. 'RAG MCP (self-hosted)'")
    mk_add.add_argument("--alg", default="HS256", help="Signing algorithm (only HS256 today)")
    mk_add.add_argument(
        "--secret", default=None,
        help="Shared secret. Omit to auto-generate one on first creation, or to keep the existing one when editing an existing key",
    )
    mk_add.add_argument("--inactive", dest="active", action="store_false", default=True, help="Create the key disabled (no token issued for it)")

    mcp_key_subs.add_parser("list", help="List signing keys — secret shown masked (last 4 chars only)")

    mk_reveal = mcp_key_subs.add_parser("reveal", help="Show the full secret for one key — use to re-share it, not logged by default")
    mk_reveal.add_argument("id", help="Key id (kid) to reveal")

    mk_rm = mcp_key_subs.add_parser("rm", help="Delete a signing key")
    mk_rm.add_argument("id", help="Key id (kid) to delete")


def _print_result(result: dict) -> int:
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def _call(action: str, payload: dict) -> int:
    try:
        result = _config.execute(action, payload)
    except ConnectorError as exc:
        return _print_result(exc.to_dict())
    return _print_result(result)


def rights_command(args: argparse.Namespace) -> int:
    sub = getattr(args, "rights_command", None)

    if sub == "role":
        rsub = getattr(args, "rights_role_command", None)
        if rsub == "bind":
            return _call("bind_role", {
                "platform": args.platform,
                "user": args.user,
                "roles": args.roles,
                "label": args.label,
            })
        if rsub == "unbind":
            return _call("unbind_role", {"platform": args.platform, "user": args.user})
        if rsub == "list":
            return _call("list_role_bindings", {"platform": args.platform, "user": args.user})
        if rsub == "catalog":
            csub = getattr(args, "rights_role_catalog_command", None)
            if csub == "create":
                return _call("save_role", {"id": args.id, "label": args.label, "description": args.description})
            if csub == "list":
                return _call("list_roles", {})
            if csub == "rm":
                return _call("delete_role", {"id": args.id})
            print("usage: hermes rights role catalog {create,list,rm}")
            return 2
        print("usage: hermes rights role {bind,unbind,list,catalog}")
        return 2

    if sub == "right":
        rsub = getattr(args, "rights_right_command", None)
        if rsub == "add":
            return _call("save_right", {
                "id": args.id,
                "roles": args.roles,
                "resource_type": args.resource_type,
                "resource_id": args.resource_id,
                "fields": args.fields,
                "label": args.label,
                "create": args.create,
                "read": args.read,
                "update": args.update,
                "delete": args.delete,
                "execute": args.execute,
                "require_confirmation": args.require_confirmation,
                "confirm_create": args.confirm_create,
                "confirm_read": args.confirm_read,
                "confirm_update": args.confirm_update,
                "confirm_delete": args.confirm_delete,
                "confirm_execute": args.confirm_execute,
            })
        if rsub == "list":
            return _call("list_rights", {
                "role": args.role,
                "resource_type": args.resource_type,
                "resource_id": args.resource_id,
            })
        if rsub == "rm":
            return _call("delete_right", {"id": args.id})
        print("usage: hermes rights right {add,list,rm}")
        return 2

    if sub == "check":
        return _call("check_right", {
            "roles": args.roles,
            "resource_type": args.resource_type,
            "resource_id": args.resource_id,
            "operation": args.operation,
            "field": args.field,
            "confirmed": args.confirmed,
        })

    if sub == "whoami":
        return _call("whoami", {
            "platform": args.platform,
            "user": args.user,
            "session_id": args.session_id,
        })

    if sub == "migrate-odoo-rights":
        return _call("migrate_odoo_rights", {"path": args.path, "dry_run": args.dry_run})

    if sub == "directory":
        dsub = getattr(args, "rights_directory_command", None)
        if dsub == "sync":
            return _call("sync_directory", {"platform": args.platform})
        if dsub == "list":
            return _call("list_directory", {"platform": args.platform})
        print("usage: hermes rights directory {sync,list}")
        return 2

    if sub == "platforms":
        return _call("list_platforms", {"include_unconfigured": args.include_unconfigured})

    if sub == "tools":
        return _call("list_hermes_tools", {})

    if sub == "mcp-key":
        msub = getattr(args, "rights_mcp_key_command", None)
        if msub == "add":
            return _call("save_mcp_signing_key", {
                "id": args.id,
                "label": args.label,
                "alg": args.alg,
                "secret": args.secret,
                "active": args.active,
            })
        if msub == "list":
            return _call("list_mcp_signing_keys", {})
        if msub == "reveal":
            return _call("reveal_mcp_signing_key", {"id": args.id})
        if msub == "rm":
            return _call("delete_mcp_signing_key", {"id": args.id})
        print("usage: hermes rights mcp-key {add,list,reveal,rm}")
        return 2

    print("usage: hermes rights {role,right,check,whoami,migrate-odoo-rights,directory,platforms,tools,mcp-key} ...")
    return 2
