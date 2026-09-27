"""SDKTable: CRUD manager for a collection of SDKModel instances."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors_manager.errors import NotFoundError, ServiceError
from .file_manager import FileManager
from .models_service import SDKModel
from .secret_service import SecretService


class SDKTable:
    """
    Manages a persisted list of SDKModel instances.

    Non-secret fields are stored in a JSON file (via FileManager).
    Secret fields are stored in the keyring (via SecretService).

    Usage::

        table = SDKTable(
            OdooProfile,
            file_path="/workspace/omop-plugin-config.json",
            keyring_service="odoo-plugin",
        )
        table.save(OdooProfile(id="main", label="Main", password="s3cr3t"))
        profile = table.get("main")
        table.delete("main")
    """

    def __init__(
        self,
        model_class: type[SDKModel],
        *,
        file_path: str | Path,
        keyring_service: str,
    ) -> None:
        pk = model_class._pk_field_name()
        if pk is None:
            raise ValueError(f"Model {model_class.__name__} has no primary_key field")

        self._model = model_class
        self._pk = pk
        self._file = FileManager(file_path)
        self._secrets = SecretService(keyring_service)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _secret_key(self, pk_value: Any, field_name: str) -> str:
        """Keyring key: '<pk>.<field_name>'."""
        return f"{pk_value}.{field_name}"

    def _load_secrets(self, pk_value: Any) -> dict[str, str | None]:
        secrets: dict[str, str | None] = {}
        for field_name, field_def in self._model._fields.items():
            if field_def.secret:
                try:
                    secrets[field_name] = self._secrets.get_secret(
                        self._secret_key(pk_value, field_name)
                    )
                except Exception:
                    secrets[field_name] = None
        return secrets

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, instance: SDKModel) -> None:
        """Insert or update an instance (upsert by primary key)."""
        pk = instance.get_pk()
        self._file.upsert(self._pk, instance.to_record())
        for field_name, value in instance.secret_items().items():
            self._secrets.save_secret(self._secret_key(pk, field_name), str(value))

    def get(self, pk_value: Any) -> SDKModel:
        """Return the instance with the given primary key; raise NotFoundError if absent."""
        record = self._file.read_one(self._pk, pk_value)
        if record is None:
            raise NotFoundError(
                f"{self._model.__name__} '{pk_value}' not found",
                {self._pk: pk_value},
            )
        return self._model.from_record(record, **self._load_secrets(pk_value))

    def get_or_none(self, pk_value: Any) -> SDKModel | None:
        """Return the instance or None if not found."""
        record = self._file.read_one(self._pk, pk_value)
        if record is None:
            return None
        return self._model.from_record(record, **self._load_secrets(pk_value))

    def list(self) -> list[SDKModel]:
        """Return all instances with secrets resolved."""
        return [
            self._model.from_record(r, **self._load_secrets(r.get(self._pk)))
            for r in self._file.read_all()
        ]

    def list_public(self) -> list[dict[str, Any]]:
        """Return all records without secrets (safe for API responses)."""
        return self._file.read_all()

    def delete(self, pk_value: Any) -> bool:
        """Delete an instance and its secrets. Returns True if it existed."""
        deleted = self._file.delete(self._pk, pk_value)
        for field_name, field_def in self._model._fields.items():
            if field_def.secret:
                try:
                    self._secrets.delete_secret(self._secret_key(pk_value, field_name))
                except (NotFoundError, ServiceError):
                    pass
        return deleted
