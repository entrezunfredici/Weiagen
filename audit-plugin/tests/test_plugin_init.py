"""audit-plugin/__init__.py — hooks and register()."""

import json

import audit_store


class _FakeCtx:
    def __init__(self):
        self.hooks = {}
        self.tools = []
        self.cli = []

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_tool(self, **kw):
        self.tools.append(kw["name"])

    def register_cli_command(self, **kw):
        self.cli.append(kw["name"])


def test_register_without_agent_tool(audit_plugin_pkg):
    ctx = _FakeCtx()
    audit_plugin_pkg.register(ctx)
    assert set(ctx.hooks) == {"post_tool_call", "post_approval_response"}
    assert ctx.cli == ["audit"]
    assert ctx.tools == []


def test_register_with_agent_tool(audit_plugin_pkg, monkeypatch):
    monkeypatch.setenv("AUDIT_AGENT_TOOL_ENABLED", "true")
    ctx = _FakeCtx()
    audit_plugin_pkg.register(ctx)
    assert ctx.tools == ["audit_search"]


def test_post_tool_call_records_ok_call_with_identity(audit_plugin_pkg, fake_sessions):
    fake_sessions["s1"] = {"source": "slack", "user_id": "U42"}
    ret = audit_plugin_pkg._post_tool_call(
        tool_name="odoo_sdk_update",
        args={"model": "project.task", "values": {"name": "x"}, "caller_token": "secret-token"},
        result='{"ok": true}',
        task_id="t1", session_id="s1", tool_call_id="c1", turn_id="turn1",
        duration_ms=12, status="ok", telemetry_schema_version=1, api_request_id="r", middleware_trace=[],
    )
    assert ret is None
    (e,) = audit_store.query_events()
    assert (e["event"], e["tool_name"], e["status"]) == ("tool_call", "odoo_sdk_update", "ok")
    assert (e["platform"], e["user_id"]) == ("slack", "U42")
    assert (e["session_id"], e["tool_call_id"], e["turn_id"], e["duration_ms"]) == ("s1", "c1", "turn1", 12)
    assert e["args"]["caller_token"] == "[REDACTED]"
    assert e["args"]["values"] == {"name": "x"}
    assert e["result_size"] == len('{"ok": true}')


def test_post_tool_call_records_rights_block(audit_plugin_pkg):
    audit_plugin_pkg._post_tool_call(
        tool_name="terminal", args={"command": "rm -rf /"}, result='{"error": "Blocked by rights-plugin: no"}',
        status="blocked", error_type="plugin_block", error_message="Blocked by rights-plugin: no",
    )
    (e,) = audit_store.query_events(status="blocked")
    assert e["error_type"] == "plugin_block"
    assert e["error_message"] == "Blocked by rights-plugin: no"
    # No session -> identity left empty rather than guessed.
    assert (e["platform"], e["user_id"]) == ("", "")


def test_post_tool_call_defaults_status_ok(audit_plugin_pkg):
    audit_plugin_pkg._post_tool_call(tool_name="x")
    assert audit_store.query_events()[0]["status"] == "ok"


def test_post_tool_call_non_string_result_size(audit_plugin_pkg):
    audit_plugin_pkg._post_tool_call(tool_name="x", result={"a": 1})
    assert audit_store.query_events()[0]["result_size"] == len(json.dumps({"a": 1}))


def test_post_tool_call_never_raises(audit_plugin_pkg, monkeypatch):
    def boom(**_):
        raise RuntimeError("disk full")

    monkeypatch.setattr(audit_store, "append_event", boom)
    assert audit_plugin_pkg._post_tool_call(tool_name="x") is None


def test_unknown_session_leaves_identity_empty(audit_plugin_pkg, fake_sessions):
    audit_plugin_pkg._post_tool_call(tool_name="x", session_id="missing")
    e = audit_store.query_events()[0]
    assert (e["platform"], e["user_id"], e["session_id"]) == ("", "", "missing")


def test_post_approval_response_plugin_rule(audit_plugin_pkg):
    audit_plugin_pkg._post_approval_response(
        command="<odoo_sdk_delete> (plugin approval rule)",
        description="Delete requires confirmation",
        pattern_key="plugin_rule:rights:odoo_model:default:project.task:delete",
        pattern_keys=["..."], session_key="agent:main:slack:dm:U42", surface="gateway",
        choice="once", turn_id="turn1", tool_call_id="c9",
    )
    (e,) = audit_store.query_events(event="approval")
    assert (e["tool_name"], e["status"], e["tool_call_id"]) == ("odoo_sdk_delete", "once", "c9")
    assert e["args"]["surface"] == "gateway"
    assert e["args"]["decided_by"] == "human"


def test_post_approval_response_shell_command_and_smart(audit_plugin_pkg):
    audit_plugin_pkg._post_approval_response(
        command="rm -rf /tmp/x", description="recursive delete", pattern_key="rm_rf",
        surface="smart", choice="smart_deny", decided_by="aux_llm",
    )
    (e,) = audit_store.query_events(event="approval")
    assert e["tool_name"] == ""
    assert e["status"] == "smart_deny"
    assert e["args"]["command"] == "rm -rf /tmp/x"
    assert e["args"]["decided_by"] == "aux_llm"


def test_post_approval_response_never_raises(audit_plugin_pkg, monkeypatch):
    monkeypatch.setattr(audit_store, "append_event", lambda **_: 1 / 0)
    assert audit_plugin_pkg._post_approval_response(choice="deny") is None


def test_identity_is_cached(audit_plugin_pkg, fake_sessions):
    fake_sessions["s1"] = {"source": "slack", "user_id": "U1"}
    audit_plugin_pkg._post_tool_call(tool_name="a", session_id="s1")
    fake_sessions.clear()
    audit_plugin_pkg._post_tool_call(tool_name="b", session_id="s1")
    assert [e["user_id"] for e in audit_store.query_events()] == ["U1", "U1"]
