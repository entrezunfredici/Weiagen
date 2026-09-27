"""w_odoo.odoo_profile — OdooProfile CRUD.

Uses the module-level `_table` singleton (env vars set once in
tests/conftest.py, data files truncated before every test by the
`_reset_plugin_data_files` autouse fixture).
"""

import pytest

from w_main.errors_manager.errors import NotFoundError
from w_odoo.odoo_profile import (
    create_odoo_profile,
    delete_odoo_profile,
    filter_profiles,
    get_odoo_profile,
    get_odoo_profile_or_none,
    get_odoo_profiles,
)


def test_create_and_get_profile():
    create_odoo_profile(
        id="p1", label="Profile One", base_url="https://odoo.example.com",
        database="db1", login="ai@example.com", password="s3cret",
    )
    profile = get_odoo_profile("p1")
    assert profile.label == "Profile One"
    assert profile.database == "db1"
    assert profile.password == "s3cret"
    assert profile.enabled is True
    assert profile.port == 443


def test_get_missing_profile_raises_not_found():
    with pytest.raises(NotFoundError):
        get_odoo_profile("missing")


def test_get_or_none_missing_returns_none():
    assert get_odoo_profile_or_none("missing") is None


def test_create_disabled_profile():
    create_odoo_profile(
        id="p1", label="P", base_url="https://x", database="db", login="l", password="pw",
        enabled=False,
    )
    assert get_odoo_profile("p1").enabled is False


def test_list_profiles():
    create_odoo_profile(id="p1", label="P1", base_url="https://x", database="db", login="l", password="pw")
    create_odoo_profile(id="p2", label="P2", base_url="https://x", database="db", login="l", password="pw")
    ids = {p.id for p in get_odoo_profiles()}
    assert ids == {"p1", "p2"}


def test_delete_profile():
    create_odoo_profile(id="p1", label="P", base_url="https://x", database="db", login="l", password="pw")
    assert delete_odoo_profile("p1") is True
    assert get_odoo_profile_or_none("p1") is None
    assert delete_odoo_profile("p1") is False


def test_filter_profiles_by_field():
    create_odoo_profile(id="p1", label="P1", base_url="https://x", database="db1", login="l", password="pw", enabled=True)
    create_odoo_profile(id="p2", label="P2", base_url="https://x", database="db2", login="l", password="pw", enabled=False)
    enabled = filter_profiles(enabled=True)
    assert [p.id for p in enabled] == ["p1"]


def test_filter_profiles_multiple_kwargs():
    create_odoo_profile(id="p1", label="P1", base_url="https://x", database="db1", login="l", password="pw", enabled=True)
    create_odoo_profile(id="p2", label="P2", base_url="https://x", database="db1", login="l", password="pw", enabled=False)
    result = filter_profiles(database="db1", enabled=True)
    assert [p.id for p in result] == ["p1"]


def test_save_upserts_existing_profile():
    create_odoo_profile(id="p1", label="Original", base_url="https://x", database="db", login="l", password="pw")
    create_odoo_profile(id="p1", label="Updated", base_url="https://x", database="db", login="l", password="pw2")
    profile = get_odoo_profile("p1")
    assert profile.label == "Updated"
    assert profile.password == "pw2"
