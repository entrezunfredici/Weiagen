"""rights_plugin/cli.py — `hermes rights` argparse tree + dispatch.

Loaded through the ``cli_mod`` fixture (see tests/conftest.py), which goes
through the real plugin-loading path — same pattern as odoo-plugin's
tests/test_cli.py.
"""

import argparse
import json

import pytest


@pytest.fixture
def parser(cli_mod):
    p = argparse.ArgumentParser()
    cli_mod.register_cli(p)
    return p


class _FakeConfigExecutor:
    def __init__(self):
        self.calls = []
        self._result = {"ok": True}

    def returning(self, result):
        self._result = result
        return self

    def execute(self, action, payload):
        self.calls.append((action, payload))
        return self._result


@pytest.fixture
def fake_config(cli_mod, monkeypatch):
    fake = _FakeConfigExecutor()
    monkeypatch.setattr(cli_mod, "_config", fake)
    return fake


# ---------------------------------------------------------------------------
# argparse tree
# ---------------------------------------------------------------------------


def test_role_bind_parses_required_args(parser):
    args = parser.parse_args(["role", "bind", "--platform", "slack", "--user", "U0123", "--roles", "admin,finance"])
    assert args.platform == "slack"
    assert args.user == "U0123"
    assert args.roles == "admin,finance"


def test_right_add_defaults(parser):
    args = parser.parse_args([
        "right", "add", "--roles", "admin", "--resource-type", "hermes_tool", "--resource-id", "shell_exec",
    ])
    assert args.fields == "*"
    assert args.read is True
    assert args.create is False
    assert args.execute is False
    assert args.require_confirmation is False


def test_right_add_no_read_flag(parser):
    args = parser.parse_args([
        "right", "add", "--roles", "admin", "--resource-type", "hermes_tool", "--resource-id", "shell_exec", "--no-read",
    ])
    assert args.read is False


def test_check_requires_operation_choice(parser):
    with pytest.raises(SystemExit):
        parser.parse_args([
            "check", "--roles", "admin", "--resource-type", "hermes_tool",
            "--resource-id", "shell_exec", "--operation", "not-a-real-op",
        ])


# ---------------------------------------------------------------------------
# dispatch (rights_command)
# ---------------------------------------------------------------------------


def test_role_bind_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["role", "bind", "--platform", "slack", "--user", "U0123", "--roles", "admin,finance"])
    rc = cli_mod.rights_command(args)
    assert rc == 0
    action, payload = fake_config.calls[0]
    assert action == "bind_role"
    assert payload["platform"] == "slack"
    assert payload["user"] == "U0123"
    assert payload["roles"] == "admin,finance"


def test_role_unbind_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["role", "unbind", "--platform", "slack", "--user", "U0123"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("unbind_role", {"platform": "slack", "user": "U0123"})


def test_role_list_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["role", "list"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("list_role_bindings", {"platform": None, "user": None})


def test_right_add_dispatches_save_right(cli_mod, parser, fake_config):
    args = parser.parse_args([
        "right", "add", "--roles", "admin,finance", "--resource-type", "odoo_model", "--resource-id", "1:project.task",
        "--fields", "name,deadline", "--create", "--require-confirmation",
    ])
    cli_mod.rights_command(args)
    action, payload = fake_config.calls[0]
    assert action == "save_right"
    assert payload["roles"] == "admin,finance"
    assert payload["resource_type"] == "odoo_model"
    assert payload["resource_id"] == "1:project.task"
    assert payload["fields"] == "name,deadline"
    assert payload["create"] is True
    assert payload["require_confirmation"] is True


def test_right_list_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["right", "list"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("list_rights", {"role": None, "resource_type": None, "resource_id": None})


def test_right_rm_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["right", "rm", "r1"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("delete_right", {"id": "r1"})


def test_check_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args([
        "check", "--roles", "admin,everyone", "--resource-type", "odoo_model",
        "--resource-id", "1:project.task", "--operation", "read", "--field", "name", "--confirmed",
    ])
    cli_mod.rights_command(args)
    action, payload = fake_config.calls[0]
    assert action == "check_right"
    assert payload["roles"] == "admin,everyone"
    assert payload["operation"] == "read"
    assert payload["field"] == "name"
    assert payload["confirmed"] is True


def test_whoami_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["whoami", "--platform", "slack", "--user", "U0123"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == (
        "whoami", {"platform": "slack", "user": "U0123", "session_id": None},
    )


def test_call_returns_1_when_result_not_ok(cli_mod, parser, fake_config):
    fake_config.returning({"ok": False, "error": {"code": "X"}})
    args = parser.parse_args(["role", "list"])
    rc = cli_mod.rights_command(args)
    assert rc == 1


def test_call_prints_result_as_json(cli_mod, parser, fake_config, capsys):
    fake_config.returning({"ok": True, "value": 1})
    args = parser.parse_args(["role", "list"])
    cli_mod.rights_command(args)
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"ok": True, "value": 1}


def test_call_converts_connector_error_to_error_dict(cli_mod, parser, monkeypatch, capsys):
    from rights_w_main.errors_manager.errors import NotFoundError

    class RaisingExecutor:
        def execute(self, action, payload):
            raise NotFoundError("nope", {"id": "x"})

    monkeypatch.setattr(cli_mod, "_config", RaisingExecutor())
    args = parser.parse_args(["right", "rm", "missing"])
    rc = cli_mod.rights_command(args)
    assert rc == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Unknown subcommands — usage + exit code 2
# ---------------------------------------------------------------------------


def test_no_subcommand_prints_usage(cli_mod):
    args = argparse.Namespace(rights_command=None)
    rc = cli_mod.rights_command(args)
    assert rc == 2


def test_role_no_sub_subcommand_prints_usage(cli_mod):
    args = argparse.Namespace(rights_command="role", rights_role_command=None)
    rc = cli_mod.rights_command(args)
    assert rc == 2


def test_role_catalog_no_sub_subcommand_prints_usage(cli_mod):
    args = argparse.Namespace(rights_command="role", rights_role_command="catalog", rights_role_catalog_command=None)
    rc = cli_mod.rights_command(args)
    assert rc == 2


def test_right_no_sub_subcommand_prints_usage(cli_mod):
    args = argparse.Namespace(rights_command="right", rights_right_command=None)
    rc = cli_mod.rights_command(args)
    assert rc == 2


def test_directory_no_sub_subcommand_prints_usage(cli_mod):
    args = argparse.Namespace(rights_command="directory", rights_directory_command=None)
    rc = cli_mod.rights_command(args)
    assert rc == 2


# ---------------------------------------------------------------------------
# directory sync/list
# ---------------------------------------------------------------------------


def test_directory_sync_parses_default_platform(parser):
    args = parser.parse_args(["directory", "sync"])
    assert args.platform == "slack"


def test_directory_list_parses_platform_override(parser):
    args = parser.parse_args(["directory", "list", "--platform", "telegram"])
    assert args.platform == "telegram"


def test_directory_sync_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["directory", "sync"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("sync_directory", {"platform": "slack"})


def test_directory_list_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["directory", "list"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("list_directory", {"platform": "slack"})


# ---------------------------------------------------------------------------
# platforms
# ---------------------------------------------------------------------------


def test_platforms_defaults_to_connected_only(parser):
    args = parser.parse_args(["platforms"])
    assert args.include_unconfigured is False


def test_platforms_all_flag(parser):
    args = parser.parse_args(["platforms", "--all"])
    assert args.include_unconfigured is True


def test_platforms_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["platforms"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("list_platforms", {"include_unconfigured": False})


# ---------------------------------------------------------------------------
# role catalog
# ---------------------------------------------------------------------------


def test_role_catalog_create_parses_args(parser):
    args = parser.parse_args(["role", "catalog", "create", "--id", "admin", "--label", "Administrateur", "--description", "Full access"])
    assert args.id == "admin"
    assert args.label == "Administrateur"
    assert args.description == "Full access"


def test_role_catalog_create_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["role", "catalog", "create", "--id", "admin", "--label", "Administrateur"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("save_role", {"id": "admin", "label": "Administrateur", "description": ""})


def test_role_catalog_list_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["role", "catalog", "list"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("list_roles", {})


def test_role_catalog_rm_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["role", "catalog", "rm", "admin"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("delete_role", {"id": "admin"})


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------


def test_tools_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["tools"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("list_hermes_tools", {})


# ---------------------------------------------------------------------------
# mcp-key
# ---------------------------------------------------------------------------


def test_mcp_key_add_parses_args(parser):
    args = parser.parse_args([
        "mcp-key", "add", "--id", "rag_mcp", "--label", "RAG MCP", "--alg", "HS256", "--secret", "s3cret",
    ])
    assert args.id == "rag_mcp"
    assert args.label == "RAG MCP"
    assert args.alg == "HS256"
    assert args.secret == "s3cret"
    assert args.active is True


def test_mcp_key_add_inactive_flag(parser):
    args = parser.parse_args(["mcp-key", "add", "--id", "rag_mcp", "--inactive"])
    assert args.active is False


def test_mcp_key_add_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["mcp-key", "add", "--id", "rag_mcp", "--label", "RAG MCP"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == (
        "save_mcp_signing_key",
        {"id": "rag_mcp", "label": "RAG MCP", "alg": "HS256", "secret": None, "active": True},
    )


def test_mcp_key_list_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["mcp-key", "list"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("list_mcp_signing_keys", {})


def test_mcp_key_reveal_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["mcp-key", "reveal", "rag_mcp"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("reveal_mcp_signing_key", {"id": "rag_mcp"})


def test_mcp_key_rm_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["mcp-key", "rm", "rag_mcp"])
    cli_mod.rights_command(args)
    assert fake_config.calls[0] == ("delete_mcp_signing_key", {"id": "rag_mcp"})


def test_mcp_key_no_sub_subcommand_prints_usage(cli_mod):
    args = argparse.Namespace(rights_command="mcp-key", rights_mcp_key_command=None)
    assert cli_mod.rights_command(args) == 2
