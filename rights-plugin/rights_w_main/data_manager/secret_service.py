# Vendored verbatim from odoo-plugin/w_main/data_manager/secret_service.py
# — see .agents/DECISIONS.md ("rights-plugin: vendoring vs cross-plugin
# import"). Included only so SDKTable (table.py) stays byte-identical to the
# original and importable without modification — rights-plugin declares no
# SecretField on any model (RoleBinding/AccessRight carry no secret data), so
# this module's code paths are never actually exercised here. The
# ODOO_PLUGIN_* env var names below are therefore dead in this plugin's
# context, kept as-is rather than renamed to avoid diverging from the
# original for no functional benefit.
"""Secret storage service — keyring file backend with system keyring fallback."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from ..errors_manager.errors import NotFoundError, ServiceError

try:
    import keyring
except ImportError as exc:
    keyring = None
    _KEYRING_IMPORT_ERROR = exc
else:
    _KEYRING_IMPORT_ERROR = None

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = Exception  # never actually raised when Fernet is unavailable

logger = logging.getLogger(__name__)

# Values written to the file keyring are prefixed once encrypted, so reads
# can tell an encrypted entry from a legacy plaintext one (written before
# ODOO_PLUGIN_ENCRYPTION_KEY existed, or because the key wasn't set at write
# time) without needing a format-version migration step.
_ENC_PREFIX = "enc:v1:"

_warned_no_key = False


def _get_fernet() -> "Fernet | None":
    """Return a Fernet instance from ODOO_PLUGIN_ENCRYPTION_KEY, or None.

    None means "no encryption available" — callers fall back to storing/
    reading plaintext rather than breaking, but log a warning once so the
    gap doesn't go unnoticed. Only used for the FILE keyring; the system
    keyring (macOS Keychain / GNOME Keyring / KWallet) is already
    encrypted at rest by the OS, so double-encrypting there is redundant.
    """
    global _warned_no_key
    if Fernet is None:
        if not _warned_no_key:
            logger.warning(
                "cryptography package not installed — odoo-plugin file keyring "
                "secrets will be stored in PLAINTEXT. Add 'cryptography' to "
                "requirements.txt and reinstall."
            )
            _warned_no_key = True
        return None
    key = os.getenv("ODOO_PLUGIN_ENCRYPTION_KEY", "").strip()
    if not key:
        if not _warned_no_key:
            logger.warning(
                "ODOO_PLUGIN_ENCRYPTION_KEY is not set — odoo-plugin file keyring "
                "secrets will be stored in PLAINTEXT. Generate one with "
                "`python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"` and set it in .env."
            )
            _warned_no_key = True
        return None
    try:
        return Fernet(key.encode("utf-8"))
    except Exception:
        logger.warning("ODOO_PLUGIN_ENCRYPTION_KEY is set but not a valid Fernet key — ignoring it.")
        return None


class SecretService:
    """Persist and resolve secrets for a named service.

    Priority for reads: file keyring → env var → system keyring.
    Writes always target the file keyring when ODOO_PLUGIN_KEYRING_PATH is set,
    otherwise fall back to the system keyring.
    """

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name

    # ------------------------------------------------------------------
    # File keyring helpers
    # ------------------------------------------------------------------

    def _file_keyring_path(self) -> Path | None:
        raw = os.getenv("ODOO_PLUGIN_KEYRING_PATH", "").strip()
        return Path(raw) if raw else None

    def _read_file_keyring(self) -> dict:
        path = self._file_keyring_path()
        if path is None or not path.exists():
            return {"version": 1, "services": {}}
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ServiceError(
                "Unable to read keyring file",
                {"path": str(path), "service": self.service_name},
            ) from exc
        if not isinstance(parsed, dict):
            return {"version": 1, "services": {}}
        if not isinstance(parsed.get("services"), dict):
            parsed["services"] = {}
        return parsed

    def _write_file_keyring(self, store: dict) -> None:
        path = self._file_keyring_path()
        if path is None:
            raise ServiceError(
                "No file keyring path configured (ODOO_PLUGIN_KEYRING_PATH)",
                {"service": self.service_name},
            )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
            path.chmod(0o600)
        except Exception as exc:
            raise ServiceError(
                "Unable to write keyring file",
                {"path": str(path), "service": self.service_name},
            ) from exc

    def _encrypt(self, plaintext: str) -> str:
        fernet = _get_fernet()
        if fernet is None:
            return plaintext
        return _ENC_PREFIX + fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def _decrypt(self, stored: str) -> str:
        if not stored.startswith(_ENC_PREFIX):
            return stored  # legacy plaintext entry, written before encryption was enabled
        fernet = _get_fernet()
        if fernet is None:
            raise ServiceError(
                "Secret is encrypted but ODOO_PLUGIN_ENCRYPTION_KEY is not set (or invalid) "
                "— cannot decrypt.",
                {"service": self.service_name},
            )
        token = stored[len(_ENC_PREFIX):]
        try:
            return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ServiceError(
                "Failed to decrypt secret — wrong ODOO_PLUGIN_ENCRYPTION_KEY.",
                {"service": self.service_name},
            ) from exc

    def _save_file_secret(self, name: str, secret: str) -> bool:
        path = self._file_keyring_path()
        if path is None:
            return False
        store = self._read_file_keyring()
        store["services"].setdefault(self.service_name, {})[name] = self._encrypt(secret)
        self._write_file_keyring(store)
        return True

    def _get_file_secret(self, name: str) -> str | None:
        service = self._read_file_keyring().get("services", {}).get(self.service_name, {})
        if not isinstance(service, dict):
            return None
        value = service.get(name)
        if not isinstance(value, str) or not value:
            return None
        plaintext = self._decrypt(value)
        if not value.startswith(_ENC_PREFIX) and _get_fernet() is not None:
            # Opportunistic migration: a key is now configured but this entry
            # predates it — re-save it encrypted so it doesn't stay in
            # plaintext forever just because nobody re-typed the secret.
            self._save_file_secret(name, plaintext)
        return plaintext

    def _delete_file_secret(self, name: str) -> bool:
        path = self._file_keyring_path()
        if path is None:
            return False
        store = self._read_file_keyring()
        service = store.get("services", {}).get(self.service_name)
        if not isinstance(service, dict) or name not in service:
            return False
        del service[name]
        self._write_file_keyring(store)
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_secret(self, name: str, secret: str) -> None:
        if self._save_file_secret(name, secret):
            return
        if keyring is None:
            raise ServiceError(
                "No secret backend available; set ODOO_PLUGIN_KEYRING_PATH or install keyring",
            ) from _KEYRING_IMPORT_ERROR
        try:
            keyring.set_password(self.service_name, name, secret)
        except Exception as exc:
            raise ServiceError(
                f"Unable to save secret '{name}' for service '{self.service_name}'",
            ) from exc

    def get_secret(self, secret_ref: str) -> str:
        from_file = self._get_file_secret(secret_ref)
        if from_file:
            return from_file

        env_name = f"ODOO_SECRET_{secret_ref.upper()}"
        from_env = os.getenv(env_name)
        if from_env:
            return from_env

        if keyring is None:
            raise ServiceError(
                "No secret backend available; set ODOO_PLUGIN_KEYRING_PATH or install keyring",
                {"secret_ref": secret_ref},
            ) from _KEYRING_IMPORT_ERROR

        try:
            secret = keyring.get_password(self.service_name, secret_ref)
        except keyring.errors.NoKeyringError:
            # No system keyring backend installed/configured (e.g. a headless
            # container with no secret-service daemon) — there is nothing to
            # look up, which is not the same as a backend failing to answer.
            # Fall through to "not found" below instead of surfacing a
            # ServiceError for what is really just an absent secret.
            secret = None
        except Exception as exc:
            raise ServiceError(
                "Unable to read secret from keyring",
                {"secret_ref": secret_ref, "service": self.service_name},
            ) from exc

        if secret is None:
            raise NotFoundError("Secret not found", {"secret_ref": secret_ref})

        return secret

    def delete_secret(self, secret_ref: str) -> bool:
        """Delete a secret. Returns True if it existed, False if not found."""
        if self._delete_file_secret(secret_ref):
            return True

        if keyring is None:
            return False

        try:
            existing = keyring.get_password(self.service_name, secret_ref)
        except keyring.errors.NoKeyringError:
            # No system keyring backend available — nothing to delete.
            return False
        except Exception as exc:
            raise ServiceError(
                f"Unable to delete secret '{secret_ref}' for service '{self.service_name}'",
            ) from exc

        if existing is None:
            return False

        try:
            keyring.delete_password(self.service_name, secret_ref)
            return True
        except keyring.errors.NoKeyringError:
            return False
        except Exception as exc:
            raise ServiceError(
                f"Unable to delete secret '{secret_ref}' for service '{self.service_name}'",
            ) from exc
