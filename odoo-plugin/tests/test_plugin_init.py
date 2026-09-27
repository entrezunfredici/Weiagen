"""odoo_plugin/__init__.py — _pre_tool_call human-approval hook + register().

Rights now come from rights-plugin — ``_right()`` is the same test helper
pattern as test_odoo_cli_for_ai.py (role "everyone", resource_id =
f"{profile_id}:{odoo_model}"). No session_id is passed to _pre_tool_call in
most of these tests, so the caller resolves to the "automation" pseudo-
identity (see rights_plugin/identity.py), whose roles include "everyone" —
that's why binding to role "everyone" is enough for these tests without
needing a fake session.
"""

import pytest

from w_odoo.odoo_profile import create_odoo_profile


def _right(profile_id: str, odoo_model: str, fields: list[str], **kwargs):
    import models
    return models.create_access_right(
        roles=["everyone"], resource_type="odoo_model",
        resource_id=f"{profile_id}:{odoo_model}", fields=fields, **kwargs,
    )


@pytest.fixture
def profile():
    return create_odoo_profile(
        id="p1", label="P1", base_url="https://odoo.example.com",
        database="db", login="l", password="pw",
    )


# ---------------------------------------------------------------------------
# _pre_tool_call
# ---------------------------------------------------------------------------

def test_non_confirmable_tool_returns_none(odoo_plugin_pkg):
    assert odoo_plugin_pkg._pre_tool_call("docs_create_xlsx", {"output_path": "/tmp/x.xlsx"}) is None


def test_missing_profile_id_or_model_returns_none(odoo_plugin_pkg):
    assert odoo_plugin_pkg._pre_tool_call("odoo_sdk_read", {"model": "res.partner"}) is None
    assert odoo_plugin_pkg._pre_tool_call("odoo_sdk_read", {"profile_id": "p1"}) is None


def test_no_matching_right_returns_none(odoo_plugin_pkg, profile):
    # Deny-by-default: no right at all configured for this field -> hook has
    # nothing to escalate (the handler itself will raise AuthorizationError).
    result = odoo_plugin_pkg._pre_tool_call(
        "odoo_sdk_read", {"profile_id": "p1", "model": "res.partner", "fields": ["name"]},
    )
    assert result is None


def test_right_without_confirmation_returns_none(odoo_plugin_pkg, profile):
    _right("p1", "res.partner", ["name"], read=True)
    result = odoo_plugin_pkg._pre_tool_call(
        "odoo_sdk_read", {"profile_id": "p1", "model": "res.partner", "fields": ["name"]},
    )
    assert result is None


def test_right_requiring_confirmation_returns_approve_directive(odoo_plugin_pkg, profile):
    _right("p1", "res.partner", ["name"], read=True, confirm_read=True)
    result = odoo_plugin_pkg._pre_tool_call(
        "odoo_sdk_read", {"profile_id": "p1", "model": "res.partner", "fields": ["name"]},
    )
    assert result is not None
    assert result["action"] == "approve"
    assert "res.partner" in result["message"]
    assert result["rule_key"] == "odoo:read:res.partner"


def test_delete_checked_against_wildcard_field(odoo_plugin_pkg, profile):
    _right("p1", "res.partner", ["*"], delete=True, confirm_delete=True)
    result = odoo_plugin_pkg._pre_tool_call(
        "odoo_sdk_delete", {"profile_id": "p1", "model": "res.partner", "id": 1},
    )
    assert result is not None
    assert result["rule_key"] == "odoo:delete:res.partner"


def test_create_checks_every_field_in_values(odoo_plugin_pkg, profile):
    _right("p1", "res.partner", ["name"], create=True)
    _right("p1", "res.partner", ["vat"], create=True, confirm_create=True)
    result = odoo_plugin_pkg._pre_tool_call(
        "odoo_sdk_create",
        {"profile_id": "p1", "model": "res.partner", "values": {"name": "Acme", "vat": "FR1"}},
    )
    # "vat" requires confirmation even though "name" doesn't -> whole call escalates.
    assert result is not None


def test_args_not_a_dict_returns_none(odoo_plugin_pkg):
    assert odoo_plugin_pkg._pre_tool_call("odoo_sdk_read", None) is None


def test_session_id_resolves_a_bound_role(odoo_plugin_pkg, profile, fake_sessions):
    import models
    fake_sessions["sess-1"] = {"source": "slack", "user_id": "U0123"}
    models.bind_role("slack", "U0123", ["admin"])
    _right("p1", "res.partner", ["name"], read=True, confirm_read=True)  # bound to role "everyone"

    # An identity with only "admin" (no "everyone" binding, but "everyone" is
    # always implicit — see rights_plugin/identity.py) still sees this right.
    result = odoo_plugin_pkg._pre_tool_call(
        "odoo_sdk_read", {"profile_id": "p1", "model": "res.partner", "fields": ["name"]},
        session_id="sess-1",
    )
    assert result is not None
    assert result["action"] == "approve"


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------

class _FakeCtx:
    def __init__(self):
        self.registered_tools = []
        self.registered_cli = []
        self.registered_hooks = []

    def register_tool(self, *, name, toolset, schema, handler, emoji):
        self.registered_tools.append(name)

    def register_cli_command(self, *, name, help, setup_fn, handler_fn, description):
        self.registered_cli.append(name)

    def register_hook(self, hook_name, fn):
        self.registered_hooks.append(hook_name)


def test_register_registers_every_tool_the_cli_and_the_hook(odoo_plugin_pkg, tools_mod):
    ctx = _FakeCtx()
    odoo_plugin_pkg.register(ctx)
    assert set(ctx.registered_tools) == {entry[0] for entry in tools_mod.ALL_TOOLS}
    assert ctx.registered_cli == ["odoo"]
    assert ctx.registered_hooks == ["pre_tool_call"]
