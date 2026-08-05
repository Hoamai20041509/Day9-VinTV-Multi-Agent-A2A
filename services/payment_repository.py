"""Data access for the Olist order_payments dataset."""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "olist_order_payments_dataset.csv"


@lru_cache(maxsize=1)
def _load_all() -> dict[str, list[dict]]:
    payments_by_order: dict[str, list[dict]] = {}
    with DATA_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            payments_by_order.setdefault(row["order_id"], []).append(
                {
                    "order_id": row["order_id"],
                    "payment_sequential": int(row["payment_sequential"]),
                    "payment_type": row["payment_type"],
                    "payment_installments": int(row["payment_installments"]),
                    "payment_value": float(row["payment_value"]),
                }
            )
    for rows in payments_by_order.values():
        rows.sort(key=lambda r: r["payment_sequential"])
    return payments_by_order


def get_payments(order_id: str) -> list[dict]:
    """All payment rows for order_id, sorted by payment_sequential. Empty list if none."""
    return list(_load_all().get(order_id, []))
