"""Odoo connection profile model and CRUD helpers."""

from __future__ import annotations

import os

from w_main.data_manager import BoolField, IntField, SDKModel, SDKTable, SecretField, StringField


class OdooProfile(SDKModel):
    id:       str  = StringField(primary_key=True)
    label:    str  = StringField()
    base_url: str  = StringField()
    database: str  = StringField()
    login:    str  = StringField()
    password: str  = SecretField()
    enabled:  bool = BoolField(default=True)
    port:     int  = IntField(default=443)


_table = SDKTable(
    OdooProfile,
    file_path=os.getenv("ODOO_PROFILES_FILE_PATH", "/workspace/openclaw-config/odoo-profiles.json"),
    keyring_service="odoo-plugin",
)


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

def create_odoo_profile(
    id: str,
    label: str,
    base_url: str,
    database: str,
    login: str,
    password: str,
    enabled: bool = True,
    port: int = 443,
) -> OdooProfile:
    profile = OdooProfile(
        id=id,
        label=label,
        base_url=base_url,
        database=database,
        login=login,
        password=password,
        enabled=enabled,
        port=port,
    )
    _table.save(profile)
    return profile


def get_odoo_profiles() -> list[OdooProfile]:
    return _table.list()


def get_odoo_profile(profile_id: str) -> OdooProfile:
    return _table.get(profile_id)


def get_odoo_profile_or_none(profile_id: str) -> OdooProfile | None:
    return _table.get_or_none(profile_id)


def delete_odoo_profile(profile_id: str) -> bool:
    return _table.delete(profile_id)


# ------------------------------------------------------------------
# Filtres
# ------------------------------------------------------------------

def filter_profiles(**kwargs) -> list[OdooProfile]:
    """Retourne les profils dont les champs correspondent aux kwargs.

    Exemple :
        filter_profiles(enabled=True)
        filter_profiles(database="mydb", enabled=True)
    """
    return [
        p for p in _table.list()
        if all(getattr(p, field, None) == value for field, value in kwargs.items())
    ]
