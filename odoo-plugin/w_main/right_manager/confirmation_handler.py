"""Confirmation handler protocol and built-in implementations.

The RightManager raises ConfirmationRequiredError when an operation needs
explicit user approval.  The action layer catches it and delegates to a
ConfirmationHandler to obtain (or deny) that approval.

Built-in handlers
-----------------
- CLIConfirmationHandler   — interactive terminal prompt
- AutoConfirmHandler       — always confirms  (tests / trusted automation)
- AutoDenyHandler          — always denies    (safe default / read-only contexts)
- AgentConfirmationHandler — re-raises ConfirmationRequiredError so the
                             Claude agent tool-use layer can surface it to
                             the frontend as a CONFIRMATION_REQUIRED response

Custom handler
--------------
Implement the ConfirmationHandler protocol::

    class MyHandler:
        def request(self, operation: str, context: dict) -> bool:
            ...   # return True to confirm, False to cancel

Usage
-----
    from w_main.right_manager import RightManager, Right
    from w_main.right_manager.confirmation_handler import CLIConfirmationHandler
    from w_main.errors_manager.errors import AuthorizationError, ConfirmationRequiredError

    handler = CLIConfirmationHandler()
    rm = RightManager(Right(id="profile", delete=True, confirm_delete=True))

    try:
        rm.assert_delete()
    except ConfirmationRequiredError as exc:
        if not handler.request(exc.details.get("operation", ""), exc.details):
            raise AuthorizationError("Action cancelled by user", exc.details) from exc
        rm.assert_delete(confirmed=True)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..errors_manager.errors import AuthorizationError, ConfirmationRequiredError

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ConfirmationHandler(Protocol):
    """Any object with a ``request`` method qualifies as a handler."""

    def request(self, operation: str, context: dict[str, Any]) -> bool:
        """Ask for confirmation.

        Parameters
        ----------
        operation:
            The CRUD operation being gated (``"create"``, ``"read"``,
            ``"update"``, ``"delete"``).
        context:
            Arbitrary metadata from the ``ConfirmationRequiredError`` details
            (e.g. ``right_id``, model name, record id …).

        Returns
        -------
        bool
            ``True`` → confirmed, proceed.
            ``False`` → cancelled, the caller should raise ``AuthorizationError``.
        """
        ...


# ---------------------------------------------------------------------------
# Built-in implementations
# ---------------------------------------------------------------------------

class CLIConfirmationHandler:
    """Interactive terminal prompt.

    Accepts: o, oui, y, yes  (case-insensitive).
    Everything else is treated as a denial.
    """

    _YES = frozenset({"o", "oui", "y", "yes"})

    def __init__(self, prompt_template: str = "Confirmer '{operation}' ? (o/N) ") -> None:
        self._prompt_template = prompt_template

    def request(self, operation: str, context: dict[str, Any]) -> bool:
        prompt = self._prompt_template.format(operation=operation, **context)
        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in self._YES


class AutoConfirmHandler:
    """Always confirms — use in tests or fully trusted automation."""

    def request(self, operation: str, context: dict[str, Any]) -> bool:
        return True


class AutoDenyHandler:
    """Always denies — safe default for read-only or restricted contexts."""

    def request(self, operation: str, context: dict[str, Any]) -> bool:
        return False


class AgentConfirmationHandler:
    """For Claude agent tool-use contexts.

    Re-raises ``ConfirmationRequiredError`` so the calling tool handler can
    serialize it as a ``CONFIRMATION_REQUIRED`` response and surface the
    confirmation dialog in the openclaw frontend.  The tool is then re-invoked
    with ``confirmed: true`` in the payload.
    """

    def request(self, operation: str, context: dict[str, Any]) -> bool:
        raise ConfirmationRequiredError(
            f"Operation '{operation}' requires user confirmation",
            context,
        )


# ---------------------------------------------------------------------------
# Helper: wrap assert_allowed with automatic confirmation flow
# ---------------------------------------------------------------------------

def guarded(
    assert_fn,
    *,
    handler: ConfirmationHandler,
    operation: str,
    confirmed: bool = False,
) -> None:
    """Call ``assert_fn(confirmed=…)`` and handle ConfirmationRequiredError.

    Parameters
    ----------
    assert_fn:
        A bound method such as ``rm.assert_delete``.
    handler:
        The handler used to request confirmation when needed.
    operation:
        The operation name (forwarded to the handler for display).
    confirmed:
        Pass ``True`` if the caller already has confirmation.

    Raises
    ------
    AuthorizationError
        If the operation is not allowed or the user cancelled.
    ConfirmationRequiredError
        If the handler itself re-raises it (e.g. AgentConfirmationHandler).

    Example
    -------
        guarded(rm.assert_delete, handler=cli_handler, operation="delete")
    """
    try:
        assert_fn(confirmed=confirmed)
    except ConfirmationRequiredError as exc:
        if not handler.request(operation, exc.details or {}):
            raise AuthorizationError(
                f"Operation '{operation}' cancelled by user",
                exc.details,
            ) from exc
        assert_fn(confirmed=True)
