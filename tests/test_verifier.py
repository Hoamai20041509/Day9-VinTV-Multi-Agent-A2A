"""Tests for output verification (schema, evidence existence, finance gates).

Uses the real EC_003 case (canceled order, single payment) so evidence
existence checks run against the actual CSVs.
"""
import copy

from agents.verifier_agent import VerifierAgent

ORDER_ID = "71303d7e93b399f5bcd537d124c0bcfa"  # EC_003, canceled, 1 payment, 1 item
VALID_OUTPUT = {
    "case_id": "EC_003",
    "assessment": {
        "primary_issue": "canceled_order_paid",
        "case_status": "action_required",
        "confidence": 0.95,
    },
    "affected_entities": {
        "order_ids": [ORDER_ID],
        "item_ids": [f"{ORDER_ID}:1"],
        "seller_ids": ["25e6ffe976bd75618accfe16cefcbd0d"],
        "payment_ids": [f"{ORDER_ID}:1"],
    },
    "root_cause_analysis": {
        "ranked_causes": [{"cause_code": "ORDER_CANCELED_AFTER_PAYMENT", "rank": 1}],
        "responsible_parties": [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}],
    },
    "evidence_ids": [
        f"order:{ORDER_ID}",
        f"item:{ORDER_ID}:1",
        f"payment:{ORDER_ID}:1",
        "policy:ORDER_CANCELED_AFTER_PAYMENT",
    ],
    "financial_resolution": {
        "currency": "BRL",
        "item_total_brl": 100.0,
        "freight_total_brl": 9.34,
        "payment_total_brl": 109.34,
        "recommended_refund_brl": 109.34,
    },
    "resolution_actions": ["issue_full_refund"],
}


def test_valid_output_passes() -> None:
    assert VerifierAgent().verify(copy.deepcopy(VALID_OUTPUT)) == []


def test_nonexistent_evidence_is_flagged() -> None:
    output = copy.deepcopy(VALID_OUTPUT)
    output["evidence_ids"].append("payment:" + "0" * 32 + ":1")
    violations = VerifierAgent().verify(output)
    assert any("not found in data" in v for v in violations)


def test_malformed_evidence_is_flagged() -> None:
    output = copy.deepcopy(VALID_OUTPUT)
    output["evidence_ids"].append("transaction:abc123")
    violations = VerifierAgent().verify(output)
    assert any("malformed" in v for v in violations)


def test_refund_mismatching_policy_is_flagged() -> None:
    output = copy.deepcopy(VALID_OUTPUT)
    output["financial_resolution"]["recommended_refund_brl"] = 9.34
    violations = VerifierAgent().verify(output)
    assert any("does not match policy" in v for v in violations)


def test_case_status_inconsistent_with_refund_is_flagged() -> None:
    output = copy.deepcopy(VALID_OUTPUT)
    output["assessment"]["case_status"] = "no_action"
    violations = VerifierAgent().verify(output)
    assert any("inconsistent with refund" in v for v in violations)


def test_entity_cap_violation_is_flagged() -> None:
    output = copy.deepcopy(VALID_OUTPUT)
    output["affected_entities"]["item_ids"] = [f"{ORDER_ID}:{n}" for n in range(1, 8)]
    violations = VerifierAgent().verify(output)
    assert any("exceeds 5" in v for v in violations)


def test_confidence_out_of_range_is_flagged() -> None:
    output = copy.deepcopy(VALID_OUTPUT)
    output["assessment"]["confidence"] = 1.2
    violations = VerifierAgent().verify(output)
    assert any("confidence" in v for v in violations)
