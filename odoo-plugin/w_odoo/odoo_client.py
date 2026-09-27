"""Low-level Odoo transport client.

This module only handles communication with Odoo and transport-level errors.
Policy, validation, authorization, logging, and rollback are implemented elsewhere.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

from w_main.errors_manager import ServiceError

try:
    import odoolib
except ImportError as exc:
    odoolib = None
    _ODOOLIB_IMPORT_ERROR = exc
else:
    _ODOOLIB_IMPORT_ERROR = None


class OdooClient:
    def __init__(self, url: str, port: int, database: str, login: str, password: str) -> None:
        if odoolib is None:
            raise ServiceError(
                "odoolib is not installed. Run 'npm run install:python' from the plugin root."
            ) from _ODOOLIB_IMPORT_ERROR

        hostname = self._normalize_hostname(url)
        try:
            self.client = odoolib.get_connection(
                hostname=hostname,
                protocol="jsonrpcs",
                port=port,
                database=database,
                login=login,
                password=password,
            )
        except Exception as exc:
            raise ServiceError(
                f"Unable to connect to Odoo host '{hostname}' on database '{database}'"
            ) from exc

    @staticmethod
    def _normalize_hostname(url: str) -> str:
        parsed = urlparse(url)
        return parsed.hostname or parsed.path or url

    def get_model(self, model_name: str) -> Any:
        try:
            return self.client.get_model(model_name)
        except Exception as exc:
            raise ServiceError(f"Unable to access model '{model_name}'") from exc

    def get_model_schema(self, model: str) -> dict[str, dict]:
        odoo_model = self.get_model(model)
        return odoo_model.fields_get(attributes=["type", "required", "readonly", "string"])

    def get(
        self,
        model_name: str,
        domain: Sequence[Any],
        fields: Sequence[str],
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        try:
            model = self.get_model(model_name)
            search_kwargs = {}
            if limit is not None:
                search_kwargs["limit"] = limit
            return model.search_read(list(domain), list(fields), **search_kwargs)
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(
                f"Unable to get records matching '{domain}' in '{model_name}'"
            ) from exc

    def post(self, model_name: str, values: Mapping[str, Any]) -> int:
        try:
            model = self.get_model(model_name)
            return model.create(dict(values))
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(f"Unable to create record in '{model_name}'") from exc

    def put(
        self,
        model_name: str,
        object_ids: Sequence[int],
        values: Mapping[str, Any],
    ) -> bool:
        try:
            model = self.get_model(model_name)
            return bool(model.write(list(object_ids), dict(values)))
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(f"Unable to update records in '{model_name}'") from exc

    def delete(self, model_name: str, object_ids: Sequence[int]) -> bool:
        try:
            model = self.get_model(model_name)
            return bool(model.unlink(list(object_ids)))
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(f"Unable to delete records in '{model_name}'") from exc
