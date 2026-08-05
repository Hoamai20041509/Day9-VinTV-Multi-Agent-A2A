from decimal import Decimal

from services.payment_repository import PaymentRepository, money_to_decimal, money_to_float
from shared.constants import MAX_ENTITY_IDS, MONEY_TOLERANCE_BRL
from shared.schemas import PaymentAnalysis


AGENT_NAME = "payment_agent"


class PaymentAgent:
    """Owns rule-5 payment facts; does not infer refunds or transaction IDs."""

    def __init__(self, repository: PaymentRepository | None = None) -> None:
        self.repository = repository or PaymentRepository()

    def analyze(
        self,
        order_id: str,
        item_total_brl: float | int | str | Decimal | None = None,
        freight_total_brl: float | int | str | Decimal | None = None,
    ) -> PaymentAnalysis:
        rows = self.repository.get_by_order_id(order_id)
        payment_total = sum((money_to_decimal(row.payment_value_brl) for row in rows), Decimal("0.00"))
        payment_total = money_to_decimal(payment_total)

        expected_total: Decimal | None = None
        reconciled = False
        delta = Decimal("0.00")
        notes: list[str] = []

        if item_total_brl is None or freight_total_brl is None:
            notes.append("item_total_brl/freight_total_brl not provided; reconciliation deferred")
        else:
            expected_total = money_to_decimal(item_total_brl) + money_to_decimal(freight_total_brl)
            expected_total = money_to_decimal(expected_total)
            delta = abs(payment_total - expected_total)
            reconciled = delta <= MONEY_TOLERANCE_BRL

        has_split_payment = len(rows) >= 2
        valid_split_payment = has_split_payment and reconciled

        return PaymentAnalysis(
            agent_name=AGENT_NAME,
            order_id=order_id,
            payment_rows=rows,
            payment_total_brl=money_to_float(payment_total),
            payment_row_count=len(rows),
            payment_ids=[row.entity_id for row in rows[:MAX_ENTITY_IDS]],
            evidence_ids=[row.evidence_id for row in rows[:MAX_ENTITY_IDS]],
            has_split_payment=has_split_payment,
            reconciled_with_order_total=reconciled,
            reconciliation_delta_brl=money_to_float(delta),
            valid_split_payment=valid_split_payment,
            expected_order_total_brl=money_to_float(expected_total) if expected_total is not None else None,
            notes=notes,
        )


def analyze_payment(
    order_id: str,
    item_total_brl: float | int | str | Decimal | None = None,
    freight_total_brl: float | int | str | Decimal | None = None,
) -> dict:
    return PaymentAgent().analyze(order_id, item_total_brl, freight_total_brl).to_handoff()
