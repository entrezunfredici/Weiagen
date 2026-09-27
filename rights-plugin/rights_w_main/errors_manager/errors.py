# Vendored verbatim from odoo-plugin/w_main/errors_manager/errors.py — see
# .agents/DECISIONS.md ("rights-plugin: vendoring vs cross-plugin import")
# for why this is a copy, not a shared import. Keep in sync by hand; a
# `diff -r rights-plugin/w_main odoo-plugin/w_main` (ignoring this header
# and the right_manager.py "execute" operation extension, see that file) is
# the sanity check for drift.
"""Structured error classes for the deny-by-default rights engine."""

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
