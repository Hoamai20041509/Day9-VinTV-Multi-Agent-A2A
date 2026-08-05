"""Final schema and evidence verifier."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.item_repository import ItemRepository
from services.order_repository import OrderRepository
from services import payment_repository
from shared.a2a_messages import A2AMessage, AgentName, MessageType
from shared.schemas import CaseOutput, VerificationResult


class VerifierAgent:
    """Reject malformed outputs and evidence that cannot be checked in CSV data."""

    name = AgentName.VERIFIER

    def __init__(
        self,
        data_dir: str | Path | None = None,
        order_repository: OrderRepository | None = None,
        item_repository: ItemRepository | None = None,
    ) -> None:
        if data_dir is not None and (order_repository is not None or item_repository is not None):
            raise ValueError("data_dir cannot be combined with explicit repositories")
        if data_dir is not None:
            data_path = Path(data_dir)
            order_repository = OrderRepository(data_path / "olist_orders_dataset.csv")
            item_repository = ItemRepository(
                data_path / "olist_order_items_dataset.csv",
                data_path / "olist_sellers_dataset.csv",
            )
            self._payments_path = data_path / "olist_order_payments_dataset.csv"
        else:
            self._payments_path = None
        self._payments_by_order: dict[str, list[dict]] | None = None
        self.order_repository = order_repository or OrderRepository()
        self.item_repository = item_repository or ItemRepository()

    def verify(self, case_id: str, draft_output: Any) -> VerificationResult:
        errors: list[str] = []
        try:
            output = CaseOutput.model_validate(draft_output)
        except Exception as exc:
            return VerificationResult(case_id=case_id, is_valid=False, errors=[str(exc)])

        if output.case_id != case_id:
            errors.append("output case_id mismatch")
        for evidence_id in output.evidence_ids:
            if not self._evidence_exists(evidence_id):
                errors.append(f"unknown evidence: {evidence_id}")

        if errors:
            return VerificationResult(case_id=case_id, is_valid=False, errors=errors)
        return VerificationResult(case_id=case_id, is_valid=True, verified_output=output)

    def _evidence_exists(self, evidence_id: str) -> bool:
        kind, rest = evidence_id.split(":", 1)
        if kind == "policy":
            return True
        if kind == "order":
            return self.order_repository.get_order(rest) is not None
        if kind == "seller":
            return self.item_repository.get_seller(rest) is not None
        if kind == "item":
            order_id, item_seq = rest.rsplit(":", 1)
            return any(str(item["order_item_id"]) == item_seq for item in self.item_repository.get_items(order_id))
        if kind == "payment":
            order_id, payment_seq = rest.rsplit(":", 1)
            return any(str(row["payment_sequential"]) == payment_seq for row in self._payment_rows(order_id))
        return False

    def _payment_rows(self, order_id: str) -> list[dict]:
        if self._payments_path is None:
            return payment_repository.get_payments(order_id)
        import csv

        if self._payments_by_order is None:
            payments_by_order: dict[str, list[dict]] = {}
            with self._payments_path.open(newline="", encoding="utf-8") as source:
                for row in csv.DictReader(source):
                    payments_by_order.setdefault(row["order_id"], []).append(row)
            self._payments_by_order = payments_by_order
        return list(self._payments_by_order.get(order_id, []))

    def handle(self, message: A2AMessage) -> A2AMessage:
        if message.message_type != MessageType.VERIFIER_REQUEST:
            return A2AMessage.failure_response(
                request=message,
                sender=self.name,
                message_type=MessageType.VERIFIER_RESULT,
                code="unexpected_message",
                message=f"unsupported message type: {message.message_type}",
            )
        result = self.verify(message.case_id, message.payload.get("draft_output"))
        return A2AMessage.success_response(
            request=message,
            sender=self.name,
            message_type=MessageType.VERIFIER_RESULT,
            payload=result,
        )
