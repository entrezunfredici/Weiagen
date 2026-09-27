"""Generic rights and confirmation management.

Provides a deny-by-default operation gate usable in any context (Odoo
connector, API endpoints, CLI tools, …).

Typical usage
-------------
    right = Right(
        id="admin-profile",
        create=True, read=True, update=True, delete=True,
        confirm_delete=True,
    )
    rm = RightManager(right)

    # Simple check — raises AuthorizationError or ConfirmationRequiredError
    rm.assert_create()
    rm.assert_delete()               # → raises ConfirmationRequiredError
    rm.assert_delete(confirmed=True) # → OK

    # Non-raising introspection
    decision = rm.check("delete")
    decision.allowed                 # True
    decision.require_confirmation    # True
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..errors_manager.errors import AuthorizationError, ConfirmationRequiredError

Operation = Literal["create", "read", "update", "delete"]

_ALL_OPERATIONS: tuple[Operation, ...] = ("create", "read", "update", "delete")


# ---------------------------------------------------------------------------
# Right definition
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Right:
    """Defines what is allowed for a given subject/profile.

    Per-operation confirmation flags (``confirm_*``) override the global
    ``require_confirmation`` flag.  If a global flag is set, every operation
    requires confirmation unless its specific flag is explicitly ``False``.
    """

    id: str

    # Allowed operations (deny-by-default)
    create: bool = False
    read:   bool = True
    update: bool = False
    delete: bool = False

    # Confirmation requirement (global, then per-operation)
    require_confirmation: bool = False
    confirm_create: bool | None = None
    confirm_read:   bool | None = None
    confirm_update: bool | None = None
    confirm_delete: bool | None = None

    def is_allowed(self, operation: Operation) -> bool:
        return bool(getattr(self, operation, False))

    def needs_confirmation(self, operation: Operation) -> bool:
        """Return True if this operation requires explicit confirmation."""
        specific = getattr(self, f"confirm_{operation}", None)
        if specific is not None:
            return bool(specific)
        return self.require_confirmation


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RightDecision:
    """Result of a non-raising rights check."""

    operation:            Operation
    allowed:              bool
    require_confirmation: bool
    reason:               str

    def is_ready(self, *, confirmed: bool = False) -> bool:
        """True when the operation can proceed (allowed and confirmation satisfied)."""
        return self.allowed and (not self.require_confirmation or confirmed)


# ---------------------------------------------------------------------------
# RightManager
# ---------------------------------------------------------------------------

class RightManager:
    """Gate for CRUD operations based on a :class:`Right` definition.

    Two usage styles:

    **Asserting** (raises on failure — use in service / action layers)::

        rm.assert_create()
        rm.assert_delete(confirmed=True)

    **Inspecting** (returns a :class:`RightDecision` — use when you need
    details before acting)::

        decision = rm.check("delete")
        if not decision.allowed:
            ...
        if decision.require_confirmation and not confirmed:
            raise ConfirmationRequiredError(...)
    """

    def __init__(self, right: Right) -> None:
        self._right = right

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def check(self, operation: Operation) -> RightDecision:
        """Return a :class:`RightDecision` without raising."""
        allowed = self._right.is_allowed(operation)
        confirm = self._right.needs_confirmation(operation) if allowed else False

        if not allowed:
            reason = f"Operation '{operation}' is not allowed for right '{self._right.id}'"
        elif confirm:
            reason = f"Operation '{operation}' requires confirmation"
        else:
            reason = f"Operation '{operation}' is allowed"

        return RightDecision(
            operation=operation,
            allowed=allowed,
            require_confirmation=confirm,
            reason=reason,
        )

    def assert_allowed(self, operation: Operation, *, confirmed: bool = False) -> None:
        """Raise :class:`AuthorizationError` if not allowed, or
        :class:`ConfirmationRequiredError` if confirmation is needed and
        ``confirmed`` is ``False``.
        """
        decision = self.check(operation)

        if not decision.allowed:
            raise AuthorizationError(
                decision.reason, {"operation": operation, "right_id": self._right.id}
            )

        if decision.require_confirmation and not confirmed:
            raise ConfirmationRequiredError(
                decision.reason,
                {"operation": operation, "right_id": self._right.id},
            )

    # ------------------------------------------------------------------
    # Per-operation convenience methods
    # ------------------------------------------------------------------

    def assert_create(self, *, confirmed: bool = False) -> None:
        self.assert_allowed("create", confirmed=confirmed)

    def assert_read(self, *, confirmed: bool = False) -> None:
        self.assert_allowed("read", confirmed=confirmed)

    def assert_update(self, *, confirmed: bool = False) -> None:
        self.assert_allowed("update", confirmed=confirmed)

    def assert_delete(self, *, confirmed: bool = False) -> None:
        self.assert_allowed("delete", confirmed=confirmed)

    # ------------------------------------------------------------------
    # Bulk helpers
    # ------------------------------------------------------------------

    def allowed_operations(self) -> list[Operation]:
        """Return the list of operations that are allowed (ignoring confirmation)."""
        return [op for op in _ALL_OPERATIONS if self._right.is_allowed(op)]

    def operations_requiring_confirmation(self) -> list[Operation]:
        """Return allowed operations that require confirmation."""
        return [
            op for op in _ALL_OPERATIONS
            if self._right.is_allowed(op) and self._right.needs_confirmation(op)
        ]
