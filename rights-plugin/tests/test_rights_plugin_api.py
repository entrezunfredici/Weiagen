"""rights_plugin_api — the stable public contract other plugins import.

Not the internal implementation (already covered by test_engine.py/
test_identity.py) — just that the re-export surface itself works, since
this is the one module a consumer plugin (odoo-plugin) actually imports.
"""

import rights_plugin_api
from models import create_access_right


def test_exports_match_all():
    for name in rights_plugin_api.__all__:
        assert hasattr(rights_plugin_api, name)


def test_check_right_reexport_is_the_real_function():
    create_access_right(["admin"], "hermes_tool", "shell_exec", execute=True)
    decision = rights_plugin_api.check_right(
        roles=["admin"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute",
    )
    assert decision.allowed is True


def test_resolve_identity_reexport_is_the_real_function():
    identity = rights_plugin_api.resolve_identity(platform="slack", external_user_id="U0123")
    assert identity.platform == "slack"
    assert rights_plugin_api.ROLE_EVERYONE in identity.roles


def test_has_any_right_for_reexport():
    assert rights_plugin_api.has_any_right_for("hermes_tool", ("shell_exec", "*")) is False
    create_access_right(["admin"], "hermes_tool", "shell_exec")
    assert rights_plugin_api.has_any_right_for("hermes_tool", ("shell_exec", "*")) is True


def test_list_rights_for_roles_returns_plain_dicts():
    create_access_right(["everyone"], "odoo_model", "1:project.task", id="r1",
        fields=["name"], create=True, read=True,
    )
    create_access_right(["admin"], "odoo_model", "1:res.partner", id="r2")
    create_access_right(["everyone"], "hermes_tool", "shell_exec", id="r3")

    result = rights_plugin_api.list_rights_for_roles(["everyone"], "odoo_model")
    assert len(result) == 1
    entry = result[0]
    assert isinstance(entry, dict)
    assert entry["resource_id"] == "1:project.task"
    assert entry["fields"] == ["name"]
    assert entry["create"] is True
    assert entry["read"] is True


def test_list_rights_for_roles_matches_any_of_multiple_roles():
    create_access_right(["admin"], "odoo_model", "1:project.task", id="r1")
    create_access_right(["finance"], "odoo_model", "1:account.move", id="r2")
    result = rights_plugin_api.list_rights_for_roles(["admin", "finance"], "odoo_model")
    assert {r["resource_id"] for r in result} == {"1:project.task", "1:account.move"}


def test_create_right_reexport_returns_a_plain_dict():
    result = rights_plugin_api.create_right(
        roles=["everyone"], resource_type="odoo_model", resource_id="1:project.task",
        fields=["name"], create=True,
    )
    assert isinstance(result, dict)
    assert result["resource_id"] == "1:project.task"
    assert result["create"] is True
    assert result["id"]  # generated
    assert result["roles"] == ["everyone"]  # plural, a list — see .agents/DECISIONS.md (2026-08-18)


def test_create_right_reexport_accepts_multiple_roles():
    result = rights_plugin_api.create_right(
        roles=["admin", "finance"], resource_type="odoo_model", resource_id="1:project.task",
    )
    assert result["roles"] == ["admin", "finance"]


def test_create_right_reexport_upserts_by_explicit_id():
    rights_plugin_api.create_right(
        roles=["everyone"], resource_type="odoo_model", resource_id="1:project.task", id="r1",
    )
    result = rights_plugin_api.create_right(
        roles=["everyone"], resource_type="odoo_model", resource_id="1:project.task",
        id="r1", create=True,
    )
    assert result["id"] == "r1"
    all_rights = rights_plugin_api.list_rights_for_resource_type("odoo_model")
    assert len(all_rights) == 1
    assert all_rights[0]["create"] is True


def test_delete_right_reexport():
    created = rights_plugin_api.create_right(
        roles=["everyone"], resource_type="odoo_model", resource_id="1:project.task",
    )
    assert rights_plugin_api.delete_right(created["id"]) is True
    assert rights_plugin_api.delete_right(created["id"]) is False
