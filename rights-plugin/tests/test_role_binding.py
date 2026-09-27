"""rights_plugin.models — RoleBinding CRUD + identity lookups."""

from models import (
    bind_role,
    get_role_binding,
    get_role_binding_for_identity,
    get_role_binding_or_none,
    list_role_bindings,
    role_bindings_for_platform,
    unbind_role,
)
from rights_w_main.errors_manager.errors import NotFoundError

import pytest


def test_bind_role_creates_binding_with_composite_id():
    binding = bind_role("slack", "U0123", ["admin", "finance"])
    assert binding.id == "slack:U0123"
    assert binding.platform == "slack"
    assert binding.external_user_id == "U0123"
    assert binding.roles == ["admin", "finance"]


def test_bind_role_upserts_existing_identity():
    bind_role("slack", "U0123", ["admin"])
    bind_role("slack", "U0123", ["finance", "hr"])
    binding = get_role_binding_for_identity("slack", "U0123")
    assert binding.roles == ["finance", "hr"]


def test_get_role_binding_by_id():
    bind_role("telegram", "42", ["reader"])
    binding = get_role_binding("telegram:42")
    assert binding.roles == ["reader"]


def test_get_role_binding_missing_raises_not_found():
    with pytest.raises(NotFoundError):
        get_role_binding("slack:missing")


def test_get_role_binding_for_identity_returns_none_when_absent():
    assert get_role_binding_for_identity("slack", "ghost") is None


def test_get_role_binding_or_none_missing_returns_none():
    assert get_role_binding_or_none("slack:missing") is None


def test_unbind_role_removes_binding():
    bind_role("slack", "U0123", ["admin"])
    assert unbind_role("slack", "U0123") is True
    assert get_role_binding_for_identity("slack", "U0123") is None
    assert unbind_role("slack", "U0123") is False


def test_list_role_bindings_returns_all():
    bind_role("slack", "U1", ["a"])
    bind_role("telegram", "42", ["b"])
    assert {b.id for b in list_role_bindings()} == {"slack:U1", "telegram:42"}


def test_role_bindings_for_platform_filters():
    bind_role("slack", "U1", ["a"])
    bind_role("slack", "U2", ["b"])
    bind_role("telegram", "42", ["c"])
    slack_bindings = role_bindings_for_platform("slack")
    assert {b.external_user_id for b in slack_bindings} == {"U1", "U2"}


def test_identities_are_scoped_per_platform():
    # Same external id on two different platforms must not collide.
    bind_role("slack", "U1", ["slack-role"])
    bind_role("telegram", "U1", ["telegram-role"])
    assert get_role_binding_for_identity("slack", "U1").roles == ["slack-role"]
    assert get_role_binding_for_identity("telegram", "U1").roles == ["telegram-role"]
