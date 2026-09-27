"""rights_plugin.models — Role catalog CRUD, plus the migration/seed
functions that run as a module-level side effect (models.py import time)."""

import json

import models
from models import create_role, delete_role, get_role, get_role_or_none, list_roles, save_role
from rights_w_main.errors_manager.errors import NotFoundError

import pytest


def test_create_role_minimal():
    role = create_role("admin")
    assert role.id == "admin"
    assert role.label == ""
    assert role.description == ""


def test_create_role_with_label_and_description():
    role = create_role("admin", label="Administrateur", description="Full access")
    assert role.label == "Administrateur"
    assert role.description == "Full access"


def test_create_role_upserts_by_id():
    create_role("admin", label="First")
    create_role("admin", label="Second")
    assert get_role("admin").label == "Second"
    assert len(list_roles()) == 1


def test_get_role_missing_raises_not_found():
    with pytest.raises(NotFoundError):
        get_role("missing")


def test_get_role_or_none_missing_returns_none():
    assert get_role_or_none("missing") is None


def test_save_role_direct():
    role = models.Role(id="finance", label="Finance")
    save_role(role)
    assert get_role("finance").label == "Finance"


def test_delete_role():
    create_role("admin")
    assert delete_role("admin") is True
    assert get_role_or_none("admin") is None
    assert delete_role("admin") is False


def test_list_roles_returns_all():
    create_role("admin")
    create_role("finance")
    assert {r.id for r in list_roles()} == {"admin", "finance"}


# ---------------------------------------------------------------------------
# migrate_access_right_role_field — schema migration for already-stored
# AccessRight rows (role: str -> roles: list). Runs automatically at
# `models.py` import time; exercised directly here against a hand-crafted
# raw file state, the only practical way to test an import-time side
# effect.
# ---------------------------------------------------------------------------


def test_migrate_access_right_role_field_rewrites_legacy_records():
    legacy_record = {
        "id": "r1", "label": "", "role": "admin", "resource_type": "hermes_tool",
        "resource_id": "shell_exec", "fields": ["*"], "create": False, "read": True,
        "update": False, "delete": False, "execute": False, "require_confirmation": False,
        "confirm_create": False, "confirm_read": False, "confirm_update": False,
        "confirm_delete": False, "confirm_execute": False,
    }
    models._access_rights_table._file.write_all([legacy_record])

    changed = models.migrate_access_right_role_field()

    assert changed == 1
    stored = models.get_access_right("r1")
    assert stored.roles == ["admin"]
    raw = models._access_rights_table._file.read_all()
    assert "role" not in raw[0]
    assert raw[0]["roles"] == ["admin"]


def test_migrate_access_right_role_field_is_idempotent():
    models._access_rights_table._file.write_all([
        {"id": "r1", "role": "admin", "resource_type": "hermes_tool", "resource_id": "shell_exec", "fields": ["*"]},
    ])
    first = models.migrate_access_right_role_field()
    second = models.migrate_access_right_role_field()
    assert first == 1
    assert second == 0  # already "roles" -> nothing left to rewrite


def test_migrate_access_right_role_field_leaves_already_migrated_records_untouched():
    models._access_rights_table._file.write_all([
        {"id": "r1", "roles": ["admin", "finance"], "resource_type": "hermes_tool", "resource_id": "shell_exec", "fields": ["*"]},
    ])
    changed = models.migrate_access_right_role_field()
    assert changed == 0
    assert models.get_access_right("r1").roles == ["admin", "finance"]


def test_migrate_access_right_role_field_handles_missing_file_gracefully():
    # No file has been written at all in this test — read_all() returns []
    # for a missing path, migrate must not raise.
    assert models.migrate_access_right_role_field() == 0


# ---------------------------------------------------------------------------
# seed_role_catalog
# ---------------------------------------------------------------------------


def test_seed_role_catalog_creates_everyone_and_automation():
    models.seed_role_catalog()
    assert get_role_or_none("everyone") is not None
    assert get_role_or_none("automation") is not None


def test_seed_role_catalog_backfills_roles_from_bindings_and_rights():
    models.bind_role("slack", "U1", ["admin"])
    models.create_access_right(["finance"], "hermes_tool", "shell_exec")
    models.seed_role_catalog()
    ids = {r.id for r in list_roles()}
    assert {"admin", "finance", "everyone", "automation"} <= ids


def test_seed_role_catalog_never_overwrites_an_existing_label():
    create_role("admin", label="Custom label")
    models.seed_role_catalog()
    assert get_role("admin").label == "Custom label"


def test_seed_role_catalog_is_idempotent_on_created_count():
    first = models.seed_role_catalog()
    second = models.seed_role_catalog()
    assert first >= 2  # at least everyone + automation on a clean table
    assert second == 0
