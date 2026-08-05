"""Payment Agent (TV3) - reconciles order_payments against item + freight totals.

Handoff contract:
- Receives `item_total_brl` / `freight_total_brl` from the Order & Seller Agent
  (already 0.0/0.0 when the order has no item rows) - this agent never reads
  order_items.csv itself.
- Never infers a refund ledger or transaction ID; Olist has none.

All money math is deterministic Python (`compute_reconciliation`), not model
output, so the model can never corrupt the scored financial_resolution
numbers. The LLM (Qwen2.5-1.5B-Instruct) is only used for an optional
natural-language note for the trace log.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services import payment_repository
from shared.a2a_messages import A2AMessage, AgentName, MessageType
from shared.schemas import PaymentResult

MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"
RECONCILIATION_TOLERANCE_BRL = 0.10
MAX_PAYMENT_IDS = 5


@dataclass
class PaymentReconciliation:
    payment_total_brl: float
    payment_count: int
    is_split_payment: bool
    reconciled: bool
    payment_ids: list[str]


def compute_reconciliation(
    order_id: str, item_total_brl: float, freight_total_brl: float
) -> PaymentReconciliation:
    """Sums ALL payment rows (the 5-ID cap below only trims the evidence list,
    never the total), then checks it against item_total + freight_total
    within the 0.10 BRL tolerance from EC_POLICY_V1."""
    rows = payment_repository.get_payments(order_id)
    payment_total_brl = round(sum(r["payment_value"] for r in rows), 2)
    expected_total = round(item_total_brl + freight_total_brl, 2)
    diff = round(abs(payment_total_brl - expected_total), 2)
    payment_ids = [f"payment:{order_id}:{r['payment_sequential']}" for r in rows[:MAX_PAYMENT_IDS]]
    return PaymentReconciliation(
        payment_total_brl=payment_total_brl,
        payment_count=len(rows),
        is_split_payment=len(rows) >= 2,
        reconciled=diff <= RECONCILIATION_TOLERANCE_BRL,
        payment_ids=payment_ids,
    )


class PaymentAgent:
    """Thin LLM wrapper around `compute_reconciliation`. The model narrates the
    already-computed numbers; it never recomputes them."""

    name = AgentName.PAYMENT

    def __init__(self, data_dir: str | Path | None = None, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._pipeline = None
        self._payments_path = (
            Path(data_dir) / "olist_order_payments_dataset.csv"
            if data_dir is not None
            else None
        )
        self._payments_by_order: dict[str, list[dict]] | None = None

    def _rows(self, order_id: str) -> list[dict]:
        if self._payments_path is None:
            return payment_repository.get_payments(order_id)
        import csv

        if self._payments_by_order is None:
            payments_by_order: dict[str, list[dict]] = {}
            with self._payments_path.open(newline="", encoding="utf-8") as source:
                for row in csv.DictReader(source):
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
                rows.sort(key=lambda row: row["payment_sequential"])
            self._payments_by_order = payments_by_order
        return list(self._payments_by_order.get(order_id, []))

    def _compute(
        self, order_id: str, item_total_brl: float, freight_total_brl: float
    ) -> PaymentReconciliation:
        rows = self._rows(order_id)
        payment_total_brl = round(sum(r["payment_value"] for r in rows), 2)
        expected_total = round(item_total_brl + freight_total_brl, 2)
        diff = round(abs(payment_total_brl - expected_total), 2)
        payment_ids = [f"payment:{order_id}:{r['payment_sequential']}" for r in rows[:MAX_PAYMENT_IDS]]
        return PaymentReconciliation(
            payment_total_brl=payment_total_brl,
            payment_count=len(rows),
            is_split_payment=len(rows) >= 2,
            reconciled=diff <= RECONCILIATION_TOLERANCE_BRL,
            payment_ids=payment_ids,
        )

    def _load_model(self):
        from transformers import pipeline

        self._pipeline = pipeline("text-generation", model=self.model_name, tokenizer=self.model_name)

    def analyze(self, order_id: str, item_total_brl: float, freight_total_brl: float) -> dict:
        result = self._compute(order_id, item_total_brl, freight_total_brl)
        return {
            "financial_resolution": {
                "item_total_brl": round(item_total_brl, 2),
                "freight_total_brl": round(freight_total_brl, 2),
                "payment_total_brl": result.payment_total_brl,
            },
            "payment_ids": result.payment_ids,
            "is_split_payment": result.is_split_payment,
            "reconciled": result.reconciled,
        }

    def _result(
        self, case_id: str, order_id: str, item_total_brl: float, freight_total_brl: float
    ) -> PaymentResult:
        rows = self._rows(order_id)
        result = self._compute(order_id, item_total_brl, freight_total_brl)
        expected_total = round(item_total_brl + freight_total_brl, 2)
        return PaymentResult(
            case_id=case_id,
            order_id=order_id,
            payments=[
                {
                    "payment_id": f"{order_id}:{row['payment_sequential']}",
                    "payment_sequential": row["payment_sequential"],
                    "payment_type": row["payment_type"],
                    "payment_installments": row["payment_installments"],
                    "payment_value_brl": row["payment_value"],
                }
                for row in rows
            ],
            payment_total_brl=result.payment_total_brl,
            payment_row_count=len(rows),
            is_split_payment=result.is_split_payment,
            is_reconciled=result.reconciled,
            reconciliation_difference_brl=round(abs(result.payment_total_brl - expected_total), 2),
            evidence_ids=result.payment_ids,
        )

    def handle(self, message: A2AMessage) -> A2AMessage:
        if message.message_type != MessageType.PAYMENT_REQUEST:
            return A2AMessage.failure_response(
                request=message,
                sender=self.name,
                message_type=MessageType.PAYMENT_RESULT,
                code="unexpected_message",
                message=f"unsupported message type: {message.message_type}",
            )
        try:
            result = self._result(
                message.payload["case_id"],
                message.payload["order_id"],
                float(message.payload["item_total_brl"]),
                float(message.payload["freight_total_brl"]),
            )
        except Exception as exc:
            return A2AMessage.failure_response(
                request=message,
                sender=self.name,
                message_type=MessageType.PAYMENT_RESULT,
                code="payment_error",
                message=str(exc),
            )
        return A2AMessage.success_response(
            request=message,
            sender=self.name,
            message_type=MessageType.PAYMENT_RESULT,
            payload=result,
        )

    def explain(self, order_id: str, item_total_brl: float, freight_total_brl: float) -> str:
        """Optional one-line Vietnamese note for trace.jsonl - not used for scoring."""
        result = compute_reconciliation(order_id, item_total_brl, freight_total_brl)
        if self._pipeline is None:
            self._load_model()
        expected_total = round(item_total_brl + freight_total_brl, 2)
        prompt = (
            f"Đơn hàng {order_id}: tổng thanh toán {result.payment_total_brl} BRL, "
            f"tổng item+freight {expected_total} BRL, {result.payment_count} dòng thanh toán. "
            "Viết một câu tiếng Việt ngắn gọn nêu payment có đối soát khớp hay không."
        )
        messages = [{"role": "user", "content": prompt}]
        output = self._pipeline(messages, max_new_tokens=60, do_sample=False)
        return output[0]["generated_text"][-1]["content"].strip()
