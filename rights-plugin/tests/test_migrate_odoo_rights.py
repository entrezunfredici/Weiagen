"""rights_plugin.migrate_odoo_rights — legacy OdooRight -> AccessRight.

Fixture data below reproduces exactly the 2 real rights configured on
test-server at the time this migration was written (profile "1": project.project
create+read, project.task create+read+update, neither requiring
confirmation, neither allowing delete) — see .agents/CHANGELOG_AGENT.md.
"""

import json

import models
from migrate_odoo_rights import maybe_migrate_odoo_rights_on_load, migrate_odoo_rights

_MTB1_LEGACY_RIGHTS = [
    {
        "id": "f5e7574a-fcaf-4795-907d-03679e8208db",
        "label": "",
        "profile_id": "1",
        "odoo_model": "project.project",
        "fields": ["*"],
        "create": True,
        "read": True,
        "update": False,
        "delete": False,
        "require_confirmation": False,
        "confirm_create": False,
        "confirm_read": False,
        "confirm_update": False,
        "confirm_delete": False,
    },
    {
        "id": "45b9d9af-0be1-46a6-9388-641de0706f29",
        "label": "",
        "profile_id": "1",
        "odoo_model": "project.task",
        "fields": ["*"],
        "create": True,
        "read": True,
        "update": True,
        "delete": False,
        "require_confirmation": False,
        "confirm_create": False,
        "confirm_read": False,
        "confirm_update": False,
        "confirm_delete": False,
    },
]


def _write_legacy_file(tmp_path, records=_MTB1_LEGACY_RIGHTS):
    path = tmp_path / "odoo-rights.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def test_missing_source_file_returns_empty_list(tmp_path):
    result = migrate_odoo_rights(source_path=str(tmp_path / "does-not-exist.json"))
    assert result == []


def test_migrates_each_legacy_right_to_an_access_right_bound_to_everyone(tmp_path):
    path = _write_legacy_file(tmp_path)
    migrated = migrate_odoo_rights(source_path=str(path))
    assert len(migrated) == 2

    rights = {r.resource_id: r for r in models.list_access_rights()}
    assert set(rights) == {"1:project.project", "1:project.task"}

    project = rights["1:project.project"]
    assert project.roles == ["everyone"]
    assert project.resource_type == "odoo_model"
    assert project.fields == ["*"]
    assert project.create is True
    assert project.read is True
    assert project.update is False
    assert project.delete is False
    assert project.require_confirmation is False
    assert project.id == "migrated:f5e7574a-fcaf-4795-907d-03679e8208db"

    task = rights["1:project.task"]
    assert task.create is True
    assert task.read is True
    assert task.update is True
    assert task.delete is False


def test_dry_run_reports_without_writing(tmp_path):
    path = _write_legacy_file(tmp_path)
    migrated = migrate_odoo_rights(source_path=str(path), dry_run=True)
    assert len(migrated) == 2
    assert models.list_access_rights() == []


def test_migration_is_idempotent(tmp_path):
    path = _write_legacy_file(tmp_path)
    migrate_odoo_rights(source_path=str(path))
    migrate_odoo_rights(source_path=str(path))
    # Upsert by id — re-running must not duplicate.
    assert len(models.list_access_rights()) == 2


def test_entries_without_id_are_skipped(tmp_path):
    path = tmp_path / "odoo-rights.json"
    path.write_text(json.dumps([{"profile_id": "1", "odoo_model": "res.partner"}]), encoding="utf-8")
    migrated = migrate_odoo_rights(source_path=str(path))
    assert migrated == []
    assert models.list_access_rights() == []


def test_non_list_json_returns_empty(tmp_path):
    path = tmp_path / "odoo-rights.json"
    path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    assert migrate_odoo_rights(source_path=str(path)) == []


# ---------------------------------------------------------------------------
# maybe_migrate_odoo_rights_on_load — the auto-trigger used by register()
# ---------------------------------------------------------------------------


def test_auto_migrate_runs_once_when_legacy_file_present(tmp_path, monkeypatch):
    path = _write_legacy_file(tmp_path)
    monkeypatch.setenv("ODOO_RIGHTS_PATH", str(path))
    maybe_migrate_odoo_rights_on_load()
    assert len(models.list_access_rights()) == 2


def test_auto_migrate_is_a_noop_when_already_migrated(tmp_path, monkeypatch):
    path = _write_legacy_file(tmp_path)
    monkeypatch.setenv("ODOO_RIGHTS_PATH", str(path))
    maybe_migrate_odoo_rights_on_load()
    # Manually tamper with one migrated right to prove a second run doesn't touch it.
    right = models.get_access_right("migrated:f5e7574a-fcaf-4795-907d-03679e8208db")
    right.label = "manually edited after migration"
    models.save_access_right(right)

    maybe_migrate_odoo_rights_on_load()

    unchanged = models.get_access_right("migrated:f5e7574a-fcaf-4795-907d-03679e8208db")
    assert unchanged.label == "manually edited after migration"


def test_auto_migrate_is_a_noop_when_no_legacy_file(monkeypatch):
    monkeypatch.setenv("ODOO_RIGHTS_PATH", "/nonexistent/path.json")
    maybe_migrate_odoo_rights_on_load()
    assert models.list_access_rights() == []


def test_auto_migrate_is_a_noop_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("ODOO_RIGHTS_PATH", raising=False)
    maybe_migrate_odoo_rights_on_load()
    assert models.list_access_rights() == []
