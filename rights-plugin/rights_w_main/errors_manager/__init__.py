# Vendored verbatim from odoo-plugin/w_main/errors_manager/__init__.py —
# see .agents/DECISIONS.md ("rights-plugin: vendoring vs cross-plugin import").
"""Public package exports for the errors_manager package."""

from .errors import (
    AuthorizationError,
    ConfigurationError,
    ConfirmationRequiredError,
    ConnectorError,
    NotFoundError,
    ServiceError,
    ValidationError,
)

__all__ = [
    "AuthorizationError",
    "ConfigurationError",
    "ConfirmationRequiredError",
    "ConnectorError",
    "NotFoundError",
    "ServiceError",
    "ValidationError",
]
