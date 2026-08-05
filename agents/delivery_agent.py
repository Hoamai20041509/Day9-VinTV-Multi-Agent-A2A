"""Delivery Agent - compares the actual delivery date against the estimate.

The seller-handoff milestone (carrier date vs shipping_limit_date) belongs to
the Order & Seller Agent; this agent only answers whether the customer
received the order later than Olist promised.
"""
from __future__ import annotations

from typing import Any

from services.delivery_analysis import delivered_late
from services.order_repository import OrderRepository


class DeliveryAgent:
    def __init__(self, order_repository: OrderRepository | None = None) -> None:
        self.order_repository = order_repository or OrderRepository()

    def analyze(self, order_id: str) -> dict[str, Any]:
        order = self.order_repository.get_order(order_id)
        if order is None:
            return {
                "order_found": False,
                "delivered_late": None,
                "order_delivered_customer_date": None,
                "order_estimated_delivery_date": None,
            }
        return {
            "order_found": True,
            "delivered_late": delivered_late(order),
            "order_delivered_customer_date": order.get("order_delivered_customer_date") or None,
            "order_estimated_delivery_date": order.get("order_estimated_delivery_date") or None,
        }
