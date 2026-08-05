"""Read-only access to the Olist orders data."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


DEFAULT_ORDERS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "olist_orders_dataset.csv"
)


class OrderRepository:
    """Index orders by ID while preserving the source CSV values."""

    def __init__(self, csv_path: str | Path = DEFAULT_ORDERS_PATH) -> None:
        self.csv_path = Path(csv_path)
        self._orders: dict[str, dict[str, Any]] | None = None

    def _load(self) -> None:
        if self._orders is not None:
            return

        with self.csv_path.open(encoding="utf-8", newline="") as source:
            self._orders = {
                row["order_id"]: dict(row) for row in csv.DictReader(source)
            }

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        """Return a copy of an order, or ``None`` when it does not exist."""
        self._load()
        assert self._orders is not None
        order = self._orders.get(order_id)
        return dict(order) if order is not None else None

    def get_by_id(self, order_id: str) -> dict[str, Any] | None:
        return self.get_order(order_id)

    def exists(self, order_id: str) -> bool:
        return self.get_order(order_id) is not None
