# Vendored from odoo-plugin/tests/test_right_manager.py — smoke test proving
# the vendored rights_w_main/right_manager copy behaves identically for the
# original CRUD vocabulary, plus new cases for the "execute" operation this
# copy adds (see rights_w_main/right_manager/right_manager.py's header). See
# .agents/DECISIONS.md ("rights-plugin: vendoring vs cross-plugin import").
"""rights_w_main.right_manager.right_manager — deny-by-default CRUD(+execute) gate."""

import pytest

from rights_w_main.errors_manager.errors import AuthorizationError, ConfirmationRequiredError
from rights_w_main.right_manager.right_manager import Right, RightManager


def test_defaults_are_deny_by_default_except_read():
    right = Right(id="r1")
    assert right.is_allowed("read") is True
    assert right.is_allowed("create") is False
    assert right.is_allowed("update") is False
    assert right.is_allowed("delete") is False
    assert right.is_allowed("execute") is False


def test_check_denied_operation():
    rm = RightManager(Right(id="r1"))
    decision = rm.check("delete")
    assert decision.allowed is False
    assert decision.require_confirmation is False
    assert decision.is_ready() is False


def test_check_allowed_no_confirmation():
    rm = RightManager(Right(id="r1", create=True))
    decision = rm.check("create")
    assert decision.allowed is True
    assert decision.require_confirmation is False
    assert decision.is_ready() is True


def test_global_require_confirmation_applies_to_every_allowed_operation():
    rm = RightManager(Right(id="r1", create=True, delete=True, require_confirmation=True))
    for op in ("create", "delete"):
        decision = rm.check(op)
        assert decision.require_confirmation is True
        assert decision.is_ready() is False
        assert decision.is_ready(confirmed=True) is True


def test_per_operation_confirm_flag_overrides_global_flag():
    # Global confirmation on, but confirm_create explicitly False — create
    # should NOT need confirmation even though require_confirmation=True.
    right = Right(id="r1", create=True, delete=True, require_confirmation=True, confirm_create=False)
    rm = RightManager(right)
    assert rm.check("create").require_confirmation is False
    assert rm.check("delete").require_confirmation is True


def test_per_operation_confirm_flag_can_require_confirmation_alone():
    # Global flag off, but confirm_update explicitly True.
    right = Right(id="r1", update=True, confirm_update=True)
    rm = RightManager(right)
    assert rm.check("update").require_confirmation is True


def test_assert_allowed_raises_authorization_error_when_denied():
    rm = RightManager(Right(id="r1"))
    with pytest.raises(AuthorizationError) as exc_info:
        rm.assert_delete()
    assert exc_info.value.to_dict()["error"]["code"] == "AUTHORIZATION_DENIED"


def test_assert_allowed_raises_confirmation_required_when_unconfirmed():
    rm = RightManager(Right(id="r1", delete=True, confirm_delete=True))
    with pytest.raises(ConfirmationRequiredError):
        rm.assert_delete()
    rm.assert_delete(confirmed=True)  # does not raise


def test_assert_create_read_update_delete_convenience_methods():
    rm = RightManager(Right(id="r1", create=True, read=True, update=True, delete=True))
    rm.assert_create()
    rm.assert_read()
    rm.assert_update()
    rm.assert_delete()


def test_allowed_operations_lists_only_allowed():
    right = Right(id="r1", create=True, read=True, update=False, delete=True)
    rm = RightManager(right)
    assert rm.allowed_operations() == ["create", "read", "delete"]


def test_operations_requiring_confirmation():
    right = Right(id="r1", create=True, read=True, update=True, require_confirmation=True, confirm_read=False)
    rm = RightManager(right)
    # read is allowed but confirm_read=False overrides the global flag.
    assert set(rm.operations_requiring_confirmation()) == {"create", "update"}


# ---------------------------------------------------------------------------
# New: "execute" operation (rights-plugin's divergence from the original —
# odoo-plugin's copy has no such operation, see right_manager.py header).
# ---------------------------------------------------------------------------

def test_execute_is_deny_by_default():
    rm = RightManager(Right(id="r1"))
    assert rm.check("execute").allowed is False


def test_execute_can_be_allowed_and_confirmed_like_any_other_operation():
    right = Right(id="r1", execute=True, confirm_execute=True)
    rm = RightManager(right)
    decision = rm.check("execute")
    assert decision.allowed is True
    assert decision.require_confirmation is True
    with pytest.raises(ConfirmationRequiredError):
        rm.assert_execute()
    rm.assert_execute(confirmed=True)  # does not raise


def test_execute_included_in_all_operations_bulk_helpers():
    right = Right(id="r1", create=True, execute=True, require_confirmation=True, confirm_execute=False)
    rm = RightManager(right)
    # read is allowed by default (Right.read defaults True) alongside create/execute.
    assert set(rm.allowed_operations()) == {"create", "read", "execute"}
    # execute allowed but confirm_execute=False overrides the global flag;
    # create/read have no per-operation override so they inherit it.
    assert set(rm.operations_requiring_confirmation()) == {"create", "read"}
