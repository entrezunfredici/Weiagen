"""odoo_plugin/cli.py — `hermes odoo` argparse tree + dispatch.

Loaded through the ``cli_mod`` fixture (see tests/conftest.py), which goes
through the real plugin-loading path.
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

def test_profile_add_parses_required_args(parser):
    args = parser.parse_args([
        "profile", "add", "p1", "--base-url", "https://x", "--database", "db",
        "--login", "l", "--password", "pw",
    ])
    assert args.id == "p1"
    assert args.base_url == "https://x"
    assert args.port == 443
    assert args.disabled is False


def test_profile_add_disabled_flag(parser):
    args = parser.parse_args([
        "profile", "add", "p1", "--base-url", "https://x", "--database", "db",
        "--login", "l", "--password", "pw", "--disabled",
    ])
    assert args.disabled is True


def test_right_list_parses_optional_profile_filter(parser):
    args = parser.parse_args(["right", "list"])
    assert args.profile_id is None
    args = parser.parse_args(["right", "list", "--profile-id", "p1"])
    assert args.profile_id == "p1"


# ---------------------------------------------------------------------------
# dispatch (odoo_command)
# ---------------------------------------------------------------------------

def test_profile_add_dispatches_save_profile(cli_mod, parser, fake_config, capsys):
    fake_config.returning({"ok": True, "profile": {"id": "p1"}})
    args = parser.parse_args([
        "profile", "add", "p1", "--base-url", "https://x", "--database", "db",
        "--login", "l", "--password", "pw",
    ])
    rc = cli_mod.odoo_command(args)
    assert rc == 0
    assert fake_config.calls[0][0] == "save_profile"
    assert fake_config.calls[0][1]["id"] == "p1"
    assert fake_config.calls[0][1]["enabled"] is True


def test_profile_add_disabled_maps_to_enabled_false(cli_mod, parser, fake_config):
    args = parser.parse_args([
        "profile", "add", "p1", "--base-url", "https://x", "--database", "db",
        "--login", "l", "--password", "pw", "--disabled",
    ])
    cli_mod.odoo_command(args)
    assert fake_config.calls[0][1]["enabled"] is False


def test_profile_list_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["profile", "list"])
    cli_mod.odoo_command(args)
    assert fake_config.calls[0] == ("list_profiles", {})


def test_profile_rm_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["profile", "rm", "p1"])
    cli_mod.odoo_command(args)
    assert fake_config.calls[0] == ("delete_profile", {"id": "p1"})


def test_right_list_dispatches(cli_mod, parser, fake_config):
    args = parser.parse_args(["right", "list"])
    cli_mod.odoo_command(args)
    assert fake_config.calls[0] == ("list_rights", {"profile_id": None})


def test_right_list_dispatches_with_profile_filter(cli_mod, parser, fake_config):
    args = parser.parse_args(["right", "list", "--profile-id", "p1"])
    cli_mod.odoo_command(args)
    assert fake_config.calls[0] == ("list_rights", {"profile_id": "p1"})


def test_call_returns_1_when_result_not_ok(cli_mod, parser, fake_config):
    fake_config.returning({"ok": False, "error": {"code": "X"}})
    args = parser.parse_args(["profile", "list"])
    rc = cli_mod.odoo_command(args)
    assert rc == 1


def test_call_prints_result_as_json(cli_mod, parser, fake_config, capsys):
    fake_config.returning({"ok": True, "value": 1})
    args = parser.parse_args(["profile", "list"])
    cli_mod.odoo_command(args)
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"ok": True, "value": 1}


def test_call_converts_connector_error_to_error_dict(cli_mod, parser, monkeypatch, capsys):
    from w_main.errors_manager.errors import NotFoundError

    class RaisingExecutor:
        def execute(self, action, payload):
            raise NotFoundError("nope", {"id": "x"})

    monkeypatch.setattr(cli_mod, "_config", RaisingExecutor())
    args = parser.parse_args(["profile", "rm", "missing"])
    rc = cli_mod.odoo_command(args)
    assert rc == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Unknown subcommands — usage + exit code 2
# ---------------------------------------------------------------------------

def test_no_subcommand_prints_usage(cli_mod):
    args = argparse.Namespace(odoo_command=None)
    rc = cli_mod.odoo_command(args)
    assert rc == 2


def test_profile_no_sub_subcommand_prints_usage(cli_mod):
    args = argparse.Namespace(odoo_command="profile", odoo_profile_command=None)
    rc = cli_mod.odoo_command(args)
    assert rc == 2


def test_right_no_sub_subcommand_prints_usage(cli_mod):
    args = argparse.Namespace(odoo_command="right", odoo_right_command=None)
    rc = cli_mod.odoo_command(args)
    assert rc == 2
