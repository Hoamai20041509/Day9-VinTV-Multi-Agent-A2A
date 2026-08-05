"""Payment reconciliation agent."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from services.payment_repository import PaymentRepository
from shared.constants import MAX_ENTITY_IDS, PAYMENT_TOLERANCE_BRL


class PaymentAgent:
    def __init__(self, repository: PaymentRepository | None = None) -> None:
        self.repository = repository or PaymentRepository()

    def analyze(self, order_id: str, expected_total_brl: float) -> dict[str, Any]:
        rows = self.repository.get_payments(order_id)
        total = sum(
            (Decimal(row.get("payment_value") or "0") for row in rows),
            Decimal("0"),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        expected = Decimal(str(expected_total_brl)).quantize(Decimal("0.01"))
        difference = abs(total - expected)
        payment_ids = [
            f'{order_id}:{row["payment_sequential"]}' for row in rows
        ][:MAX_ENTITY_IDS]
        return {
            "payment_ids": payment_ids,
            "payment_count": len(rows),
            "payment_total_brl": float(total),
            "expected_total_brl": float(expected),
            "difference_brl": float(difference),
            "payment_matches": difference <= Decimal(str(PAYMENT_TOLERANCE_BRL)),
            "is_split_payment": len(rows) >= 2,
        }

    def run(self, order_id: str, expected_total_brl: float) -> dict[str, Any]:
        return self.analyze(order_id, expected_total_brl)
