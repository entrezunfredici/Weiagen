"""Public package exports for the embedded Odoo connector."""

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
