"""Evidence ID formats and root-cause vocabulary for EC_POLICY_V1.

Only IDs that can be built directly from the Olist CSVs are legal:
    order:<order_id>
    item:<order_id>:<order_item_id>
    payment:<order_id>:<payment_sequential>
    seller:<seller_id>
    policy:<root_cause_code>
"""
from __future__ import annotations

import re

ROOT_CAUSE_CODES = frozenset(
    {
        "SELLER_HANDOFF_AFTER_LIMIT",
        "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "ORDER_CANCELED_AFTER_PAYMENT",
        "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "MULTIPLE_PAYMENTS_RECONCILED",
        "DELIVERY_WITHIN_ESTIMATE",
    }
)

_HEX_ID = r"[0-9a-f]{32}"
_EVIDENCE_PATTERNS = {
    "order": re.compile(rf"^order:({_HEX_ID})$"),
    "item": re.compile(rf"^item:({_HEX_ID}):(\d+)$"),
    "payment": re.compile(rf"^payment:({_HEX_ID}):(\d+)$"),
    "seller": re.compile(rf"^seller:({_HEX_ID})$"),
    "policy": re.compile(r"^policy:([A-Z_]+)$"),
}


def parse_evidence_id(evidence_id: str) -> tuple[str, tuple[str, ...]] | None:
    """Return (kind, captured parts) for a well-formed evidence ID, else None."""
    for kind, pattern in _EVIDENCE_PATTERNS.items():
        match = pattern.match(evidence_id)
        if match:
            return kind, match.groups()
    return None


def order_evidence(order_id: str) -> str:
    return f"order:{order_id}"


def item_evidence(order_id: str, order_item_id: str | int) -> str:
    return f"item:{order_id}:{order_item_id}"


def payment_evidence(order_id: str, payment_sequential: str | int) -> str:
    return f"payment:{order_id}:{payment_sequential}"


def seller_evidence(seller_id: str) -> str:
    return f"seller:{seller_id}"


def policy_evidence(root_cause_code: str) -> str:
    return f"policy:{root_cause_code}"
