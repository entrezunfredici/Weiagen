# Vendored from odoo-plugin/tests/test_secret_service.py — smoke test
# proving the vendored rights_w_main/data_manager copy behaves identically (this
# code path is unused in rights-plugin's own models, see
# rights_w_main/data_manager/secret_service.py's header — kept covered anyway
# since it's part of the verbatim copy). See .agents/DECISIONS.md
# ("rights-plugin: vendoring vs cross-plugin import").
"""rights_w_main.data_manager.secret_service.SecretService — file keyring, Fernet
encryption, env-var fallback, legacy-plaintext migration.
"""

import json

import pytest

from rights_w_main.data_manager.secret_service import SecretService
from rights_w_main.errors_manager.errors import NotFoundError, ServiceError


@pytest.fixture
def keyring_path(tmp_path, monkeypatch):
    path = tmp_path / "keyring.json"
    monkeypatch.setenv("ODOO_PLUGIN_KEYRING_PATH", str(path))
    return path


def test_save_and_get_secret_roundtrip(keyring_path):
    svc = SecretService("svc")
    svc.save_secret("ref1", "s3cret")
    assert svc.get_secret("ref1") == "s3cret"


def test_get_secret_not_found_raises(keyring_path):
    svc = SecretService("svc")
    with pytest.raises(NotFoundError):
        svc.get_secret("missing")


def test_get_secret_falls_back_to_env_var(keyring_path, monkeypatch):
    monkeypatch.setenv("ODOO_SECRET_MY_REF", "env-value")
    svc = SecretService("svc")
    assert svc.get_secret("my_ref") == "env-value"


def test_delete_secret_existing_and_missing(keyring_path):
    svc = SecretService("svc")
    svc.save_secret("ref1", "s3cret")
    assert svc.delete_secret("ref1") is True
    assert svc.delete_secret("ref1") is False


def test_secrets_are_scoped_per_service_name(keyring_path):
    svc_a = SecretService("service-a")
    svc_b = SecretService("service-b")
    svc_a.save_secret("ref1", "for-a")
    with pytest.raises(NotFoundError):
        svc_b.get_secret("ref1")


def test_plaintext_when_no_encryption_key_set(keyring_path):
    svc = SecretService("svc")
    svc.save_secret("ref1", "s3cret")
    raw = json.loads(keyring_path.read_text())
    assert raw["services"]["svc"]["ref1"] == "s3cret"  # not enc:v1: prefixed


def test_encrypted_when_key_set(keyring_path, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("ODOO_PLUGIN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    svc = SecretService("svc")
    svc.save_secret("ref1", "s3cret")
    raw = json.loads(keyring_path.read_text())
    assert raw["services"]["svc"]["ref1"].startswith("enc:v1:")
    assert svc.get_secret("ref1") == "s3cret"


def test_wrong_key_fails_to_decrypt(keyring_path, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("ODOO_PLUGIN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    svc = SecretService("svc")
    svc.save_secret("ref1", "s3cret")

    monkeypatch.setenv("ODOO_PLUGIN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(ServiceError):
        svc.get_secret("ref1")


def test_legacy_plaintext_entry_is_migrated_to_encrypted_on_read(keyring_path, monkeypatch):
    from cryptography.fernet import Fernet

    # Write a legacy plaintext entry directly, as if it predated encryption.
    svc = SecretService("svc")
    svc.save_secret("ref1", "s3cret")
    raw = json.loads(keyring_path.read_text())
    assert raw["services"]["svc"]["ref1"] == "s3cret"

    # Now a key becomes available — the next read should re-save it encrypted.
    monkeypatch.setenv("ODOO_PLUGIN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert svc.get_secret("ref1") == "s3cret"
    raw_after = json.loads(keyring_path.read_text())
    assert raw_after["services"]["svc"]["ref1"].startswith("enc:v1:")


def test_no_keyring_path_configured_falls_back_to_service_error_or_env(tmp_path, monkeypatch):
    monkeypatch.delenv("ODOO_PLUGIN_KEYRING_PATH", raising=False)
    monkeypatch.delenv("ODOO_SECRET_REF1", raising=False)
    svc = SecretService("svc-no-path")
    # No file keyring path, no env var, and (most likely) no system keyring
    # backend available in this sandboxed test environment either way — the
    # important contract is that it fails closed, never silently succeeds.
    with pytest.raises((NotFoundError, ServiceError)):
        svc.get_secret("ref1")
