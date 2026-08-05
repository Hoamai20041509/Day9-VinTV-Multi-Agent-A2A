"""Read-only access to Olist payment rows."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_PAYMENTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "olist_order_payments_dataset.csv"
)


class PaymentRepository:
    def __init__(self, csv_path: str | Path = DEFAULT_PAYMENTS_PATH) -> None:
        self.csv_path = Path(csv_path)
        self._payments: dict[str, list[dict[str, Any]]] | None = None

    def _load(self) -> None:
        if self._payments is not None:
            return
        indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
        with self.csv_path.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source):
                indexed[row["order_id"]].append(dict(row))
        for rows in indexed.values():
            rows.sort(key=lambda row: int(row["payment_sequential"]))
        self._payments = dict(indexed)

    def get_payments(self, order_id: str) -> list[dict[str, Any]]:
        self._load()
        assert self._payments is not None
        return [dict(row) for row in self._payments.get(order_id, [])]

    def get_payments_by_order_id(self, order_id: str) -> list[dict[str, Any]]:
        return self.get_payments(order_id)
