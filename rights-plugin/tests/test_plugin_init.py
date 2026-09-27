"""rights_plugin/__init__.py — pre_tool_call/pre_llm_call hooks + register()."""

import pytest

import directory
import token_signer
from models import bind_role, create_access_right

# ---------------------------------------------------------------------------
# _pre_tool_call
# ---------------------------------------------------------------------------


def test_no_right_configured_for_tool_returns_none(rights_plugin_pkg):
    # Safety gate: enabling the plugin with zero rights for a tool must
    # never start gating it by surprise.
    assert rights_plugin_pkg._pre_tool_call("shell_exec", {"cmd": "ls"}) is None


def test_right_without_confirmation_returns_none(rights_plugin_pkg):
    # No session_id -> resolves to the automation pseudo-identity, which
    # always carries "everyone" -> a right bound to "everyone" applies.
    create_access_right(["everyone"], "hermes_tool", "shell_exec", execute=True)
    assert rights_plugin_pkg._pre_tool_call("shell_exec", {"cmd": "ls"}) is None


def test_right_requiring_confirmation_returns_approve_directive(rights_plugin_pkg):
    create_access_right(["everyone"], "hermes_tool", "shell_exec", execute=True, confirm_execute=True)
    result = rights_plugin_pkg._pre_tool_call("shell_exec", {"cmd": "ls"})
    assert result is not None
    assert result["action"] == "approve"
    assert "shell_exec" in result["message"]
    # rule_key includes the operation (not just resource_type:resource_id,
    # as before 2026-08-19) — matters for hermes_cron, where the same
    # resource ("*") can be create/read/update/delete on different calls;
    # an "always approve" decision must not silently cover every operation.
    assert result["rule_key"] == "rights:hermes_tool:shell_exec:execute"


def test_right_denying_execute_returns_block_directive(rights_plugin_pkg):
    # A right exists for this tool (satisfies the safety gate) but denies
    # execute -> real hard deny, not a fake approval escalation.
    create_access_right(["everyone"], "hermes_tool", "shell_exec", execute=False)
    result = rights_plugin_pkg._pre_tool_call("shell_exec", {"cmd": "ls"})
    assert result is not None
    assert result["action"] == "block"
    assert "shell_exec" in result["message"]


def test_wildcard_resource_right_governs_every_tool(rights_plugin_pkg):
    create_access_right(["everyone"], "hermes_tool", "*", execute=False)
    result = rights_plugin_pkg._pre_tool_call("any_tool_name", {})
    assert result is not None
    assert result["action"] == "block"


def test_role_bound_identity_via_session_resolves_correctly(rights_plugin_pkg, fake_sessions):
    fake_sessions["sess-1"] = {"source": "slack", "user_id": "U0123"}
    bind_role("slack", "U0123", ["admin"])
    create_access_right(["admin"], "hermes_tool", "shell_exec", execute=True)
    result = rights_plugin_pkg._pre_tool_call("shell_exec", {"cmd": "ls"}, session_id="sess-1")
    assert result is None  # allowed, no confirmation needed


def test_role_not_granted_via_session_is_blocked(rights_plugin_pkg, fake_sessions):
    fake_sessions["sess-1"] = {"source": "slack", "user_id": "U0123"}
    # No binding for U0123 -> only "everyone" applies, and "everyone" has no right here.
    create_access_right(["admin"], "hermes_tool", "shell_exec", execute=True)
    result = rights_plugin_pkg._pre_tool_call("shell_exec", {"cmd": "ls"}, session_id="sess-1")
    assert result is not None
    assert result["action"] == "block"


def test_right_for_one_tool_now_gates_every_other_tool_too(rights_plugin_pkg):
    # Real bug caught in production 2026-08-19 (see .agents/DECISIONS.md):
    # the safety gate used to check has_any_right_for(resource_type,
    # (resource_id, "*")) -- scoped to the ONE tool being called -- so
    # narrowing an existing hermes_tool "*" right down to a single tool
    # (e.g. picking one from the dashboard's new tool picker) silently
    # left every *other* tool ungated forever. Once ANY hermes_tool right
    # exists, every tool call must be evaluated for real, not just the one
    # tool that happens to have a right.
    create_access_right(["everyone"], "hermes_tool", "odoo_sdk_read", execute=True)
    # The configured tool is still allowed...
    assert rights_plugin_pkg._pre_tool_call("odoo_sdk_read", {}) is None
    # ...but any other tool, previously ungated by the old per-resource_id
    # safety gate, must now be blocked -- no right covers it.
    for other_tool in ("terminal", "execute_code", "delegate_task"):
        result = rights_plugin_pkg._pre_tool_call(other_tool, {})
        assert result is not None, f"{other_tool} should now be blocked, was ungated"
        assert result["action"] == "block"


# ---------------------------------------------------------------------------
# _pre_tool_call — "cronjob" redirected to resource_type="hermes_cron" with
# a real CRUD operation derived from args["action"] (see
# .agents/DECISIONS.md, 2026-08-19 — hermes_cron has no dedicated Hermes
# hook, this is the only enforcement point available).
# ---------------------------------------------------------------------------


def test_cronjob_no_right_configured_is_blocked(rights_plugin_pkg):
    # Unlike hermes_tool, hermes_cron does NOT get the "zero rights
    # configured -> ungated" bootstrap leniency (see .agents/DECISIONS.md,
    # 2026-08-19 — caught in production: cron creation must be denied
    # until an operator explicitly grants it, a cron job is a materially
    # more sensitive capability than a single tool call).
    result = rights_plugin_pkg._pre_tool_call("cronjob", {"action": "create"})
    assert result is not None
    assert result["action"] == "block"


@pytest.mark.parametrize("cron_action,operation", [
    ("create", "create"),
    ("list", "read"),
    ("update", "update"),
    ("pause", "update"),
    ("resume", "update"),
    ("remove", "delete"),
])
def test_cronjob_action_maps_to_the_right_crud_operation(rights_plugin_pkg, cron_action, operation):
    kwargs = {operation: True}
    create_access_right(["everyone"], "hermes_cron", "*", **kwargs)
    result = rights_plugin_pkg._pre_tool_call("cronjob", {"action": cron_action})
    assert result is None  # allowed, no confirmation required


def test_cronjob_unmapped_action_defaults_to_read(rights_plugin_pkg):
    create_access_right(["everyone"], "hermes_cron", "*", read=True, delete=False)
    # An action string the plugin doesn't recognize falls back to "read" —
    # the least destructive verb — rather than "execute" (meaningless here)
    # or silently allowing.
    result = rights_plugin_pkg._pre_tool_call("cronjob", {"action": "something_new"})
    assert result is None


def test_cronjob_action_case_and_whitespace_insensitive(rights_plugin_pkg):
    create_access_right(["everyone"], "hermes_cron", "*", create=True)
    result = rights_plugin_pkg._pre_tool_call("cronjob", {"action": "  Create  "})
    assert result is None


def test_cronjob_missing_args_defaults_to_read_not_a_crash(rights_plugin_pkg):
    create_access_right(["everyone"], "hermes_cron", "*", read=True)
    result = rights_plugin_pkg._pre_tool_call("cronjob", None)
    assert result is None


def test_cronjob_create_denied_returns_block(rights_plugin_pkg):
    create_access_right(["everyone"], "hermes_cron", "*", create=False)
    result = rights_plugin_pkg._pre_tool_call("cronjob", {"action": "create"})
    assert result is not None
    assert result["action"] == "block"


def test_cronjob_remove_requiring_confirmation_returns_approve(rights_plugin_pkg):
    create_access_right(["everyone"], "hermes_cron", "*", delete=True, confirm_delete=True)
    result = rights_plugin_pkg._pre_tool_call("cronjob", {"action": "remove"})
    assert result is not None
    assert result["action"] == "approve"
    assert result["rule_key"] == "rights:hermes_cron:*:delete"


def test_cronjob_create_right_does_not_grant_list(rights_plugin_pkg):
    # A right that only allows "create" must not silently allow "list" too
    # — real CRUD, each operation independently gated.
    create_access_right(["everyone"], "hermes_cron", "*", create=True, read=False)
    result = rights_plugin_pkg._pre_tool_call("cronjob", {"action": "list"})
    assert result is not None
    assert result["action"] == "block"


def test_hermes_tool_right_on_cronjob_no_longer_governs_cronjob_calls(rights_plugin_pkg):
    # A "hermes_tool"/"cronjob" right (the old, pre-2026-08-19 way to try
    # gating cron access) is now dead — cronjob calls are redirected to
    # "hermes_cron" and never consult "hermes_tool" rights at all, even a
    # denying one.
    create_access_right(["everyone"], "hermes_tool", "cronjob", execute=False)
    result = rights_plugin_pkg._pre_tool_call("cronjob", {"action": "create"})
    # No hermes_cron right exists -> blocked (hermes_cron has no bootstrap
    # safety gate, see test_cronjob_no_right_configured_is_blocked) — the
    # point of this test is just that the *reason* comes from hermes_cron
    # having nothing, not from the (irrelevant) hermes_tool right above.
    assert result is not None
    assert result["action"] == "block"
    assert "hermes_cron" in result["message"]


# ---------------------------------------------------------------------------
# _pre_llm_call
# ---------------------------------------------------------------------------


def test_pre_llm_call_injects_identity_context(rights_plugin_pkg):
    bind_role("slack", "U0123", ["admin"])
    result = rights_plugin_pkg._pre_llm_call(platform="slack", sender_id="U0123")
    assert result is not None
    assert "context" in result
    assert "platform=slack" in result["context"]
    assert "user=U0123" in result["context"]
    assert "admin" in result["context"]


def test_pre_llm_call_never_blocks_even_with_denying_rights(rights_plugin_pkg):
    create_access_right(["everyone"], "hermes_tool", "shell_exec", execute=False)
    result = rights_plugin_pkg._pre_llm_call(platform="slack", sender_id="U9")
    assert "action" not in (result or {})
    assert "context" in result


def test_pre_llm_call_falls_back_to_automation_context_when_unresolved(rights_plugin_pkg):
    result = rights_plugin_pkg._pre_llm_call()
    assert result is not None
    assert "platform=automation" in result["context"]
    assert "automation" in result["context"]


def test_pre_llm_call_omits_mcp_token_lines_when_no_key_configured(rights_plugin_pkg, monkeypatch):
    # No MCP signing key in the registry (conftest's per-test reset leaves
    # it empty) -> issue_mcp_identity_tokens returns [] -> no extra line.
    monkeypatch.setattr(token_signer, "issue_mcp_identity_tokens", lambda **kw: [])
    result = rights_plugin_pkg._pre_llm_call(platform="slack", sender_id="U9")
    assert "mcp_identity_token" not in result["context"]


def test_pre_llm_call_appends_one_line_per_issued_token(rights_plugin_pkg, monkeypatch):
    bind_role("slack", "U0123", ["manager"])
    monkeypatch.setattr(
        token_signer, "issue_mcp_identity_tokens",
        lambda **kw: [
            {"kid": "rag_mcp", "label": "RAG MCP", "token": "fake.token.a"},
            {"kid": "odoo_reports_mcp", "label": "", "token": "fake.token.b"},
        ],
    )
    result = rights_plugin_pkg._pre_llm_call(platform="slack", sender_id="U0123")
    assert "[mcp_identity_token kid=rag_mcp label=RAG MCP] fake.token.a" in result["context"]
    assert "[mcp_identity_token kid=odoo_reports_mcp] fake.token.b" in result["context"]


def test_pre_llm_call_token_instructions_name_the_mcp_tool_prefix(rights_plugin_pkg, monkeypatch):
    # 2026-09-22: a model mixed up which kid's token belongs to which MCP server (one server's
    # token rejected by another with "alg not allowed") — the instruction now spells out the exact
    # `mcp__<kid>__*` prefix the model already sees in its own tool list, not just "the tool whose
    # schema names this kid" (see .agents/DECISIONS.md).
    bind_role("slack", "U0123", ["manager"])
    monkeypatch.setattr(
        token_signer, "issue_mcp_identity_tokens",
        lambda **kw: [{"kid": "sandbox", "label": "sandbox-runner", "token": "fake.token.a"}],
    )
    result = rights_plugin_pkg._pre_llm_call(platform="slack", sender_id="U0123")
    assert "mcp__sandbox__*" in result["context"]
    assert "never for a tool from a different MCP server" in result["context"]
    # Still carries the plain-text identity line above it, unchanged.
    assert "[identity] platform=slack user=U0123" in result["context"]


def test_pre_llm_call_passes_resolved_identity_to_the_signer(rights_plugin_pkg, monkeypatch):
    bind_role("slack", "U0123", ["manager"])
    calls = []
    monkeypatch.setattr(
        token_signer, "issue_mcp_identity_tokens",
        lambda **kw: calls.append(kw) or [],
    )
    rights_plugin_pkg._pre_llm_call(platform="slack", sender_id="U0123")
    assert calls == [{"platform": "slack", "external_user_id": "U0123", "roles": ["everyone", "manager"]}]


def test_pre_llm_call_triggers_lazy_directory_refresh(rights_plugin_pkg, monkeypatch):
    calls = []
    monkeypatch.setattr(directory, "ensure_fresh", lambda platform, **kw: calls.append(platform))
    rights_plugin_pkg._pre_llm_call(platform="slack", sender_id="U9")
    assert calls == ["slack"]


def test_pre_llm_call_never_raises_when_directory_refresh_breaks_its_own_contract(rights_plugin_pkg, monkeypatch):
    # ensure_fresh is documented to never raise, but this hook must not
    # trust that blindly forever — if it ever regresses, a chat turn must
    # still not go down with it. (No try/except left in _pre_llm_call
    # itself today — see its docstring — so this pins the *contract*, not
    # an extra defensive layer; if this test starts failing, either
    # ensure_fresh broke its guarantee or the hook needs its own guard back.)
    def _raise(platform, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(directory, "ensure_fresh", _raise)
    with pytest.raises(RuntimeError):
        rights_plugin_pkg._pre_llm_call(platform="slack", sender_id="U9")


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


class _FakeCtx:
    def __init__(self):
        self.registered_cli = []
        self.registered_hooks = []

    def register_cli_command(self, *, name, help, setup_fn, handler_fn, description):
        self.registered_cli.append(name)

    def register_hook(self, hook_name, fn):
        self.registered_hooks.append(hook_name)


def test_register_registers_the_cli_and_both_hooks(rights_plugin_pkg):
    ctx = _FakeCtx()
    rights_plugin_pkg.register(ctx)
    assert ctx.registered_cli == ["rights"]
    assert ctx.registered_hooks == ["pre_tool_call", "pre_llm_call"]
