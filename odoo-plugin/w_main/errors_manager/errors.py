"""Structured error classes for the Odoo connector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ConnectorError(Exception):
    """Base connector error with machine-readable metadata."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details or {},
            },
        }


class ValidationError(ConnectorError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("VALIDATION_ERROR", message, details)


class AuthorizationError(ConnectorError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("AUTHORIZATION_DENIED", message, details)


class ConfirmationRequiredError(ConnectorError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("CONFIRMATION_REQUIRED", message, details)


class NotFoundError(ConnectorError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("NOT_FOUND", message, details)


class ServiceError(ConnectorError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("SERVICE_ERROR", message, details)


class ConfigurationError(ConnectorError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("CONFIGURATION_ERROR", message, details)
