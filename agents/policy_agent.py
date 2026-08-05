"""EC_POLICY_V1 policy agent."""

from __future__ import annotations

from typing import Any

from shared.a2a_messages import A2AMessage, AgentName, MessageType
from shared.schemas import (
    AffectedEntities,
    Assessment,
    CaseOutput,
    DeliveryResult,
    FinancialResolution,
    OrderSellerResult,
    PaymentResult,
    PolicyResult,
    PrimaryIssue,
    ResolutionAction,
    RootCauseAnalysis,
    RootCauseCode,
)

MAX_IDS = 5
MAX_EVIDENCE = 10


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _payment_entity_ids(payment: PaymentResult) -> list[str]:
    return [row.payment_id for row in payment.payments[:MAX_IDS]]


def _item_ids(order: OrderSellerResult) -> list[str]:
    return [item.item_id for item in order.items[:MAX_IDS]]


def _policy_evidence(cause: RootCauseCode) -> str:
    return f"policy:{cause.value}"


class PolicyAgent:
    """Apply the ordered EC policy rules to domain-agent handoffs."""

    name = AgentName.POLICY

    def evaluate(self, payload: dict[str, Any]) -> PolicyResult:
        case = payload["case"]
        case_id = case["case_id"]
        order_id = case["customer_request"]["claimed_order_id"]
        order = OrderSellerResult.model_validate(payload["order_seller_result"])
        payment = PaymentResult.model_validate(payload["payment_result"])
        delivery = DeliveryResult.model_validate(payload["delivery_result"])

        issue, cause, refund, action, responsible = self._decide(order, payment, delivery)
        evidence = self._evidence(order, payment, delivery, cause)
        draft = CaseOutput(
            case_id=case_id,
            assessment=Assessment(
                primary_issue=issue,
                case_status="action_required" if refund > 0 else "no_action",
                confidence=0.92 if refund > 0 else 0.9,
            ),
            affected_entities=AffectedEntities(
                order_ids=[order_id] if order.order_exists else [],
                item_ids=_item_ids(order),
                seller_ids=order.seller_ids[:MAX_IDS],
                payment_ids=_payment_entity_ids(payment),
            ),
            root_cause_analysis=RootCauseAnalysis(
                ranked_causes=[{"cause_code": cause, "rank": 1}],
                responsible_parties=responsible,
            ),
            evidence_ids=evidence,
            financial_resolution=FinancialResolution(
                currency="BRL",
                item_total_brl=order.item_total_brl,
                freight_total_brl=order.freight_total_brl,
                payment_total_brl=payment.payment_total_brl,
                recommended_refund_brl=refund,
            ),
            resolution_actions=[action],
        )
        return PolicyResult(case_id=case_id, draft_output=draft)

    def _decide(
        self,
        order: OrderSellerResult,
        payment: PaymentResult,
        delivery: DeliveryResult,
    ) -> tuple[PrimaryIssue, RootCauseCode, float, ResolutionAction, list[dict[str, str]]]:
        status = (order.order_status or "").lower()
        if status == "canceled" and payment.payment_total_brl > 0:
            return (
                PrimaryIssue.CANCELED_ORDER_PAID,
                RootCauseCode.ORDER_CANCELED_AFTER_PAYMENT,
                payment.payment_total_brl,
                ResolutionAction.ISSUE_FULL_REFUND,
                [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}],
            )
        if status == "unavailable" and payment.payment_total_brl > 0:
            return (
                PrimaryIssue.UNAVAILABLE_ORDER_PAID,
                RootCauseCode.ORDER_UNAVAILABLE_AFTER_PAYMENT,
                payment.payment_total_brl,
                ResolutionAction.ISSUE_FULL_REFUND,
                [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}],
            )
        if delivery.is_late and order.late_handoffs:
            seller_ids = _unique([handoff.seller_id for handoff in order.late_handoffs])[:3]
            return (
                PrimaryIssue.LATE_DELIVERY_SELLER,
                RootCauseCode.SELLER_HANDOFF_AFTER_LIMIT,
                order.freight_total_brl,
                ResolutionAction.REFUND_FREIGHT,
                [{"party_type": "seller", "party_id": seller_id} for seller_id in seller_ids],
            )
        if delivery.is_late:
            return (
                PrimaryIssue.LATE_DELIVERY_LOGISTICS,
                RootCauseCode.CARRIER_DELIVERED_AFTER_ESTIMATE,
                order.freight_total_brl,
                ResolutionAction.REFUND_FREIGHT,
                [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}],
            )
        if payment.is_split_payment and payment.is_reconciled:
            return (
                PrimaryIssue.VALID_SPLIT_PAYMENT,
                RootCauseCode.MULTIPLE_PAYMENTS_RECONCILED,
                0.0,
                ResolutionAction.EXPLAIN_VALID_SPLIT_PAYMENT,
                [],
            )
        return (
            PrimaryIssue.UNSUPPORTED_LATE_CLAIM,
            RootCauseCode.DELIVERY_WITHIN_ESTIMATE,
            0.0,
            ResolutionAction.REJECT_LATE_REFUND,
            [],
        )

    def _evidence(
        self,
        order: OrderSellerResult,
        payment: PaymentResult,
        delivery: DeliveryResult,
        cause: RootCauseCode,
    ) -> list[str]:
        evidence = []
        evidence.extend(order.evidence_ids)
        evidence.extend(payment.evidence_ids)
        evidence.extend(delivery.evidence_ids)
        evidence.append(_policy_evidence(cause))
        return _unique(evidence)[:MAX_EVIDENCE]

    def evaluate_rule_5(self, payment_handoff: dict) -> dict | None:
        if not payment_handoff.get("valid_split_payment") and not (
            payment_handoff.get("is_split_payment") and payment_handoff.get("reconciled")
        ):
            return None
        return {
            "primary_issue": PrimaryIssue.VALID_SPLIT_PAYMENT.value,
            "case_status": "no_action",
            "confidence": 0.9,
            "responsible_parties": [],
            "ranked_causes": [
                {"cause_code": RootCauseCode.MULTIPLE_PAYMENTS_RECONCILED.value, "rank": 1}
            ],
            "evidence_ids": (
                payment_handoff.get("evidence_ids", [])
                + [_policy_evidence(RootCauseCode.MULTIPLE_PAYMENTS_RECONCILED)]
            )[:MAX_EVIDENCE],
            "recommended_refund_brl": 0.0,
            "resolution_actions": [ResolutionAction.EXPLAIN_VALID_SPLIT_PAYMENT.value],
        }

    def handle(self, message: A2AMessage) -> A2AMessage:
        if message.message_type != MessageType.POLICY_REQUEST:
            return A2AMessage.failure_response(
                request=message,
                sender=self.name,
                message_type=MessageType.POLICY_RESULT,
                code="unexpected_message",
                message=f"unsupported message type: {message.message_type}",
            )
        try:
            result = self.evaluate(message.payload)
        except Exception as exc:
            return A2AMessage.failure_response(
                request=message,
                sender=self.name,
                message_type=MessageType.POLICY_RESULT,
                code="policy_error",
                message=str(exc),
            )
        return A2AMessage.success_response(
            request=message,
            sender=self.name,
            message_type=MessageType.POLICY_RESULT,
            payload=result,
        )
