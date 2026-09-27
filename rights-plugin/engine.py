"""Deny-by-default decision engine: (roles, resource, operation) -> RightDecision.

Generalizes odoo-plugin's ``w_odoo.odoo_rights.get_right_manager_for`` (see
``.agents/DECISIONS.md`` for the parity mapping) with one added dimension —
an identity can now hold *multiple* roles, not just one implicit "whoever is
configured for this profile".

Combination rule across an identity's roles, decided explicitly with Fred
(see ``.agents/DECISIONS.md``, "règle de combinaison multi-rôles"): **most
permissive wins** — allowed if at least one role's matching right allows the
operation; confirmation required only if *every* granting role's right
requires it. This is a deliberate simplification (not a full RBAC lattice
with deny-overrides) — documented, not accidental.
"""

from __future__ import annotations

from rights_w_main.right_manager.right_manager import Operation, RightDecision, RightManager

import models


def _choose_candidate(
    candidates: list[models.AccessRight], resource_id: str, field: str
) -> models.AccessRight | None:
    """Pick the most specific right that actually covers *field* — or None
    if none of the candidates cover it at all.

    Field coverage is mandatory, not a fallback: a right scoped to
    ``fields=["name"]`` must never be treated as authoritative for a
    different field like ``"vat"`` just because it's the only right on this
    resource — that was a real bug caught by the odoo-plugin test suite
    (a right for one field was silently granting access to unrelated
    fields, and even to ``delete`` — checked against the literal field
    ``"*"`` — for a right that only covered a named field). Every
    candidate that does cover the field is then ranked by specificity on
    two independent axes — (exact resource_id vs. "*" wildcard resource_id)
    and (exact field vs. "*" wildcard field) — exact beats wildcard on
    each axis, resource_id axis first. Same rule as odoo-plugin's
    get_right_manager_for() for the field axis; the resource_id axis is
    new (odoo-plugin never had an "any model" wildcard right).
    """
    field_covering = [r for r in candidates if r.applies_to_field(field)]
    if not field_covering:
        return None

    def _specificity(r: models.AccessRight) -> tuple[int, int]:
        exact_resource = 1 if r.resource_id == resource_id else 0
        exact_field = 1 if field in r.fields else 0
        return (exact_resource, exact_field)

    return max(field_covering, key=_specificity)


def _decision_for_role(role: str, resource_type: str, resource_id: str, operation: Operation, field: str) -> RightDecision | None:
    """Return this single role's RightDecision, or None if no right of this
    role covers the resource at all (as opposed to covering it but denying
    the operation, which IS a decision — allowed=False)."""
    candidates = models.rights_for_role_and_resource(role, resource_type, resource_id)
    chosen = _choose_candidate(candidates, resource_id, field)
    if chosen is None:
        return None
    return RightManager(chosen.to_right()).check(operation)


def check_right(
    *,
    roles: list[str],
    resource_type: str,
    resource_id: str,
    operation: Operation,
    field: str | None = None,
) -> RightDecision:
    """Deny-by-default. Never raises for "no matching right" — always
    returns a RightDecision(allowed=False, ...) in that case, unlike
    odoo-plugin's get_right_manager_for() (which raised NotFoundError and
    left callers to interpret that as "denied").
    """
    effective_field = field if field is not None else "*"

    # Keep (role, decision) paired explicitly — do not zip roles against a
    # filtered decisions list afterward, that misaligns indices as soon as
    # any role has no matching candidate at all.
    role_decisions: list[tuple[str, RightDecision]] = []
    for role in roles:
        decision = _decision_for_role(role, resource_type, resource_id, operation, effective_field)
        if decision is not None:
            role_decisions.append((role, decision))

    granting = [(role, d) for role, d in role_decisions if d.allowed]

    if not granting:
        return RightDecision(
            operation=operation,
            allowed=False,
            require_confirmation=False,
            reason=(
                f"No role of this identity ({', '.join(roles) or 'none'}) is granted "
                f"'{operation}' on {resource_type}:{resource_id}"
                + (f" field '{field}'" if field else "")
            ),
        )

    # Most permissive wins: allowed (already established), confirmation
    # required only if *every* granting role's decision requires it.
    require_confirmation = all(d.require_confirmation for _, d in granting)
    granting_roles = sorted({role for role, _ in granting})
    reason = (
        f"'{operation}' on {resource_type}:{resource_id} allowed via role(s) "
        f"{', '.join(granting_roles)}"
    )
    return RightDecision(
        operation=operation,
        allowed=True,
        require_confirmation=require_confirmation,
        reason=reason,
    )


def has_any_right_for(resource_type: str, resource_ids: tuple[str, ...]) -> bool:
    """True if at least one AccessRight exists for this resource_type and
    any of the given resource ids (typically ``(tool_name, "*")``).

    Public (re-exported via rights_plugin_api) — kept as a general-purpose
    "does a right exist for this exact resource" query. NOT what the
    hermes_tool bootstrap safety gate uses (see has_any_right_configured
    below) — a per-resource_id check here would mean narrowing an existing
    wildcard hermes_tool right down to one specific tool silently leaves
    every *other* tool ungated forever, which is exactly the bug caught
    2026-08-19 (see .agents/DECISIONS.md).
    """
    return any(r.resource_id in resource_ids for r in models.rights_for_resource_type(resource_type))


def has_any_right_configured(resource_type: str) -> bool:
    """True if at least one AccessRight exists for this resource_type at
    all, regardless of which resource_id it targets.

    Used by the pre_tool_call hook's hermes_tool safety gate: enabling
    rights-plugin with *zero* hermes_tool rights configured anywhere must
    never start denying every built-in tool by surprise (day-one
    bootstrap). But the moment an operator adds their first hermes_tool
    right — for any single tool, or "*" — the plugin is considered
    actively configured, and every other tool call must go through real
    deny-by-default evaluation instead of staying permanently ungated
    just because nobody happened to add a right for THAT specific tool
    yet. See .agents/DECISIONS.md, 2026-08-19, for the production bug
    this fixes: narrowing the "*" wildcard right down to a single tool
    (`odoo_sdk_read`) via the dashboard's new tool picker silently left
    every other tool (terminal, execute_code, cronjob's own dashboard
    listing, delegate_task, ...) callable, because has_any_right_for()
    only checked the one resource_id being called, never "is hermes_tool
    configured at all".
    """
    return bool(models.rights_for_resource_type(resource_type))
