# Vendored from odoo-plugin/tests/test_table.py — smoke test proving the
# vendored rights_w_main/data_manager copy behaves identically. See
# .agents/DECISIONS.md ("rights-plugin: vendoring vs cross-plugin import").
"""rights_w_main.data_manager.table.SDKTable — CRUD combining FileManager + SecretService."""

import pytest

from rights_w_main.data_manager import SDKTable, SecretField, StringField
from rights_w_main.data_manager.models_service import SDKModel
from rights_w_main.errors_manager.errors import NotFoundError


class Account(SDKModel):
    id: str = StringField(primary_key=True)
    label: str = StringField(default="")
    password: str = SecretField()


@pytest.fixture
def table(tmp_path, monkeypatch):
    monkeypatch.setenv("ODOO_PLUGIN_KEYRING_PATH", str(tmp_path / "keyring.json"))
    return SDKTable(Account, file_path=tmp_path / "accounts.json", keyring_service="test-accounts")


def test_save_and_get_roundtrips_secret_and_non_secret_fields(table):
    table.save(Account(id="a1", label="Account One", password="s3cret"))
    acc = table.get("a1")
    assert acc.label == "Account One"
    assert acc.password == "s3cret"


def test_get_missing_raises_not_found(table):
    with pytest.raises(NotFoundError):
        table.get("missing")


def test_get_or_none_returns_none_for_missing(table):
    assert table.get_or_none("missing") is None


def test_list_returns_all_with_secrets_resolved(table):
    table.save(Account(id="a1", password="p1"))
    table.save(Account(id="a2", password="p2"))
    accounts = {a.id: a.password for a in table.list()}
    assert accounts == {"a1": "p1", "a2": "p2"}


def test_list_public_never_exposes_secret_values(table):
    table.save(Account(id="a1", label="L1", password="s3cret"))
    records = table.list_public()
    assert len(records) == 1
    assert "password" not in records[0]
    assert records[0]["label"] == "L1"


def test_save_upserts_by_primary_key(table):
    table.save(Account(id="a1", label="First", password="p1"))
    table.save(Account(id="a1", label="Updated", password="p2"))
    acc = table.get("a1")
    assert acc.label == "Updated"
    assert acc.password == "p2"


def test_delete_removes_record_and_secret(table):
    table.save(Account(id="a1", password="s3cret"))
    assert table.delete("a1") is True
    assert table.get_or_none("a1") is None
    # Secret for a1 should be gone too, not just orphaned.
    assert table.delete("a1") is False


def test_delete_missing_returns_false(table):
    assert table.delete("missing") is False


def test_model_missing_primary_key_field_raises_on_table_construction(tmp_path, monkeypatch):
    monkeypatch.setenv("ODOO_PLUGIN_KEYRING_PATH", str(tmp_path / "keyring.json"))

    class NoPkModel(SDKModel):
        name: str = StringField()

    with pytest.raises(ValueError):
        SDKTable(NoPkModel, file_path=tmp_path / "x.json", keyring_service="x")
