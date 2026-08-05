
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PaymentRow:
    order_id: str
    payment_sequential: int
    payment_type: str
    payment_installments: int
    payment_value_brl: float

    @property
    def entity_id(self) -> str:
        return f"{self.order_id}:{self.payment_sequential}"

    @property
    def evidence_id(self) -> str:
        return f"payment:{self.entity_id}"


@dataclass(frozen=True)
class PaymentAnalysis:
    agent_name: str
    order_id: str
    payment_rows: list[PaymentRow]
    payment_total_brl: float
    payment_row_count: int
    payment_ids: list[str]
    evidence_ids: list[str]
    has_split_payment: bool
    reconciled_with_order_total: bool
    reconciliation_delta_brl: float
    valid_split_payment: bool
    expected_order_total_brl: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_handoff(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "order_id": self.order_id,
            "payment_rows": [
                {
                    "payment_sequential": row.payment_sequential,
                    "payment_type": row.payment_type,
                    "payment_installments": row.payment_installments,
                    "payment_value_brl": row.payment_value_brl,
                    "payment_id": row.entity_id,
                    "evidence_id": row.evidence_id,
                }
                for row in self.payment_rows
            ],
            "payment_total_brl": self.payment_total_brl,
            "payment_row_count": self.payment_row_count,
            "payment_ids": self.payment_ids,
            "evidence_ids": self.evidence_ids,
            "has_split_payment": self.has_split_payment,
            "reconciled_with_order_total": self.reconciled_with_order_total,
            "reconciliation_delta_brl": self.reconciliation_delta_brl,
            "valid_split_payment": self.valid_split_payment,
            "expected_order_total_brl": self.expected_order_total_brl,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PolicyDecision:
    primary_issue: str
    case_status: str
    confidence: float
    responsible_parties: list[dict[str, str]]
    ranked_causes: list[dict[str, int]]
    evidence_ids: list[str]
    recommended_refund_brl: float
    resolution_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_issue": self.primary_issue,
            "case_status": self.case_status,
            "confidence": self.confidence,
            "responsible_parties": self.responsible_parties,
            "ranked_causes": self.ranked_causes,
            "evidence_ids": self.evidence_ids,
            "recommended_refund_brl": self.recommended_refund_brl,
            "resolution_actions": self.resolution_actions,
        }
