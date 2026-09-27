"""rights_plugin.config_executor.RightsConfigExecutor — action dispatch."""

import pytest

import slack_directory
from config_executor import RightsConfigExecutor
from rights_w_main.errors_manager.errors import ConfigurationError, ValidationError


@pytest.fixture
def config():
    return RightsConfigExecutor()


def test_unknown_action_raises_validation_error(config):
    with pytest.raises(ValidationError):
        config.execute("bogus", {})


# ---------------------------------------------------------------------------
# Role bindings
# ---------------------------------------------------------------------------


def test_bind_role_requires_platform_and_user(config):
    with pytest.raises(ValidationError):
        config.execute("bind_role", {"platform": "slack"})
    with pytest.raises(ValidationError):
        config.execute("bind_role", {"user": "U1"})


def test_bind_role_success(config):
    result = config.execute("bind_role", {"platform": "slack", "user": "U0123", "roles": "admin,finance"})
    assert result["ok"] is True
    assert result["role_binding"]["roles"] == ["admin", "finance"]
    assert result["role_binding"]["id"] == "slack:U0123"


def test_bind_role_accepts_roles_as_list():
    config = RightsConfigExecutor()
    result = config.execute("bind_role", {"platform": "slack", "user": "U1", "roles": ["a", "b"]})
    assert result["role_binding"]["roles"] == ["a", "b"]


def test_unbind_role_requires_platform_and_user(config):
    with pytest.raises(ValidationError):
        config.execute("unbind_role", {})


def test_unbind_role_success(config):
    config.execute("bind_role", {"platform": "slack", "user": "U1", "roles": "admin"})
    result = config.execute("unbind_role", {"platform": "slack", "user": "U1"})
    assert result["deleted"] is True


def test_list_role_bindings_unfiltered(config):
    config.execute("bind_role", {"platform": "slack", "user": "U1", "roles": "a"})
    config.execute("bind_role", {"platform": "telegram", "user": "42", "roles": "b"})
    result = config.execute("list_role_bindings", {})
    assert result["count"] == 2


def test_list_role_bindings_filtered_by_platform(config):
    config.execute("bind_role", {"platform": "slack", "user": "U1", "roles": "a"})
    config.execute("bind_role", {"platform": "telegram", "user": "42", "roles": "b"})
    result = config.execute("list_role_bindings", {"platform": "slack"})
    assert result["count"] == 1


def test_list_role_bindings_filtered_by_user(config):
    config.execute("bind_role", {"platform": "slack", "user": "U1", "roles": "a"})
    config.execute("bind_role", {"platform": "slack", "user": "U2", "roles": "b"})
    result = config.execute("list_role_bindings", {"user": "U2"})
    assert result["count"] == 1


# ---------------------------------------------------------------------------
# Access rights
# ---------------------------------------------------------------------------


def test_save_right_requires_roles_resource_type_and_id(config):
    with pytest.raises(ValidationError):
        config.execute("save_right", {"roles": "admin"})


def test_save_right_fields_accepts_comma_separated_string(config):
    result = config.execute("save_right", {
        "roles": "admin", "resource_type": "odoo_model", "resource_id": "1:res.partner",
        "fields": "name, email , vat",
    })
    assert result["right"]["fields"] == ["name", "email", "vat"]


def test_save_right_fields_defaults_to_wildcard_when_empty(config):
    result = config.execute("save_right", {
        "roles": "admin", "resource_type": "odoo_model", "resource_id": "1:res.partner", "fields": "",
    })
    assert result["right"]["fields"] == ["*"]


def test_save_right_defaults_read_true_others_false(config):
    result = config.execute("save_right", {"roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec"})
    right = result["right"]
    assert right["read"] is True
    assert right["create"] is False
    assert right["execute"] is False


def test_save_right_accepts_several_roles(config):
    result = config.execute("save_right", {"roles": "admin,finance", "resource_type": "hermes_tool", "resource_id": "shell_exec"})
    assert result["right"]["roles"] == ["admin", "finance"]


def test_list_rights_filtered_by_role(config):
    config.execute("save_right", {"roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec"})
    config.execute("save_right", {"roles": "everyone", "resource_type": "hermes_tool", "resource_id": "shell_exec"})
    result = config.execute("list_rights", {"role": "admin"})
    assert result["count"] == 1


def test_list_rights_filtered_by_role_matches_a_right_bound_to_several_roles(config):
    config.execute("save_right", {"roles": "admin,finance", "resource_type": "hermes_tool", "resource_id": "shell_exec"})
    result = config.execute("list_rights", {"role": "finance"})
    assert result["count"] == 1


def test_list_rights_filtered_by_resource_type(config):
    config.execute("save_right", {"roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec"})
    config.execute("save_right", {"roles": "admin", "resource_type": "odoo_model", "resource_id": "1:project.task"})
    result = config.execute("list_rights", {"resource_type": "odoo_model"})
    assert result["count"] == 1


def test_delete_right_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("delete_right", {})


def test_delete_right_success(config):
    saved = config.execute("save_right", {"id": "r1", "roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec"})
    result = config.execute("delete_right", {"id": saved["right"]["id"]})
    assert result["deleted"] is True


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


def test_check_right_requires_resource_type_id_and_operation(config):
    with pytest.raises(ValidationError):
        config.execute("check_right", {"roles": "admin"})


def test_check_right_allowed(config):
    config.execute("save_right", {"roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec", "execute": True})
    result = config.execute("check_right", {
        "roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec", "operation": "execute",
    })
    assert result["allowed"] is True
    assert result["is_ready"] is True


def test_check_right_requiring_confirmation_not_ready_unless_confirmed(config):
    config.execute("save_right", {
        "roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec",
        "execute": True, "confirm_execute": True,
    })
    result = config.execute("check_right", {
        "roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec", "operation": "execute",
    })
    assert result["allowed"] is True
    assert result["require_confirmation"] is True
    assert result["is_ready"] is False

    confirmed_result = config.execute("check_right", {
        "roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec",
        "operation": "execute", "confirmed": True,
    })
    assert confirmed_result["is_ready"] is True


def test_check_right_defaults_roles_to_everyone_when_omitted(config):
    config.execute("save_right", {"roles": "everyone", "resource_type": "hermes_tool", "resource_id": "shell_exec", "execute": True})
    result = config.execute("check_right", {
        "resource_type": "hermes_tool", "resource_id": "shell_exec", "operation": "execute",
    })
    assert result["allowed"] is True


def test_whoami_requires_session_id_or_platform_and_user(config):
    with pytest.raises(ValidationError):
        config.execute("whoami", {})
    with pytest.raises(ValidationError):
        config.execute("whoami", {"platform": "slack"})


def test_whoami_resolves_direct_identity(config):
    config.execute("bind_role", {"platform": "slack", "user": "U0123", "roles": "admin"})
    result = config.execute("whoami", {"platform": "slack", "user": "U0123"})
    assert result["platform"] == "slack"
    assert result["external_user_id"] == "U0123"
    assert "admin" in result["roles"]
    assert "everyone" in result["roles"]


# ---------------------------------------------------------------------------
# Identity directory
# ---------------------------------------------------------------------------


def test_list_directory_defaults_to_slack_and_never_raises(config):
    # No SLACK_BOT_TOKEN in the test environment (conftest pops it) — the
    # best-effort lazy refresh inside must swallow that, not bubble up.
    result = config.execute("list_directory", {})
    assert result["ok"] is True
    assert result["platform"] == "slack"
    assert result["directory"] == []
    assert result["synced_at"] == 0


def test_list_directory_returns_cached_entries(config, monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setattr(
        slack_directory, "fetch_slack_members",
        lambda token: [{"external_user_id": "U1", "display_name": "Fred"}],
    )
    result = config.execute("list_directory", {"platform": "slack"})
    assert result["count"] == 1
    assert result["directory"][0]["external_user_id"] == "U1"
    assert result["synced_at"] > 0


def test_sync_directory_raises_loudly_when_token_missing(config):
    with pytest.raises(ConfigurationError):
        config.execute("sync_directory", {"platform": "slack"})


def test_sync_directory_success(config, monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.setattr(
        slack_directory, "fetch_slack_members",
        lambda token: [{"external_user_id": "U1", "display_name": "Fred"}],
    )
    result = config.execute("sync_directory", {"platform": "slack"})
    assert result["ok"] is True
    assert result["count"] == 1


# ---------------------------------------------------------------------------
# Connected platforms
# ---------------------------------------------------------------------------


def test_list_platforms_defaults_to_connected_only(config, monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-fake")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    result = config.execute("list_platforms", {})
    slugs = {p["slug"] for p in result["platforms"]}
    assert "slack" in slugs
    assert "telegram" not in slugs


def test_list_platforms_include_unconfigured(config, monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    result = config.execute("list_platforms", {"include_unconfigured": True})
    slugs = {p["slug"] for p in result["platforms"]}
    assert "slack" in slugs  # present even though not configured
    slack = next(p for p in result["platforms"] if p["slug"] == "slack")
    assert slack["configured"] is False


# ---------------------------------------------------------------------------
# Role catalog
# ---------------------------------------------------------------------------


def test_save_role_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("save_role", {"label": "Administrateur"})


def test_save_role_success(config):
    result = config.execute("save_role", {"id": "admin", "label": "Administrateur", "description": "Full access"})
    assert result["ok"] is True
    assert result["role"] == {"id": "admin", "label": "Administrateur", "description": "Full access"}


def test_save_role_upserts_by_id(config):
    config.execute("save_role", {"id": "admin", "label": "First"})
    config.execute("save_role", {"id": "admin", "label": "Second"})
    result = config.execute("list_roles", {})
    assert result["count"] == 1
    assert result["roles"][0]["label"] == "Second"


def test_list_roles(config):
    config.execute("save_role", {"id": "admin", "label": "Administrateur"})
    config.execute("save_role", {"id": "finance", "label": "Finance"})
    result = config.execute("list_roles", {})
    assert {r["id"] for r in result["roles"]} == {"admin", "finance"}
    assert result["count"] == 2


def test_delete_role_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("delete_role", {})


def test_delete_role_success(config):
    config.execute("save_role", {"id": "admin"})
    result = config.execute("delete_role", {"id": "admin"})
    assert result["deleted"] is True
    assert config.execute("list_roles", {})["count"] == 0


def test_delete_role_reports_still_referenced_by_bindings_and_rights(config):
    config.execute("save_role", {"id": "admin"})
    config.execute("bind_role", {"platform": "slack", "user": "U1", "roles": "admin"})
    config.execute("save_right", {"roles": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec"})
    result = config.execute("delete_role", {"id": "admin"})
    # Not blocked — roles are opaque strings, not a hard foreign key — but
    # the caller is told what still references it.
    assert result["deleted"] is True
    assert result["still_referenced_by"] == {"role_bindings": 1, "rights": 1}


def test_delete_role_reports_zero_when_unreferenced(config):
    config.execute("save_role", {"id": "unused"})
    result = config.execute("delete_role", {"id": "unused"})
    assert result["still_referenced_by"] == {"role_bindings": 0, "rights": 0}


# ---------------------------------------------------------------------------
# Hermes tool catalog
# ---------------------------------------------------------------------------


def test_list_hermes_tools_empty_when_real_registry_unavailable(config):
    # No real tools.registry in this test environment (see
    # tests/test_tools_catalog.py) — must degrade gracefully, not raise.
    result = config.execute("list_hermes_tools", {})
    assert result["ok"] is True
    assert result["tools"] == []
    assert result["count"] == 0


def test_list_hermes_tools_shapes_a_fake_registry(config, monkeypatch):
    import sys
    import types

    class _FakeEntry:
        toolset = "terminal"
        description = "Run a shell command"

    class _FakeRegistry:
        def get_all_tool_names(self):
            return ["shell_exec"]

        def get_entry(self, name):
            return _FakeEntry()

    fake_module = types.ModuleType("tools.registry")
    fake_module.registry = _FakeRegistry()
    monkeypatch.setitem(sys.modules, "tools.registry", fake_module)

    result = config.execute("list_hermes_tools", {})
    assert result["count"] == 1
    assert result["tools"][0]["name"] == "shell_exec"


# ---------------------------------------------------------------------------
# MCP signing keys (see models.McpSigningKey / token_signer.py)
# ---------------------------------------------------------------------------


def test_save_mcp_signing_key_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("save_mcp_signing_key", {"label": "RAG MCP"})


def test_save_mcp_signing_key_rejects_unsupported_alg(config):
    with pytest.raises(ValidationError):
        config.execute("save_mcp_signing_key", {"id": "rag_mcp", "alg": "RS256"})


def test_save_mcp_signing_key_accepts_eddsa(config):
    # EdDSA became supported 2026-09-22 (see .agents/DECISIONS.md) — auto-generated secret (a
    # base64url-encoded 32-byte seed, same shape HS256 already used) must be a valid Ed25519 seed.
    result = config.execute("save_mcp_signing_key", {"id": "sandbox", "alg": "EdDSA"})
    assert result["ok"] is True
    assert result["mcp_signing_key"]["alg"] == "EDDSA"


def test_save_mcp_signing_key_auto_generates_a_secret_when_omitted(config):
    result = config.execute("save_mcp_signing_key", {"id": "rag_mcp", "label": "RAG MCP"})
    assert result["ok"] is True
    key = result["mcp_signing_key"]
    assert key["id"] == "rag_mcp"
    assert key["alg"] == "HS256"
    assert key["active"] is True
    assert len(key["secret"]) > 10  # revealed, unmasked, on the create response


def test_save_mcp_signing_key_accepts_an_explicit_secret(config):
    result = config.execute("save_mcp_signing_key", {"id": "rag_mcp", "secret": "my-own-secret"})
    assert result["mcp_signing_key"]["secret"] == "my-own-secret"


def test_save_mcp_signing_key_upserts_by_id(config):
    config.execute("save_mcp_signing_key", {"id": "rag_mcp", "label": "First", "secret": "s1"})
    result = config.execute("save_mcp_signing_key", {"id": "rag_mcp", "label": "Second", "secret": "s2"})
    assert result["mcp_signing_key"]["label"] == "Second"
    assert config.execute("list_mcp_signing_keys", {})["count"] == 1


def test_save_mcp_signing_key_edit_without_secret_keeps_the_existing_one(config):
    config.execute("save_mcp_signing_key", {"id": "rag_mcp", "secret": "original-secret"})
    result = config.execute("save_mcp_signing_key", {"id": "rag_mcp", "label": "Renamed"})
    assert result["mcp_signing_key"]["secret"] == "original-secret"
    assert result["mcp_signing_key"]["label"] == "Renamed"


def test_list_mcp_signing_keys_masks_the_secret(config):
    config.execute("save_mcp_signing_key", {"id": "rag_mcp", "secret": "a-very-long-secret-value"})
    result = config.execute("list_mcp_signing_keys", {})
    listed_secret = result["mcp_signing_keys"][0]["secret"]
    assert listed_secret != "a-very-long-secret-value"
    assert listed_secret.endswith("alue")  # last 4 chars preserved
    assert "•" in listed_secret


def test_list_mcp_signing_keys_reports_supported_algs(config):
    result = config.execute("list_mcp_signing_keys", {})
    assert "HS256" in result["supported_algs"]


def test_delete_mcp_signing_key_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("delete_mcp_signing_key", {})


def test_delete_mcp_signing_key_success(config):
    config.execute("save_mcp_signing_key", {"id": "rag_mcp"})
    result = config.execute("delete_mcp_signing_key", {"id": "rag_mcp"})
    assert result["deleted"] is True
    assert config.execute("list_mcp_signing_keys", {})["count"] == 0


def test_reveal_mcp_signing_key_requires_id(config):
    with pytest.raises(ValidationError):
        config.execute("reveal_mcp_signing_key", {})


def test_reveal_mcp_signing_key_unknown_id_raises(config):
    with pytest.raises(ValidationError):
        config.execute("reveal_mcp_signing_key", {"id": "missing"})


def test_reveal_mcp_signing_key_returns_the_unmasked_secret(config):
    config.execute("save_mcp_signing_key", {"id": "rag_mcp", "secret": "the-real-secret"})
    result = config.execute("reveal_mcp_signing_key", {"id": "rag_mcp"})
    assert result["mcp_signing_key"]["secret"] == "the-real-secret"
