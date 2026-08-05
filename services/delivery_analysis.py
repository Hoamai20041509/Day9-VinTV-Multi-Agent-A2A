"""Deterministic delivery-timeline comparisons for EC_POLICY_V1.

Timestamps are compared as parsed values straight from the CSV; the brief
says no timezone conversion is required.
"""
from __future__ import annotations

from datetime import datetime


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def delivered_late(order: dict) -> bool | None:
    """True when the customer delivery happened after the estimated date.

    Returns None when either timestamp is missing (undelivered orders), so the
    policy engine can distinguish "on time" from "cannot evaluate".
    """
    delivered = parse_timestamp(order.get("order_delivered_customer_date"))
    estimated = parse_timestamp(order.get("order_estimated_delivery_date"))
    if delivered is None or estimated is None:
        return None
    return delivered > estimated
