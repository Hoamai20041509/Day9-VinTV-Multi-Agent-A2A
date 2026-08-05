"""Coordinator for the deterministic multi-agent investigation pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from agents.delivery_agent import DeliveryAgent
from agents.order_seller_agent import OrderSellerAgent
from agents.payment_agent import PaymentAgent
from agents.policy_agent import PolicyAgent
from agents.verifier_agent import VerifierAgent
from services.data_loader import load_cases
from services.output_writer import write_output
from shared.constants import CURRENCY
from shared.evidence import build_evidence_ids
from shared.schemas import CaseInput, CaseOutput
from shared.trace import TraceLogger


ROOT = Path(__file__).resolve().parents[1]


class CoordinatorAgent:
    def __init__(
        self,
        order_seller_agent: OrderSellerAgent | None = None,
        payment_agent: PaymentAgent | None = None,
        delivery_agent: DeliveryAgent | None = None,
        policy_agent: PolicyAgent | None = None,
        verifier_agent: VerifierAgent | None = None,
        trace_logger: TraceLogger | None = None,
    ) -> None:
        self.order_seller_agent = order_seller_agent or OrderSellerAgent()
        self.payment_agent = payment_agent or PaymentAgent()
        self.delivery_agent = delivery_agent or DeliveryAgent()
        self.policy_agent = policy_agent or PolicyAgent()
        self.verifier_agent = verifier_agent or VerifierAgent()
        self.trace = trace_logger

    def _trace(self, case_id: str, agent: str, payload: dict[str, Any]) -> None:
        if self.trace:
            self.trace.record(case_id, agent, "handoff", payload)

    def process(self, case: CaseInput) -> CaseOutput:
        case_id = case["case_id"]
        order_id = case["customer_request"]["claimed_order_id"]

        order_result = self.order_seller_agent.analyze(order_id)
        self._trace(case_id, "order_seller_agent", order_result)
        if not order_result["order_found"]:
            raise ValueError(f"Order not found for {case_id}: {order_id}")

        expected_total = round(
            order_result["item_total_brl"] + order_result["freight_total_brl"], 2
        )
        payment_result = self.payment_agent.analyze(order_id, expected_total)
        self._trace(case_id, "payment_agent", payment_result)

        delivery_result = self.delivery_agent.analyze(order_result["order"])
        self._trace(case_id, "delivery_agent", delivery_result)

        policy_result = self.policy_agent.analyze(
            order_result, payment_result, delivery_result
        )
        self._trace(case_id, "policy_agent", policy_result)

        issue = policy_result["primary_issue"]
        cause_code = policy_result["cause_code"]
        if issue in {"canceled_order_paid", "unavailable_order_paid"}:
            evidence_item_ids = order_result["item_ids"]
            evidence_seller_ids = []
        elif issue == "late_delivery_seller":
            evidence_item_ids = order_result["late_item_ids"]
            evidence_seller_ids = order_result["late_seller_ids"]
        else:
            evidence_item_ids = order_result["item_ids"]
            evidence_seller_ids = []
        evidence_ids = build_evidence_ids(
            order_id,
            evidence_item_ids,
            payment_result["payment_ids"],
            evidence_seller_ids,
            cause_code,
        )
        result: CaseOutput = {
            "case_id": case_id,
            "assessment": {
                "primary_issue": issue,
                "case_status": policy_result["case_status"],
                "confidence": policy_result["confidence"],
            },
            "affected_entities": {
                "order_ids": [order_id],
                "item_ids": order_result["item_ids"],
                "seller_ids": order_result["seller_ids"],
                "payment_ids": payment_result["payment_ids"],
            },
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": cause_code, "rank": 1}],
                "responsible_parties": policy_result["responsible_parties"][:3],
            },
            "evidence_ids": evidence_ids,
            "financial_resolution": {
                "currency": CURRENCY,
                "item_total_brl": order_result["item_total_brl"],
                "freight_total_brl": order_result["freight_total_brl"],
                "payment_total_brl": payment_result["payment_total_brl"],
                "recommended_refund_brl": policy_result[
                    "recommended_refund_brl"
                ],
            },
            "resolution_actions": policy_result["resolution_actions"],
        }
        verified = self.verifier_agent.verify(result)
        self._trace(case_id, "verifier_agent", {"valid": True})
        return verified

    def run_all(self, input_dir: str | Path, output_dir: str | Path) -> list[CaseOutput]:
        results = []
        for case in load_cases(input_dir):
            result = self.process(case)
            write_output(result, output_dir)
            results.append(result)
        return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve all Olist dispute cases")
    parser.add_argument("--input-dir", default=str(ROOT / "input"))
    parser.add_argument("--output-dir", default=str(ROOT / "output"))
    parser.add_argument("--trace", default=str(ROOT / "logging" / "trace.jsonl"))
    args = parser.parse_args()
    coordinator = CoordinatorAgent(trace_logger=TraceLogger(args.trace))
    results = coordinator.run_all(args.input_dir, args.output_dir)
    print(f"Processed {len(results)} cases into {args.output_dir}")


if __name__ == "__main__":
    main()
