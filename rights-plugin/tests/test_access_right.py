"""rights_plugin.models — AccessRight CRUD, applies_to_field/resource/role, to_right()."""

from models import (
    AccessRight,
    create_access_right,
    delete_access_right,
    get_access_right,
    get_access_right_or_none,
    list_access_rights,
    rights_for_resource,
    rights_for_resource_type,
    rights_for_role,
    rights_for_role_and_resource,
    rights_for_roles_and_resource_type,
)
from rights_w_main.errors_manager.errors import NotFoundError

import pytest


def test_create_access_right_generates_id_when_omitted():
    right = create_access_right(["admin"], "hermes_tool", "shell_exec")
    assert right.id
    assert right.roles == ["admin"]


def test_create_access_right_with_explicit_id():
    right = create_access_right(["admin"], "hermes_tool", "shell_exec", id="r1")
    assert right.id == "r1"


def test_create_access_right_with_multiple_roles():
    right = create_access_right(["admin", "finance"], "hermes_tool", "shell_exec")
    assert right.roles == ["admin", "finance"]


def test_defaults_match_deny_by_default_except_read():
    right = create_access_right(["everyone"], "odoo_model", "1:project.task")
    assert right.create is False
    assert right.read is True
    assert right.update is False
    assert right.delete is False
    assert right.execute is False
    assert right.fields == ["*"]


def test_get_access_right_missing_raises_not_found():
    with pytest.raises(NotFoundError):
        get_access_right("missing")


def test_get_access_right_or_none_missing_returns_none():
    assert get_access_right_or_none("missing") is None


def test_delete_access_right():
    right = create_access_right(["admin"], "hermes_tool", "shell_exec")
    assert delete_access_right(right.id) is True
    assert get_access_right_or_none(right.id) is None
    assert delete_access_right(right.id) is False


def test_list_access_rights_returns_all():
    create_access_right(["admin"], "hermes_tool", "shell_exec", id="r1")
    create_access_right(["everyone"], "odoo_model", "1:project.task", id="r2")
    assert {r.id for r in list_access_rights()} == {"r1", "r2"}


def test_applies_to_field_wildcard():
    right = AccessRight(id="r1", roles=["everyone"], resource_type="odoo_model", resource_id="*", fields=["*"])
    assert right.applies_to_field("anything") is True


def test_applies_to_field_exact_match():
    right = AccessRight(id="r1", roles=["everyone"], resource_type="odoo_model", resource_id="*", fields=["name"])
    assert right.applies_to_field("name") is True
    assert right.applies_to_field("deadline") is False


def test_applies_to_resource_wildcard():
    right = AccessRight(id="r1", roles=["everyone"], resource_type="hermes_tool", resource_id="*")
    assert right.applies_to_resource("shell_exec") is True
    assert right.applies_to_resource("anything") is True


def test_applies_to_resource_exact_match():
    right = AccessRight(id="r1", roles=["everyone"], resource_type="hermes_tool", resource_id="shell_exec")
    assert right.applies_to_resource("shell_exec") is True
    assert right.applies_to_resource("other_tool") is False


def test_applies_to_role_membership():
    right = AccessRight(id="r1", roles=["admin", "finance"], resource_type="hermes_tool", resource_id="*")
    assert right.applies_to_role("admin") is True
    assert right.applies_to_role("finance") is True
    assert right.applies_to_role("everyone") is False


def test_to_right_confirm_flags_none_when_false():
    right = create_access_right(["admin"], "hermes_tool", "shell_exec", execute=True)
    converted = right.to_right()
    assert converted.execute is True
    assert converted.confirm_execute is None  # False -> None, cascades to global flag


def test_to_right_confirm_flag_true_forces_confirmation():
    right = create_access_right(["admin"], "hermes_tool", "shell_exec", execute=True, confirm_execute=True)
    converted = right.to_right()
    assert converted.confirm_execute is True


def test_rights_for_role_filters():
    create_access_right(["admin"], "hermes_tool", "shell_exec", id="r1")
    create_access_right(["everyone"], "hermes_tool", "shell_exec", id="r2")
    assert {r.id for r in rights_for_role("admin")} == {"r1"}


def test_rights_for_role_matches_a_right_bound_to_several_roles():
    create_access_right(["admin", "finance"], "hermes_tool", "shell_exec", id="r1")
    assert {r.id for r in rights_for_role("admin")} == {"r1"}
    assert {r.id for r in rights_for_role("finance")} == {"r1"}
    assert rights_for_role("everyone") == []


def test_rights_for_resource_type_filters():
    create_access_right(["admin"], "hermes_tool", "shell_exec", id="r1")
    create_access_right(["admin"], "odoo_model", "1:project.task", id="r2")
    assert {r.id for r in rights_for_resource_type("hermes_tool")} == {"r1"}


def test_rights_for_resource_exact_and_wildcard():
    create_access_right(["admin"], "hermes_tool", "shell_exec", id="exact")
    create_access_right(["admin"], "hermes_tool", "*", id="wild")
    create_access_right(["admin"], "hermes_tool", "other_tool", id="other")
    matches = {r.id for r in rights_for_resource("hermes_tool", "shell_exec")}
    assert matches == {"exact", "wild"}


def test_rights_for_role_and_resource_scopes_both_dimensions():
    create_access_right(["admin"], "hermes_tool", "shell_exec", id="admin-exact")
    create_access_right(["everyone"], "hermes_tool", "shell_exec", id="everyone-exact")
    matches = rights_for_role_and_resource("admin", "hermes_tool", "shell_exec")
    assert {r.id for r in matches} == {"admin-exact"}


def test_rights_for_roles_and_resource_type_matches_any_intersecting_role():
    create_access_right(["admin"], "hermes_tool", "shell_exec", id="r1")
    create_access_right(["finance"], "hermes_tool", "read_file", id="r2")
    create_access_right(["hr"], "hermes_tool", "other", id="r3")
    matches = rights_for_roles_and_resource_type(["admin", "finance"], "hermes_tool")
    assert {r.id for r in matches} == {"r1", "r2"}


# ---------------------------------------------------------------------------
# hermes_tool/hermes_cron fields are always forced to ["*"] — these resource
# types have no field concept at all, and a right whose fields isn't
# exactly ["*"] is 100% inert for them (engine.check_right always evaluates
# them with field="*") — real production bug caught 2026-08-20, see
# .agents/DECISIONS.md. Typing a tool name into the dashboard's Fields box
# (a natural but wrong guess at "scoping" the right) reproduced this
# exactly.
# ---------------------------------------------------------------------------


def test_create_access_right_forces_wildcard_fields_for_hermes_tool():
    right = create_access_right(["everyone"], "hermes_tool", "clarify", fields=["clarify"], execute=True)
    assert right.fields == ["*"]


def test_create_access_right_forces_wildcard_fields_for_hermes_cron():
    right = create_access_right(["everyone"], "hermes_cron", "*", fields=["create"], create=True)
    assert right.fields == ["*"]


def test_create_access_right_leaves_fields_alone_for_other_resource_types():
    # odoo_model (and any other delegating resource type) legitimately
    # uses field-level scoping — only hermes_tool/hermes_cron are forced.
    right = create_access_right(["everyone"], "odoo_model", "1:project.task", fields=["name"])
    assert right.fields == ["name"]


def test_a_hermes_tool_right_with_bad_fields_would_otherwise_be_inert():
    # Pin the actual production symptom via the real decision engine, not
    # just the stored value: before the fix, this exact call sequence
    # denied 'clarify' outright even though resource_id/operation/role all
    # matched — because check_right always queries field="*", and
    # applies_to_field("*") is only true when "*" is literally in `fields`.
    from engine import check_right

    create_access_right(["everyone"], "hermes_tool", "clarify", fields=["clarify"], execute=True)
    decision = check_right(roles=["everyone"], resource_type="hermes_tool", resource_id="clarify", operation="execute")
    assert decision.allowed is True


# ---------------------------------------------------------------------------
# normalize_hermes_resource_fields — self-heal for rows saved before the
# fix above existed (create_access_right didn't yet reject a bad `fields`
# value, so data written before 2026-08-20 can still have one on disk).
# Simulates that legacy state by writing directly through
# save_access_right(), bypassing create_access_right's guard on purpose.
# ---------------------------------------------------------------------------


def test_normalize_hermes_resource_fields_repairs_a_broken_hermes_tool_right():
    from models import save_access_right, normalize_hermes_resource_fields

    broken = AccessRight(
        id="legacy1", roles=["everyone"], resource_type="hermes_tool",
        resource_id="clarify", fields=["clarify"], execute=True,
    )
    save_access_right(broken)

    fixed_count = normalize_hermes_resource_fields()
    assert fixed_count == 1
    assert get_access_right("legacy1").fields == ["*"]


def test_normalize_hermes_resource_fields_repairs_a_broken_hermes_cron_right():
    from models import save_access_right, normalize_hermes_resource_fields

    broken = AccessRight(
        id="legacy2", roles=["everyone"], resource_type="hermes_cron",
        resource_id="*", fields=["create"], create=True,
    )
    save_access_right(broken)

    normalize_hermes_resource_fields()
    assert get_access_right("legacy2").fields == ["*"]


def test_normalize_hermes_resource_fields_leaves_other_resource_types_alone():
    from models import save_access_right, normalize_hermes_resource_fields

    right = AccessRight(
        id="odoo1", roles=["everyone"], resource_type="odoo_model",
        resource_id="1:project.task", fields=["name"], read=True,
    )
    save_access_right(right)

    fixed_count = normalize_hermes_resource_fields()
    assert fixed_count == 0
    assert get_access_right("odoo1").fields == ["name"]


def test_normalize_hermes_resource_fields_is_idempotent_and_preserves_other_flags():
    from models import save_access_right, normalize_hermes_resource_fields

    broken = AccessRight(
        id="legacy3", roles=["admin", "finance"], resource_type="hermes_tool",
        resource_id="shell_exec", fields=["shell_exec"], label="test right",
        execute=True, require_confirmation=True, confirm_execute=True,
    )
    save_access_right(broken)

    first = normalize_hermes_resource_fields()
    second = normalize_hermes_resource_fields()
    assert first == 1
    assert second == 0  # already clean, nothing left to fix

    fixed = get_access_right("legacy3")
    assert fixed.fields == ["*"]
    # Everything else about the right survives the repair untouched.
    assert fixed.roles == ["admin", "finance"]
    assert fixed.label == "test right"
    assert fixed.execute is True
    assert fixed.require_confirmation is True
    assert fixed.confirm_execute is True
