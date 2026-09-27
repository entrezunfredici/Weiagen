"""rights_plugin.engine.check_right — deny-by-default decision engine.

Parity cases ported from odoo-plugin/tests/test_odoo_rights.py's
get_right_manager_for tests (single-role case must behave identically to
today's Odoo behavior, modulo "raises NotFoundError" -> "returns
RightDecision(allowed=False)"), plus new cases for multi-role combination
and the resource_id=="*" wildcard.
"""

from engine import check_right, has_any_right_configured, has_any_right_for
from models import create_access_right


# ---------------------------------------------------------------------------
# Parity with odoo-plugin's get_right_manager_for (single role)
# ---------------------------------------------------------------------------


def test_no_match_denies_without_raising():
    # Deny-by-default: no right at all covering this resource. Unlike
    # get_right_manager_for (raised NotFoundError), check_right never raises.
    decision = check_right(roles=["p1"], resource_type="odoo_model", resource_id="project.task", operation="read")
    assert decision.allowed is False
    assert decision.require_confirmation is False


def test_prefers_exact_field_over_wildcard():
    create_access_right(["p1"], "odoo_model", "project.task", id="wildcard", fields=["*"], create=False)
    create_access_right(["p1"], "odoo_model", "project.task", id="exact", fields=["deadline"], create=True)
    decision = check_right(
        roles=["p1"], resource_type="odoo_model", resource_id="project.task",
        operation="create", field="deadline",
    )
    # The exact-field right (create=True) must win over the wildcard (create=False).
    assert decision.allowed is True


def test_falls_back_to_wildcard_when_no_exact_match():
    create_access_right(["p1"], "odoo_model", "project.task", id="wildcard", fields=["*"], create=True)
    decision = check_right(
        roles=["p1"], resource_type="odoo_model", resource_id="project.task",
        operation="create", field="any_field",
    )
    assert decision.allowed is True


def test_scoped_to_role():
    create_access_right(["p1"], "odoo_model", "project.task", fields=["*"], create=True)
    decision = check_right(
        roles=["other-role"], resource_type="odoo_model", resource_id="project.task", operation="create",
    )
    assert decision.allowed is False


def test_scoped_to_resource_type():
    create_access_right(["p1"], "odoo_model", "project.task", fields=["*"], create=True)
    decision = check_right(
        roles=["p1"], resource_type="hermes_tool", resource_id="project.task", operation="create",
    )
    assert decision.allowed is False


def test_to_right_confirm_flags_none_when_false_end_to_end():
    create_access_right(["p1"], "odoo_model", "project.task", fields=["*"],
        create=True, confirm_create=False, confirm_delete=True,
    )
    decision = check_right(roles=["p1"], resource_type="odoo_model", resource_id="project.task", operation="create")
    assert decision.allowed is True
    assert decision.require_confirmation is False  # global require_confirmation defaults False too


# ---------------------------------------------------------------------------
# resource_id == "*" wildcard (new — no equivalent in odoo-plugin, which had
# no analogous "any model" right)
# ---------------------------------------------------------------------------


def test_wildcard_resource_id_matches_any_resource():
    create_access_right(["admin"], "hermes_tool", "*", read=True, execute=True)
    decision = check_right(roles=["admin"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute")
    assert decision.allowed is True


def test_exact_resource_id_preferred_over_wildcard_resource_id():
    create_access_right(["admin"], "hermes_tool", "*", id="wild", execute=False)
    create_access_right(["admin"], "hermes_tool", "shell_exec", id="exact", execute=True)
    decision = check_right(roles=["admin"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute")
    assert decision.allowed is True


# ---------------------------------------------------------------------------
# Multi-role combination: most permissive wins (decided explicitly with Fred)
# ---------------------------------------------------------------------------


def test_multi_role_allows_if_any_role_grants():
    create_access_right(["admin"], "hermes_tool", "shell_exec", execute=True)
    # "everyone" has no right at all for this resource.
    decision = check_right(roles=["everyone", "admin"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute")
    assert decision.allowed is True


def test_multi_role_denies_if_no_role_grants():
    create_access_right(["everyone"], "hermes_tool", "shell_exec", execute=False)
    decision = check_right(roles=["everyone", "guest"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute")
    assert decision.allowed is False


def test_multi_role_confirmation_required_only_if_every_granting_role_requires_it():
    create_access_right(["admin"], "hermes_tool", "shell_exec", id="admin-right", execute=True, confirm_execute=False)
    create_access_right(["power_user"], "hermes_tool", "shell_exec", id="power-right", execute=True, confirm_execute=True)
    # admin grants without confirmation -> overall no confirmation required (most permissive wins).
    decision = check_right(
        roles=["admin", "power_user"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute",
    )
    assert decision.allowed is True
    assert decision.require_confirmation is False


def test_multi_role_confirmation_required_when_all_granting_roles_require_it():
    create_access_right(["power_user"], "hermes_tool", "shell_exec", id="p1", execute=True, confirm_execute=True)
    create_access_right(["auditor"], "hermes_tool", "shell_exec", id="p2", execute=True, confirm_execute=True)
    decision = check_right(
        roles=["power_user", "auditor"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute",
    )
    assert decision.allowed is True
    assert decision.require_confirmation is True


def test_multi_role_a_role_that_only_covers_a_different_resource_is_ignored():
    create_access_right(["admin"], "odoo_model", "1:project.task", create=True)
    # admin has no right at all for hermes_tool:shell_exec -> denied, unaffected
    # by admin's unrelated odoo_model right.
    decision = check_right(roles=["admin"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute")
    assert decision.allowed is False


# ---------------------------------------------------------------------------
# One right, several roles (AccessRight.roles is a list) — distinct from
# the "multi-role identity" cases above, which combine several *separate*
# rights across an identity's roles.
# ---------------------------------------------------------------------------


def test_one_right_with_several_roles_matches_a_caller_with_only_one_of_them():
    create_access_right(["admin", "finance"], "hermes_tool", "shell_exec", execute=True)
    decision = check_right(roles=["finance"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute")
    assert decision.allowed is True


def test_one_right_with_several_roles_denies_a_caller_with_none_of_them():
    create_access_right(["admin", "finance"], "hermes_tool", "shell_exec", execute=True)
    decision = check_right(roles=["guest"], resource_type="hermes_tool", resource_id="shell_exec", operation="execute")
    assert decision.allowed is False


# ---------------------------------------------------------------------------
# has_any_right_for — general-purpose "does a right exist for this exact
# resource" query (public, re-exported via rights_plugin_api). NOT the
# pre_tool_call hook's hermes_tool safety gate anymore as of 2026-08-19 —
# see has_any_right_configured below for that, and .agents/DECISIONS.md
# for why a per-resource_id check was a real production bug.
# ---------------------------------------------------------------------------


def test_has_any_right_for_false_when_none_configured():
    assert has_any_right_for("hermes_tool", ("shell_exec", "*")) is False


def test_has_any_right_for_true_on_exact_match():
    create_access_right(["admin"], "hermes_tool", "shell_exec")
    assert has_any_right_for("hermes_tool", ("shell_exec", "*")) is True


def test_has_any_right_for_true_on_wildcard_right():
    create_access_right(["admin"], "hermes_tool", "*")
    assert has_any_right_for("hermes_tool", ("shell_exec", "*")) is True


def test_has_any_right_for_ignores_other_resource_types():
    create_access_right(["admin"], "odoo_model", "1:project.task")
    assert has_any_right_for("hermes_tool", ("shell_exec", "*")) is False


# ---------------------------------------------------------------------------
# has_any_right_configured — the pre_tool_call hook's hermes_tool safety
# gate (2026-08-19 fix): true once ANY right exists for the resource_type,
# regardless of which resource_id it targets.
# ---------------------------------------------------------------------------


def test_has_any_right_configured_false_when_none_exist():
    assert has_any_right_configured("hermes_tool") is False


def test_has_any_right_configured_true_even_for_an_unrelated_resource_id():
    # The whole point of the fix: a right scoped to ONE tool still counts
    # as "hermes_tool is configured" for every other tool's gating.
    create_access_right(["admin"], "hermes_tool", "odoo_sdk_read")
    assert has_any_right_configured("hermes_tool") is True


def test_has_any_right_configured_ignores_other_resource_types():
    create_access_right(["admin"], "odoo_model", "1:project.task")
    assert has_any_right_configured("hermes_tool") is False
