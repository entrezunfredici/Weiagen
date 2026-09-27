"""cli.py (``hermes audit ...``) and tools.py (``audit_search``)."""

import argparse
import json
import time

import pytest

import audit_store


def _parse(cli_mod, argv):
    parser = argparse.ArgumentParser()
    cli_mod.register_cli(parser)
    return parser.parse_args(argv)


def _run(cli_mod, capsys, argv):
    code = cli_mod.audit_command(_parse(cli_mod, argv))
    return code, json.loads(capsys.readouterr().out)


def _seed():
    now = time.time()
    audit_store.append_event(event="tool_call", tool_name="odoo_sdk_read", status="ok",
                             platform="slack", user_id="U1", ts=now - 10 * 86400)
    audit_store.append_event(event="tool_call", tool_name="terminal", status="blocked",
                             platform="slack", user_id="U2", ts=now)


# ----------------------------------------------------------------------- CLI

def test_cli_list_with_filters(cli_mod, capsys):
    _seed()
    code, out = _run(cli_mod, capsys, ["list", "--status", "blocked"])
    assert code == 0
    assert out["count"] == 1
    assert out["events"][0]["tool_name"] == "terminal"
    assert out["events"][0]["time"].endswith("+00:00")

    _, out = _run(cli_mod, capsys, ["list", "--since", "7d"])
    assert [e["user_id"] for e in out["events"]] == ["U2"]


def test_cli_list_invalid_since(cli_mod, capsys):
    code, out = _run(cli_mod, capsys, ["list", "--since", "hier"])
    assert code == 1
    assert "invalid time filter" in out["error"]


def test_cli_stats(cli_mod, capsys):
    _seed()
    code, out = _run(cli_mod, capsys, ["stats"])
    assert code == 0
    assert out["total"] == 2
    assert out["by_status"] == {"ok": 1, "blocked": 1}
    assert out["oldest"] is not None


def test_cli_verify(cli_mod, capsys):
    _seed()
    code, out = _run(cli_mod, capsys, ["verify"])
    assert (code, out) == (0, {"ok": True, "checked": 2})


def test_cli_purge_requires_yes(cli_mod, capsys):
    _seed()
    code, out = _run(cli_mod, capsys, ["purge", "--older-than-days", "5"])
    assert code == 1
    assert len(audit_store.query_events()) == 2

    code, out = _run(cli_mod, capsys, ["purge", "--older-than-days", "5", "--yes"])
    assert (code, out) == (0, {"ok": True, "deleted": 1})


def test_cli_purge_rejects_zero_days(cli_mod, capsys):
    code, _ = _run(cli_mod, capsys, ["purge", "--older-than-days", "0", "--yes"])
    assert code == 1


def test_cli_without_subcommand(cli_mod, capsys):
    assert cli_mod.audit_command(_parse(cli_mod, [])) == 2


# --------------------------------------------------------------------- Tool

@pytest.mark.parametrize("value, expected", [("", False), ("0", False), ("1", True), ("TRUE", True), ("on", True)])
def test_agent_tool_enabled(tools_mod, monkeypatch, value, expected):
    monkeypatch.setenv("AUDIT_AGENT_TOOL_ENABLED", value)
    assert tools_mod.agent_tool_enabled() is expected


def test_audit_search_defaults_to_last_7_days(tools_mod):
    _seed()
    out = json.loads(tools_mod.handle_audit_search({}, task_id="t", session_id="s"))
    assert out["ok"] is True
    assert out["count"] == 1
    event = out["events"][0]
    assert (event["tool"], event["status"], event["user"]) == ("terminal", "blocked", "slack:U2")


def test_audit_search_filters_and_limit(tools_mod):
    _seed()
    out = json.loads(tools_mod.handle_audit_search({"since": "30d", "tool_name": "odoo_*"}))
    assert [e["tool"] for e in out["events"]] == ["odoo_sdk_read"]
    out = json.loads(tools_mod.handle_audit_search({"since": "30d", "limit": "1"}))
    assert out["count"] == 1
    out = json.loads(tools_mod.handle_audit_search({"since": "30d", "limit": "abc"}))
    assert out["count"] == 2


def test_audit_search_invalid_since(tools_mod):
    out = json.loads(tools_mod.handle_audit_search({"since": "last week"}))
    assert out["ok"] is False
    assert out["error"]["code"] == "VALIDATION_ERROR"
