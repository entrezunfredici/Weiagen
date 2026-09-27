"""SDKModel base class with declarative field schema."""

from __future__ import annotations

from typing import Any, ClassVar

from .field import FieldDef


class _ModelMeta(type):
    """Collect FieldDef class attributes into _fields and remove them from the namespace."""

    def __new__(mcs, name: str, bases: tuple, namespace: dict) -> _ModelMeta:
        fields: dict[str, FieldDef] = {}

        # Inherit fields from base classes (left-to-right, subclass wins)
        for base in reversed(bases):
            if hasattr(base, "_fields"):
                fields.update(base._fields)

        # Collect FieldDef instances declared on this class
        to_remove = [k for k, v in namespace.items() if isinstance(v, FieldDef)]
        for attr in to_remove:
            fields[attr] = namespace.pop(attr)

        namespace["_fields"] = fields
        return super().__new__(mcs, name, bases, namespace)


class SDKModel(metaclass=_ModelMeta):
    """
    Declarative model base class.

    Subclasses declare fields using FieldDef factories::

        class OdooProfile(SDKModel):
            id: str = StringField(primary_key=True)
            label: str = StringField()
            password: str = SecretField()

    Non-secret fields are persisted to a JSON file via FileManager.
    Secret fields are persisted to the keyring via SecretService.
    """

    _fields: ClassVar[dict[str, FieldDef]]

    def __init__(self, **kwargs: Any) -> None:
        for field_name, field_def in self._fields.items():
            if field_name in kwargs:
                value = kwargs[field_name]
            elif field_def.has_default():
                value = field_def.default
            elif hasattr(field_def, "_list_default_factory"):
                value = field_def._list_default_factory()  # type: ignore[attr-defined]
            else:
                value = None
            object.__setattr__(self, field_name, value)

    # ------------------------------------------------------------------
    # Primary key helpers
    # ------------------------------------------------------------------

    @classmethod
    def _pk_field_name(cls) -> str | None:
        for name, field_def in cls._fields.items():
            if field_def.primary_key:
                return name
        return None

    def get_pk(self) -> Any:
        pk_name = self._pk_field_name()
        if pk_name is None:
            raise ValueError(f"No primary key defined on {type(self).__name__}")
        return getattr(self, pk_name)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        """Return only non-secret fields for JSON file storage."""
        return {
            name: getattr(self, name)
            for name, field_def in self._fields.items()
            if not field_def.secret
        }

    def secret_items(self) -> dict[str, str]:
        """Return secret field name → value pairs (None values excluded)."""
        return {
            name: getattr(self, name)
            for name, field_def in self._fields.items()
            if field_def.secret and getattr(self, name) is not None
        }

    @classmethod
    def from_record(cls, record: dict[str, Any], **secrets: str) -> SDKModel:
        """Reconstruct an instance from stored record + resolved secrets."""
        return cls(**{**record, **secrets})

    def __repr__(self) -> str:
        parts = ", ".join(
            f"{name}=***" if field_def.secret else f"{name}={getattr(self, name)!r}"
            for name, field_def in self._fields.items()
        )
        return f"{type(self).__name__}({parts})"
