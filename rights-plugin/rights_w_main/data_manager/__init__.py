# Vendored verbatim from odoo-plugin/w_main/data_manager/__init__.py — see
# .agents/DECISIONS.md ("rights-plugin: vendoring vs cross-plugin import").
"""Public exports for the w_main data_manager package."""

from .field import BoolField, FieldDef, IntField, ListField, SecretField, StringField
from .file_manager import FileManager
from .models_service import SDKModel
from .secret_service import SecretService
from .table import SDKTable

__all__ = [
    "BoolField",
    "FieldDef",
    "FileManager",
    "IntField",
    "ListField",
    "SDKModel",
    "SDKTable",
    "SecretField",
    "SecretService",
    "StringField",
]
