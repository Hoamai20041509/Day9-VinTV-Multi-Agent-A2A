"""Order and seller investigation agent."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.item_repository import ItemRepository
from services.order_repository import OrderRepository


MONEY_STEP = Decimal("0.01")
MAX_ENTITIES = 5


def _money(value: Decimal) -> float:
    return float(value.quantize(MONEY_STEP, rounding=ROUND_HALF_UP))


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid Olist timestamp: {value!r}") from exc


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class OrderSellerAgent:
    """Validate an order and produce item/seller handoff evidence."""

    def __init__(
        self,
        order_repository: OrderRepository | None = None,
        item_repository: ItemRepository | None = None,
        max_entities: int = MAX_ENTITIES,
    ) -> None:
        if max_entities < 1 or max_entities > MAX_ENTITIES:
            raise ValueError("max_entities must be between 1 and 5")
        self.order_repository = order_repository or OrderRepository()
        self.item_repository = item_repository or ItemRepository()
        self.max_entities = max_entities

    def analyze(self, order_id: str) -> dict[str, Any]:
        order = self.order_repository.get_order(order_id)
        if order is None:
            return {
                "order_found": False,
                "order_id": order_id,
                "order_status": None,
                "item_ids": [],
                "seller_ids": [],
                "item_total_brl": 0.0,
                "freight_total_brl": 0.0,
                "late_handoff": False,
                "late_item_ids": [],
                "late_seller_ids": [],
                "late_handoffs": [],
                "evidence_ids": [],
            }

        items = self.item_repository.get_items(order_id)
        item_total = sum(
            (Decimal(item.get("price") or "0") for item in items), Decimal("0")
        )
        freight_total = sum(
            (Decimal(item.get("freight_value") or "0") for item in items),
            Decimal("0"),
        )

        all_item_ids = [f'{order_id}:{item["order_item_id"]}' for item in items]
        all_seller_ids = _unique([item["seller_id"] for item in items])
        carrier_date = _timestamp(order.get("order_delivered_carrier_date"))

        late_rows = []
        if carrier_date is not None:
            late_rows = [
                item
                for item in items
                if (limit := _timestamp(item.get("shipping_limit_date"))) is not None
                and carrier_date > limit
            ]

        late_item_ids = [
            f'{order_id}:{item["order_item_id"]}' for item in late_rows
        ]
        late_seller_ids = _unique([item["seller_id"] for item in late_rows])
        late_handoffs = [
            {
                "item_id": f'{order_id}:{item["order_item_id"]}',
                "seller_id": item["seller_id"],
                "shipping_limit_date": item["shipping_limit_date"],
                "order_delivered_carrier_date": order[
                    "order_delivered_carrier_date"
                ],
            }
            for item in late_rows[: self.max_entities]
        ]

        evidence_ids = [f"order:{order_id}"]
        evidence_ids.extend(
            f"item:{item_id}" for item_id in all_item_ids[: self.max_entities]
        )
        # A seller evidence ID is valid only when that seller exists in sellers.csv.
        evidence_ids.extend(
            f"seller:{seller_id}"
            for seller_id in all_seller_ids[: self.max_entities]
            if self.item_repository.get_seller(seller_id) is not None
        )

        return {
            "order_found": True,
            "order_id": order_id,
            "order_status": order.get("order_status"),
            "item_ids": all_item_ids[: self.max_entities],
            "seller_ids": all_seller_ids[: self.max_entities],
            "item_total_brl": _money(item_total),
            "freight_total_brl": _money(freight_total),
            "late_handoff": bool(late_rows),
            "late_item_ids": late_item_ids[: self.max_entities],
            "late_seller_ids": late_seller_ids[: self.max_entities],
            "late_handoffs": late_handoffs,
            "evidence_ids": evidence_ids[:10],
        }

    def investigate(self, order_id: str) -> dict[str, Any]:
        return self.analyze(order_id)

    def run(self, order_id: str) -> dict[str, Any]:
        return self.analyze(order_id)
