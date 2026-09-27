"""w_main.right_manager.right_manager — deny-by-default CRUD gate."""

import pytest

from w_main.errors_manager.errors import AuthorizationError, ConfirmationRequiredError
from w_main.right_manager.right_manager import Right, RightManager


def test_defaults_are_deny_by_default_except_read():
    right = Right(id="r1")
    assert right.is_allowed("read") is True
    assert right.is_allowed("create") is False
    assert right.is_allowed("update") is False
    assert right.is_allowed("delete") is False


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
