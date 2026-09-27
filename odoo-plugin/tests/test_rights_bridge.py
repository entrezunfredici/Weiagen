"""w_odoo.rights_bridge — the cross-plugin bridge to rights-plugin.

Exercises the real rights-plugin code (models.create_access_right, etc.) —
sys.path is mutated to include rights-plugin/ as a side effect of importing
w_odoo (see rights_bridge.py's module-level sibling-dir lookup), so
`import models` here resolves to rights-plugin's models.py. RIGHTS_AVAILABLE
must be True in this test environment (hermes_state is stubbed in
conftest.py) — a False here would mean the sibling lookup regressed.
"""

import pytest

from w_odoo import rights_bridge


def test_rights_available_in_this_test_environment():
    # If this is False, the sibling-directory lookup in rights_bridge.py
    # broke — every other test in this file would then be vacuously true
    # (check_field always returns (False, False) either way).
    assert rights_bridge.RIGHTS_AVAILABLE is True


@pytest.fixture
def access_right():
    import models
    return models.create_access_right


def test_check_field_denies_with_no_matching_right(access_right):
    allowed, confirm = rights_bridge.check_field("p1", "project.task", "name", "read", ["everyone"])
    assert allowed is False
    assert confirm is False


def test_check_field_allows_with_matching_role_right(access_right):
    access_right(["everyone"], "odoo_model", "p1:project.task", fields=["name"], read=True)
    allowed, confirm = rights_bridge.check_field("p1", "project.task", "name", "read", ["everyone"])
    assert allowed is True
    assert confirm is False


def test_check_field_scoped_to_role(access_right):
    access_right(["admin"], "odoo_model", "p1:project.task", fields=["name"], read=True)
    allowed, _ = rights_bridge.check_field("p1", "project.task", "name", "read", ["everyone"])
    assert allowed is False
    allowed, _ = rights_bridge.check_field("p1", "project.task", "name", "read", ["admin"])
    assert allowed is True


def test_check_field_requires_confirmation(access_right):
    access_right(["everyone"], "odoo_model", "p1:project.task", fields=["*"],
        delete=True, confirm_delete=True,
    )
    allowed, confirm = rights_bridge.check_field("p1", "project.task", "*", "delete", ["everyone"])
    assert allowed is True
    assert confirm is True


def test_get_identity_resolves_via_session(fake_sessions):
    import models
    fake_sessions["sess-1"] = {"source": "slack", "user_id": "U0123"}
    models.bind_role("slack", "U0123", ["admin"])
    identity = rights_bridge.get_identity("sess-1")
    assert identity.platform == "slack"
    assert "admin" in identity.roles


def test_get_identity_falls_back_to_automation_without_session():
    identity = rights_bridge.get_identity(None)
    assert "automation" in identity.roles or "everyone" in identity.roles


def test_rights_for_profile_splits_resource_id_into_model(access_right):
    access_right(["everyone"], "odoo_model", "p1:project.task", id="r1")
    access_right(["everyone"], "odoo_model", "p1:res.partner", id="r2")
    access_right(["everyone"], "odoo_model", "p2:project.task", id="r3")  # different profile

    pairs = rights_bridge.rights_for_profile("p1", ["everyone"])
    assert {model for model, _ in pairs} == {"project.task", "res.partner"}


def test_rights_for_profile_and_model_filters(access_right):
    access_right(["everyone"], "odoo_model", "p1:project.task", id="r1")
    access_right(["everyone"], "odoo_model", "p1:res.partner", id="r2")
    rights = rights_bridge.rights_for_profile_and_model("p1", "project.task", ["everyone"])
    assert len(rights) == 1
    assert rights[0]["resource_id"] == "p1:project.task"


def test_applies_to_field_wildcard():
    right = {"fields": ["*"]}
    assert rights_bridge.applies_to_field(right, "anything") is True


def test_applies_to_field_exact():
    right = {"fields": ["name"]}
    assert rights_bridge.applies_to_field(right, "name") is True
    assert rights_bridge.applies_to_field(right, "other") is False


def test_all_odoo_rights_reshapes_across_all_roles(access_right):
    access_right(["everyone"], "odoo_model", "p1:project.task", id="r1", create=True)
    access_right(["admin"], "odoo_model", "p1:res.partner", id="r2", delete=True)
    access_right(["everyone"], "hermes_tool", "shell_exec", id="r3")  # different resource_type, excluded

    rights = rights_bridge.all_odoo_rights()
    assert {r["odoo_model"] for r in rights} == {"project.task", "res.partner"}
    task = next(r for r in rights if r["odoo_model"] == "project.task")
    assert task["profile_id"] == "p1"
    assert task["create"] is True


# ---------------------------------------------------------------------------
# create_right / delete_right — write-side, backs the odoo-plugin dashboard
# ---------------------------------------------------------------------------


def test_create_right_builds_resource_id_and_binds_everyone():
    right = rights_bridge.create_right("p1", "project.task", fields=["name"], create=True)
    assert right["profile_id"] == "p1"
    assert right["odoo_model"] == "project.task"
    assert right["create"] is True

    import models
    stored = models.get_access_right(right["id"])
    assert stored.roles == ["everyone"]
    assert stored.resource_type == "odoo_model"
    assert stored.resource_id == "p1:project.task"


def test_create_right_upserts_by_explicit_id():
    rights_bridge.create_right("p1", "project.task", fields=["*"], id="r1", create=False)
    right = rights_bridge.create_right("p1", "project.task", fields=["*"], id="r1", create=True)
    assert right["id"] == "r1"
    import models
    assert len(models.list_access_rights()) == 1


def test_delete_right_removes_it():
    right = rights_bridge.create_right("p1", "project.task", fields=["*"])
    assert rights_bridge.delete_right(right["id"]) is True
    assert rights_bridge.delete_right(right["id"]) is False


def test_create_right_raises_when_rights_plugin_unavailable(monkeypatch):
    monkeypatch.setattr(rights_bridge, "RIGHTS_AVAILABLE", False)
    from w_main.errors_manager.errors import ConfigurationError
    with pytest.raises(ConfigurationError):
        rights_bridge.create_right("p1", "project.task", fields=["*"])


def test_delete_right_returns_false_when_rights_plugin_unavailable(monkeypatch):
    monkeypatch.setattr(rights_bridge, "RIGHTS_AVAILABLE", False)
    assert rights_bridge.delete_right("anything") is False
