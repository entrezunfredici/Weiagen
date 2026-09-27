"""Public package exports for the embedded Odoo connector."""

from . import rights_bridge
from .odoo_cli_for_ai import OdooAIExecutor
from .odoo_cli_for_config import OdooConfigExecutor
from .odoo_client import OdooClient
from .odoo_profile import (
    OdooProfile,
    create_odoo_profile,
    delete_odoo_profile,
    filter_profiles,
    get_odoo_profile,
    get_odoo_profile_or_none,
    get_odoo_profiles,
)

__all__ = [
    "OdooAIExecutor",
    "OdooClient",
    "OdooConfigExecutor",
    "OdooProfile",
    "create_odoo_profile",
    "delete_odoo_profile",
    "filter_profiles",
    "get_odoo_profile",
    "get_odoo_profile_or_none",
    "get_odoo_profiles",
    "rights_bridge",
]
