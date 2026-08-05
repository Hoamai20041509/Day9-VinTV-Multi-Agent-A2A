"""Deterministic test doubles for coordinator contract tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from shared.a2a_messages import A2AMessage, AgentName, MessageType
from shared.schemas import (
    AffectedEntities,
    Assessment,
    CaseOutput,
    CaseStatus,
    DeliveryResult,
    FinancialResolution,
    OrderItemResult,
    OrderSellerResult,
    PaymentResult,
    PaymentRowResult,
    PolicyResult,
    PrimaryIssue,
    RankedCause,
    ResolutionAction,
    RootCauseAnalysis,
    RootCauseCode,
    VerificationResult,
)


RESPONSE_TYPES = {
    AgentName.ORDER_SELLER: MessageType.ORDER_SELLER_RESULT,
    AgentName.PAYMENT: MessageType.PAYMENT_RESULT,
    AgentName.DELIVERY: MessageType.DELIVERY_RESULT,
    AgentName.POLICY: MessageType.POLICY_RESULT,
    AgentName.VERIFIER: MessageType.VERIFIER_RESULT,
}


class FakeAgent:
    def __init__(
        self,
        name: AgentName,
        responder: Callable[[A2AMessage], Any],
    ) -> None:
        self.name = name
        self._responder = responder

    def handle(self, message: A2AMessage) -> A2AMessage:
        return A2AMessage.success_response(
            request=message,
            sender=self.name,
            message_type=RESPONSE_TYPES[self.name],
            payload=self._responder(message),
        )


class MemoryOutputWriter:
    def __init__(self) -> None:
        self.outputs: list[CaseOutput] = []

    def write(self, output: CaseOutput) -> None:
        self.outputs.append(output)


def make_case_output(case_id: str, order_id: str) -> CaseOutput:
    return CaseOutput(
        case_id=case_id,
        assessment=Assessment(
            primary_issue=PrimaryIssue.UNSUPPORTED_LATE_CLAIM,
            case_status=CaseStatus.NO_ACTION,
            confidence=0.95,
        ),
        affected_entities=AffectedEntities(
            order_ids=[order_id],
            item_ids=[f"{order_id}:1"],
            seller_ids=["seller-test"],
            payment_ids=[f"{order_id}:1"],
        ),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[
                RankedCause(cause_code=RootCauseCode.DELIVERY_WITHIN_ESTIMATE, rank=1)
            ],
            responsible_parties=[],
        ),
        evidence_ids=[
            f"order:{order_id}",
            f"item:{order_id}:1",
            f"payment:{order_id}:1",
            "seller:seller-test",
            "policy:DELIVERY_WITHIN_ESTIMATE",
        ],
        financial_resolution=FinancialResolution(
            currency="BRL",
            item_total_brl=10,
            freight_total_brl=2,
            payment_total_brl=12,
            recommended_refund_brl=0,
        ),
        resolution_actions=[ResolutionAction.REJECT_LATE_REFUND],
    )


def build_fake_agents() -> tuple[FakeAgent, FakeAgent, FakeAgent, FakeAgent, FakeAgent]:
    def order_result(message: A2AMessage) -> OrderSellerResult:
        order_id = message.payload["order_id"]
        return OrderSellerResult(
            case_id=message.case_id,
            order_id=order_id,
            order_exists=True,
            order_status="delivered",
            order_delivered_carrier_date="2018-01-02T10:00:00",
            order_delivered_customer_date="2018-01-05T10:00:00",
            order_estimated_delivery_date="2018-01-06T10:00:00",
            items=[
                OrderItemResult(
                    item_id=f"{order_id}:1",
                    order_item_id=1,
                    seller_id="seller-test",
                    price_brl=10,
                    freight_brl=2,
                    shipping_limit_date="2018-01-03T10:00:00",
                )
            ],
            seller_ids=["seller-test"],
            item_total_brl=10,
            freight_total_brl=2,
            evidence_ids=[
                f"order:{order_id}",
                f"item:{order_id}:1",
                "seller:seller-test",
            ],
        )

    def payment_result(message: A2AMessage) -> PaymentResult:
        order_id = message.payload["order_id"]
        return PaymentResult(
            case_id=message.case_id,
            order_id=order_id,
            payments=[
                PaymentRowResult(
                    payment_id=f"{order_id}:1",
                    payment_sequential=1,
                    payment_type="credit_card",
                    payment_installments=1,
                    payment_value_brl=12,
                )
            ],
            payment_total_brl=12,
            payment_row_count=1,
            is_split_payment=False,
            is_reconciled=True,
            reconciliation_difference_brl=0,
            evidence_ids=[f"payment:{order_id}:1"],
        )

    def delivery_result(message: A2AMessage) -> DeliveryResult:
        return DeliveryResult(
            case_id=message.case_id,
            order_id=message.payload["order_id"],
            delivered_customer_date="2018-01-05T10:00:00",
            estimated_delivery_date="2018-01-06T10:00:00",
            is_late=False,
            cause_candidate=RootCauseCode.DELIVERY_WITHIN_ESTIMATE,
            evidence_ids=[],
        )

    def policy_result(message: A2AMessage) -> PolicyResult:
        case = message.payload["case"]
        return PolicyResult(
            case_id=message.case_id,
            draft_output=make_case_output(message.case_id, case["customer_request"]["claimed_order_id"]),
        )

    def verification_result(message: A2AMessage) -> VerificationResult:
        return VerificationResult(
            case_id=message.case_id,
            is_valid=True,
            verified_output=message.payload["draft_output"],
        )

    return (
        FakeAgent(AgentName.ORDER_SELLER, order_result),
        FakeAgent(AgentName.PAYMENT, payment_result),
        FakeAgent(AgentName.DELIVERY, delivery_result),
        FakeAgent(AgentName.POLICY, policy_result),
        FakeAgent(AgentName.VERIFIER, verification_result),
    )
