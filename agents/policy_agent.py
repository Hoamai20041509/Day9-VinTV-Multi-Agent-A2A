"""Policy Agent - applies EC_POLICY_V1 to the facts handed off by the
order/seller, payment and delivery agents."""
from __future__ import annotations

from typing import Any

from services.policy_engine import CaseFacts, PolicyDecision, decide


class PolicyAgent:
    def decide(
        self,
        order_seller_findings: dict[str, Any],
        payment_findings: dict[str, Any],
        delivery_findings: dict[str, Any],
    ) -> PolicyDecision:
        facts = CaseFacts(
            order_found=order_seller_findings["order_found"],
            order_status=order_seller_findings["order_status"],
            payment_total_brl=payment_findings["financial_resolution"]["payment_total_brl"],
            freight_total_brl=order_seller_findings["freight_total_brl"],
            payment_count=payment_findings["payment_count"],
            reconciled=payment_findings["reconciled"],
            delivered_late=delivery_findings["delivered_late"],
            late_seller_ids=order_seller_findings["late_seller_ids"],
        )
        return decide(facts)
