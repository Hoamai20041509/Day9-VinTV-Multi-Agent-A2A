"""EC_POLICY_V1 decision engine, evaluated in documented priority order."""

from __future__ import annotations

from typing import Any

from shared.constants import ISSUE_RULES


def select_issue(
    order_result: dict[str, Any],
    payment_result: dict[str, Any],
    delivery_result: dict[str, Any],
) -> str:
    status = order_result["order_status"]
    paid = payment_result["payment_total_brl"] > 0

    if status == "canceled" and paid:
        return "canceled_order_paid"
    if status == "unavailable" and paid:
        return "unavailable_order_paid"
    if delivery_result["delivered_late"] and order_result["late_handoff"]:
        return "late_delivery_seller"
    if delivery_result["delivered_late"] and not order_result["late_handoff"]:
        return "late_delivery_logistics"
    if payment_result["is_split_payment"] and payment_result["payment_matches"]:
        return "valid_split_payment"
    if delivery_result["delivered_within_estimate"] and payment_result["payment_matches"]:
        return "unsupported_late_claim"
    raise ValueError("Case does not match any EC_POLICY_V1 rule")


def apply_policy(
    order_result: dict[str, Any],
    payment_result: dict[str, Any],
    delivery_result: dict[str, Any],
) -> dict[str, Any]:
    issue = select_issue(order_result, payment_result, delivery_result)
    rule = ISSUE_RULES[issue]
    if issue in {"canceled_order_paid", "unavailable_order_paid"}:
        refund = payment_result["payment_total_brl"]
    elif issue in {"late_delivery_seller", "late_delivery_logistics"}:
        refund = order_result["freight_total_brl"]
    else:
        refund = 0.0

    parties = []
    if issue == "late_delivery_seller":
        parties = [
            {"party_type": "seller", "party_id": seller_id}
            for seller_id in order_result["late_seller_ids"]
        ]
    elif rule.get("party_type"):
        parties = [
            {
                "party_type": rule["party_type"],
                "party_id": rule["party_id"],
            }
        ]

    return {
        "primary_issue": issue,
        "case_status": "action_required" if refund > 0 else "no_action",
        "confidence": rule["confidence"],
        "cause_code": rule["cause"],
        "responsible_parties": parties,
        "recommended_refund_brl": round(refund, 2),
        "resolution_actions": [rule["action"]],
    }
