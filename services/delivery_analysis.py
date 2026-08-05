"""Deterministic delivery timestamp comparisons."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def analyze_delivery(order: dict[str, Any]) -> dict[str, Any]:
    delivered = parse_timestamp(order.get("order_delivered_customer_date"))
    estimated = parse_timestamp(order.get("order_estimated_delivery_date"))
    is_late = delivered is not None and estimated is not None and delivered > estimated
    return {
        "order_delivered_customer_date": order.get("order_delivered_customer_date"),
        "order_estimated_delivery_date": order.get("order_estimated_delivery_date"),
        "delivered_late": is_late,
        "delivered_within_estimate": (
            delivered is not None and estimated is not None and delivered <= estimated
        ),
    }
