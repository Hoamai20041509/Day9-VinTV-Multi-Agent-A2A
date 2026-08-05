"""Structural validation for the case output schema."""
from __future__ import annotations

from typing import Any

from shared.constants import (
    MAX_ENTITY_IDS,
    MAX_EVIDENCE_IDS,
    MAX_RANKED_CAUSES,
    MAX_RESOLUTION_ACTIONS,
    MAX_RESPONSIBLE_PARTIES,
)

PRIMARY_ISSUES = frozenset(
    {
        "canceled_order_paid",
        "unavailable_order_paid",
        "late_delivery_seller",
        "late_delivery_logistics",
        "valid_split_payment",
        "unsupported_late_claim",
    }
)
CASE_STATUSES = frozenset({"action_required", "no_action"})
RESOLUTION_ACTIONS = frozenset(
    {
        "issue_full_refund",
        "refund_freight",
        "explain_valid_split_payment",
        "reject_late_refund",
    }
)
ENTITY_SETS = ("order_ids", "item_ids", "seller_ids", "payment_ids")


def validate_case_output(output: dict[str, Any]) -> list[str]:
    """Return a list of structural violations (empty when the output is valid)."""
    violations: list[str] = []

    def _check(condition: bool, message: str) -> None:
        if not condition:
            violations.append(message)

    _check(isinstance(output.get("case_id"), str) and bool(output.get("case_id")), "case_id missing")

    assessment = output.get("assessment", {})
    _check(assessment.get("primary_issue") in PRIMARY_ISSUES, "invalid primary_issue")
    _check(assessment.get("case_status") in CASE_STATUSES, "invalid case_status")
    confidence = assessment.get("confidence")
    _check(
        isinstance(confidence, (int, float)) and 0.0 <= confidence <= 1.0,
        "confidence outside [0, 1]",
    )

    entities = output.get("affected_entities", {})
    for key in ENTITY_SETS:
        ids = entities.get(key)
        _check(isinstance(ids, list), f"{key} must be a list")
        if isinstance(ids, list):
            _check(len(ids) <= MAX_ENTITY_IDS, f"{key} exceeds {MAX_ENTITY_IDS} IDs")

    rca = output.get("root_cause_analysis", {})
    causes = rca.get("ranked_causes", [])
    _check(isinstance(causes, list) and 1 <= len(causes) <= MAX_RANKED_CAUSES, "ranked_causes count invalid")
    parties = rca.get("responsible_parties", [])
    _check(isinstance(parties, list) and len(parties) <= MAX_RESPONSIBLE_PARTIES, "responsible_parties count invalid")

    evidence = output.get("evidence_ids", [])
    _check(isinstance(evidence, list) and 1 <= len(evidence) <= MAX_EVIDENCE_IDS, "evidence_ids count invalid")

    financial = output.get("financial_resolution", {})
    _check(financial.get("currency") == "BRL", "currency must be BRL")
    for key in ("item_total_brl", "freight_total_brl", "payment_total_brl", "recommended_refund_brl"):
        value = financial.get(key)
        _check(isinstance(value, (int, float)), f"{key} missing")
        if isinstance(value, (int, float)):
            _check(round(value, 2) == value, f"{key} not rounded to 2 decimals")
            _check(value >= 0, f"{key} negative")

    actions = output.get("resolution_actions", [])
    _check(
        isinstance(actions, list) and 1 <= len(actions) <= MAX_RESOLUTION_ACTIONS,
        "resolution_actions count invalid",
    )
    if isinstance(actions, list):
        for action in actions:
            _check(action in RESOLUTION_ACTIONS, f"unknown action {action!r}")

    return violations
