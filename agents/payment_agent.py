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

from services import payment_repository

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

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._pipeline = None

    def _load_model(self):
        from transformers import pipeline

        self._pipeline = pipeline("text-generation", model=self.model_name, tokenizer=self.model_name)

    def analyze(self, order_id: str, item_total_brl: float, freight_total_brl: float) -> dict:
        result = compute_reconciliation(order_id, item_total_brl, freight_total_brl)
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
