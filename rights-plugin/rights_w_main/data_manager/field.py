# Vendored verbatim from odoo-plugin/w_main/data_manager/field.py — see
# .agents/DECISIONS.md ("rights-plugin: vendoring vs cross-plugin import").
"""Field descriptors for SDKModel schema declaration."""

from __future__ import annotations

_MISSING = object()


class FieldDef:
    """Describes one field of an SDKModel."""

    def __init__(
        self,
        *,
        secret: bool = False,
        primary_key: bool = False,
        default=_MISSING,
    ) -> None:
        self.secret = secret
        self.primary_key = primary_key
        self.default = default

    def has_default(self) -> bool:
        return self.default is not _MISSING


MISSING = _MISSING


def StringField(*, primary_key: bool = False, default=_MISSING, secret: bool = False) -> FieldDef:
    return FieldDef(secret=secret, primary_key=primary_key, default=default)


def SecretField(*, default=_MISSING) -> FieldDef:
    return FieldDef(secret=True, primary_key=False, default=default)


def IntField(*, primary_key: bool = False, default=_MISSING) -> FieldDef:
    return FieldDef(secret=False, primary_key=primary_key, default=default)


def BoolField(*, default=_MISSING) -> FieldDef:
    return FieldDef(secret=False, primary_key=False, default=default)


def ListField(*, default_factory=list) -> FieldDef:
    # default is evaluated lazily via default_factory — keep the field
    # "defaultless" (_MISSING, same sentinel every other *Field() uses) so
    # has_default() stays False and models_service.SDKModel.__init__ falls
    # through to _list_default_factory() instead of ever assigning `None`.
    f = FieldDef(secret=False, primary_key=False, default=_MISSING)
    f._list_default_factory = default_factory  # type: ignore[attr-defined]
    return f
