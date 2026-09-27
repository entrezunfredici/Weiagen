# Trimmed vs. odoo-plugin/w_main/right_manager/__init__.py — see
# .agents/DECISIONS.md ("rights-plugin: vendoring vs cross-plugin import").
# confirmation_handler.py is NOT vendored: unused here, same as it's unused
# in odoo-plugin today — Hermes's native pre_tool_call → human-approval gate
# is the confirmation mechanism, not a bespoke ConfirmationHandler.
"""Public package exports for the right_manager package."""

from .right_manager import Operation, Right, RightDecision, RightManager

__all__ = [
    "Operation",
    "Right",
    "RightDecision",
    "RightManager",
]
