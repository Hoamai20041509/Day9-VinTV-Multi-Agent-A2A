"""Coordinator Agent - receives a case, dispatches domain agents, applies the
policy decision and assembles the final schema-compliant output.

Handoff flow per case:
    coordinator -> order_seller_agent  (status, items, sellers, totals, late handoff)
    coordinator -> payment_agent       (payment rows, reconciliation)   [needs totals from order_seller]
    coordinator -> delivery_agent      (actual vs estimated delivery)
    coordinator -> policy_agent        (EC_POLICY_V1 decision on the combined facts)
    coordinator -> verifier_agent      (schema/evidence/finance gate before writing)

The LLM classifies the customer's message intent for the trace; every scored
field is produced by deterministic code so a generation glitch can never
corrupt an output file.
"""
from __future__ import annotations

from typing import Any

from agents.delivery_agent import DeliveryAgent
from agents.order_seller_agent import OrderSellerAgent
from agents.payment_agent import PaymentAgent
from agents.policy_agent import PolicyAgent
from agents.verifier_agent import VerifierAgent
from services.data_loader import get_item_repository, get_order_repository
from services.model_client import QwenModelClient
from services.policy_engine import PolicyDecision
from shared.constants import MAX_ENTITY_IDS, MAX_EVIDENCE_IDS, MODEL_NAME
from shared.evidence import policy_evidence

INTENT_LABELS = (
    "late_delivery",
    "canceled_refund",
    "unavailable_refund",
    "split_payment_check",
    "other",
)


class CoordinatorAgent:
    def __init__(self, use_llm: bool = True) -> None:
        order_repo = get_order_repository()
        item_repo = get_item_repository()
        self.order_seller_agent = OrderSellerAgent(order_repo, item_repo)
        self.payment_agent = PaymentAgent()
        self.delivery_agent = DeliveryAgent(order_repo)
        self.policy_agent = PolicyAgent()
        self.verifier_agent = VerifierAgent(order_repo, item_repo)
        self.use_llm = use_llm
        self._model_client = QwenModelClient() if use_llm else None

    def classify_intent(self, message: str) -> str:
        """LLM triage of the customer message; recorded in the trace only."""
        if self._model_client is None:
            return "llm_disabled"
        prompt = (
            "Phân loại yêu cầu của khách hàng vào đúng một nhãn trong danh sách: "
            f"{', '.join(INTENT_LABELS)}. Chỉ trả về nhãn.\n\nYêu cầu: {message}"
        )
        try:
            raw = self._model_client.generate(
                [{"role": "user", "content": prompt}], max_new_tokens=8
            ).lower()
        except Exception:
            return "unclassified"
        for label in INTENT_LABELS:
            if label in raw:
                return label
        return "other"

    def handle_case(self, case: dict[str, Any], trace: Any | None = None) -> dict[str, Any]:
        case_id = case["case_id"]
        order_id = case["customer_request"]["claimed_order_id"]

        def _log(event: str, **fields: Any) -> None:
            if trace is not None:
                trace.log(event, case_id=case_id, **fields)

        _log("case_start", order_id=order_id, policy_version=case.get("policy_version"))

        intent = self.classify_intent(case["customer_request"]["message"])
        _log("llm_intent", agent="coordinator", model=MODEL_NAME, intent=intent)

        _log("handoff", sender="coordinator", recipient="order_seller_agent", payload={"order_id": order_id})
        order_seller = self.order_seller_agent.analyze(order_id)
        _log(
            "finding",
            agent="order_seller_agent",
            payload={
                "order_status": order_seller["order_status"],
                "item_total_brl": order_seller["item_total_brl"],
                "freight_total_brl": order_seller["freight_total_brl"],
                "late_seller_ids": order_seller["late_seller_ids"],
            },
        )

        _log(
            "handoff",
            sender="order_seller_agent",
            recipient="payment_agent",
            payload={
                "order_id": order_id,
                "item_total_brl": order_seller["item_total_brl"],
                "freight_total_brl": order_seller["freight_total_brl"],
            },
        )
        payment = self.payment_agent.analyze(
            order_id, order_seller["item_total_brl"], order_seller["freight_total_brl"]
        )
        _log(
            "finding",
            agent="payment_agent",
            payload={
                "payment_total_brl": payment["financial_resolution"]["payment_total_brl"],
                "payment_count": payment["payment_count"],
                "is_split_payment": payment["is_split_payment"],
                "reconciled": payment["reconciled"],
            },
        )

        _log("handoff", sender="coordinator", recipient="delivery_agent", payload={"order_id": order_id})
        delivery = self.delivery_agent.analyze(order_id)
        _log("finding", agent="delivery_agent", payload=delivery)

        _log("handoff", sender="coordinator", recipient="policy_agent", payload={"facts": "combined findings"})
        decision = self.policy_agent.decide(order_seller, payment, delivery)
        _log(
            "finding",
            agent="policy_agent",
            payload={
                "primary_issue": decision.primary_issue,
                "root_cause_code": decision.root_cause_code,
                "recommended_refund_brl": decision.recommended_refund_brl,
                "action": decision.action,
            },
        )

        output = self._assemble_output(case_id, order_id, order_seller, payment, decision)

        violations = self.verifier_agent.verify(output)
        _log("verify", agent="verifier_agent", violations=violations)
        if violations:
            raise ValueError(f"{case_id}: verifier rejected output: {violations}")

        _log(
            "case_complete",
            primary_issue=decision.primary_issue,
            recommended_refund_brl=decision.recommended_refund_brl,
        )
        return output

    def _assemble_output(
        self,
        case_id: str,
        order_id: str,
        order_seller: dict[str, Any],
        payment: dict[str, Any],
        decision: PolicyDecision,
    ) -> dict[str, Any]:
        # Bare "<order_id>:<n>" forms for affected_entities; prefixed forms for evidence.
        payment_entity_ids = [
            pid.removeprefix("payment:") for pid in payment["payment_ids"][:MAX_ENTITY_IDS]
        ]

        # Evidence budget (max 10): order + up to 3 items + up to 3 payments
        # + responsible sellers (seller-fault cases only) + policy code.
        if decision.primary_issue == "late_delivery_seller":
            preferred_items = list(
                dict.fromkeys(order_seller["late_item_ids"] + order_seller["item_ids"])
            )
            seller_ids_for_evidence = order_seller["late_seller_ids"][:2]
        else:
            preferred_items = order_seller["item_ids"]
            seller_ids_for_evidence = []

        evidence_ids = [f"order:{order_id}"]
        evidence_ids += [f"item:{item_id}" for item_id in preferred_items[:3]]
        evidence_ids += payment["payment_ids"][:3]
        evidence_ids += [f"seller:{seller_id}" for seller_id in seller_ids_for_evidence]
        evidence_ids.append(policy_evidence(decision.root_cause_code))
        evidence_ids = list(dict.fromkeys(evidence_ids))[:MAX_EVIDENCE_IDS]

        financial = payment["financial_resolution"]
        return {
            "case_id": case_id,
            "assessment": {
                "primary_issue": decision.primary_issue,
                "case_status": decision.case_status,
                "confidence": decision.confidence,
            },
            "affected_entities": {
                "order_ids": [order_id],
                "item_ids": order_seller["item_ids"][:MAX_ENTITY_IDS],
                "seller_ids": order_seller["seller_ids"][:MAX_ENTITY_IDS],
                "payment_ids": payment_entity_ids,
            },
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": decision.root_cause_code, "rank": 1}],
                "responsible_parties": decision.responsible_parties,
            },
            "evidence_ids": evidence_ids,
            "financial_resolution": {
                "currency": "BRL",
                "item_total_brl": financial["item_total_brl"],
                "freight_total_brl": financial["freight_total_brl"],
                "payment_total_brl": financial["payment_total_brl"],
                "recommended_refund_brl": decision.recommended_refund_brl,
            },
            "resolution_actions": [decision.action],
        }
