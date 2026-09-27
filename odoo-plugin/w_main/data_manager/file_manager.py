"""JSON file storage for non-secret model fields."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..errors_manager.errors import ServiceError


class FileManager:
    """Read and write a JSON array of records to a single file."""

    def __init__(self, file_path: str | Path) -> None:
        self._path = Path(file_path)

    # ------------------------------------------------------------------
    # Internal I/O
    # ------------------------------------------------------------------

    def _read(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as exc:
            raise ServiceError(
                "Unable to read data file",
                {"path": str(self._path)},
            ) from exc

    def _write(self, records: list[dict[str, Any]]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
            self._path.chmod(0o600)
        except Exception as exc:
            raise ServiceError(
                "Unable to write data file",
                {"path": str(self._path)},
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_all(self) -> list[dict[str, Any]]:
        return self._read()

    def write_all(self, records: list[dict[str, Any]]) -> None:
        self._write(records)

    def read_one(self, pk_field: str, pk_value: Any) -> dict[str, Any] | None:
        return next(
            (r for r in self._read() if r.get(pk_field) == pk_value),
            None,
        )

    def upsert(self, pk_field: str, record: dict[str, Any]) -> None:
        pk_value = record.get(pk_field)
        records = [r for r in self._read() if r.get(pk_field) != pk_value]
        records.append(record)
        self._write(records)

    def delete(self, pk_field: str, pk_value: Any) -> bool:
        records = self._read()
        filtered = [r for r in records if r.get(pk_field) != pk_value]
        if len(filtered) == len(records):
            return False
        self._write(filtered)
        return True
