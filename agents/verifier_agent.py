"""Verifier Agent - final gate before a case output is written to disk.

Checks three layers:
1. structure - schema shape, caps, enums, rounding (shared.schemas)
2. evidence  - every evidence ID must be well-formed AND exist in the CSVs
3. finance   - the refund must match what the primary issue prescribes
"""
from __future__ import annotations

from typing import Any

from services import payment_repository
from services.item_repository import ItemRepository
from services.order_repository import OrderRepository
from shared.evidence import ROOT_CAUSE_CODES, parse_evidence_id
from shared.schemas import validate_case_output


class VerifierAgent:
    def __init__(
        self,
        order_repository: OrderRepository | None = None,
        item_repository: ItemRepository | None = None,
    ) -> None:
        self.order_repository = order_repository or OrderRepository()
        self.item_repository = item_repository or ItemRepository()

    def _evidence_exists(self, kind: str, parts: tuple[str, ...]) -> bool:
        if kind == "order":
            return self.order_repository.exists(parts[0])
        if kind == "item":
            order_id, item_id = parts
            return any(
                str(item["order_item_id"]) == item_id
                for item in self.item_repository.get_items(order_id)
            )
        if kind == "payment":
            order_id, sequential = parts
            return any(
                str(row["payment_sequential"]) == sequential
                for row in payment_repository.get_payments(order_id)
            )
        if kind == "seller":
            return self.item_repository.get_seller(parts[0]) is not None
        if kind == "policy":
            return parts[0] in ROOT_CAUSE_CODES
        return False

    def verify(self, output: dict[str, Any]) -> list[str]:
        """Return all violations found (empty list means the output may ship)."""
        violations = validate_case_output(output)

        for evidence_id in output.get("evidence_ids", []):
            parsed = parse_evidence_id(evidence_id)
            if parsed is None:
                violations.append(f"malformed evidence ID {evidence_id!r}")
            elif not self._evidence_exists(*parsed):
                violations.append(f"evidence ID {evidence_id!r} not found in data")

        financial = output.get("financial_resolution", {})
        refund = financial.get("recommended_refund_brl")
        issue = output.get("assessment", {}).get("primary_issue")
        expected_refund = {
            "canceled_order_paid": financial.get("payment_total_brl"),
            "unavailable_order_paid": financial.get("payment_total_brl"),
            "late_delivery_seller": financial.get("freight_total_brl"),
            "late_delivery_logistics": financial.get("freight_total_brl"),
            "valid_split_payment": 0.0,
            "unsupported_late_claim": 0.0,
        }.get(issue)
        if expected_refund is not None and refund != expected_refund:
            violations.append(
                f"refund {refund} does not match policy for {issue} (expected {expected_refund})"
            )

        case_status = output.get("assessment", {}).get("case_status")
        if isinstance(refund, (int, float)):
            expected_status = "action_required" if refund > 0 else "no_action"
            if case_status != expected_status:
                violations.append(f"case_status {case_status!r} inconsistent with refund {refund}")

        return violations
