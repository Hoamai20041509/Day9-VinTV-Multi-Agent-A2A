import json
from collections import Counter
from pathlib import Path

import pytest

from agents.coordinator_agent import CoordinatorAgent
from agents.verifier_agent import VerificationError, VerifierAgent
from services.data_loader import load_cases
from services.policy_engine import apply_policy


ROOT = Path(__file__).resolve().parents[1]


def _order(status="delivered", late_handoff=False):
    return {
        "order_status": status,
        "late_handoff": late_handoff,
        "late_seller_ids": ["seller-1"] if late_handoff else [],
        "freight_total_brl": 12.5,
    }


def _payment(total=100.0, matches=True, split=False):
    return {
        "payment_total_brl": total,
        "payment_matches": matches,
        "is_split_payment": split,
    }


def _delivery(late=False):
    return {"delivered_late": late, "delivered_within_estimate": not late}


@pytest.mark.parametrize(
    ("order", "payment", "delivery", "expected"),
    [
        (_order("canceled"), _payment(), _delivery(), "canceled_order_paid"),
        (
            _order("unavailable"),
            _payment(),
            _delivery(),
            "unavailable_order_paid",
        ),
        (
            _order(late_handoff=True),
            _payment(),
            _delivery(late=True),
            "late_delivery_seller",
        ),
        (
            _order(),
            _payment(),
            _delivery(late=True),
            "late_delivery_logistics",
        ),
        (
            _order(),
            _payment(split=True),
            _delivery(),
            "valid_split_payment",
        ),
        (
            _order(),
            _payment(),
            _delivery(),
            "unsupported_late_claim",
        ),
    ],
)
def test_policy_covers_all_documented_rules(order, payment, delivery, expected):
    assert apply_policy(order, payment, delivery)["primary_issue"] == expected


def test_policy_priority_prefers_canceled_over_delivery_and_split_payment():
    result = apply_policy(
        _order("canceled", late_handoff=True),
        _payment(split=True),
        _delivery(late=True),
    )
    assert result["primary_issue"] == "canceled_order_paid"
    assert result["recommended_refund_brl"] == 100.0


def test_all_official_cases_produce_expected_balanced_issue_distribution():
    coordinator = CoordinatorAgent()
    results = [coordinator.process(case) for case in load_cases(ROOT / "input")]
    issues = Counter(result["assessment"]["primary_issue"] for result in results)
    assert issues == {
        "late_delivery_seller": 8,
        "late_delivery_logistics": 8,
        "canceled_order_paid": 8,
        "unavailable_order_paid": 8,
        "valid_split_payment": 9,
        "unsupported_late_claim": 9,
    }
    assert all(result["assessment"]["confidence"] == 1.0 for result in results)


def test_checked_in_outputs_are_complete_and_valid():
    output_files = sorted((ROOT / "output").glob("EC_*.json"))
    assert len(output_files) == 50
    verifier = VerifierAgent()
    for path in output_files:
        result = json.loads(path.read_text(encoding="utf-8"))
        assert result["case_id"] == path.stem
        assert verifier.verify(result) is result


def test_evidence_is_minimal_and_issue_specific():
    outputs = {
        json.loads(path.read_text())["assessment"]["primary_issue"]: json.loads(
            path.read_text()
        )
        for path in sorted((ROOT / "output").glob("EC_*.json"))
    }
    canceled = outputs["canceled_order_paid"]
    assert any(value.startswith("item:") for value in canceled["evidence_ids"])
    assert not any(value.startswith("seller:") for value in canceled["evidence_ids"])

    seller_late = outputs["late_delivery_seller"]
    assert any(value.startswith("item:") for value in seller_late["evidence_ids"])
    assert any(value.startswith("seller:") for value in seller_late["evidence_ids"])

    logistics = outputs["late_delivery_logistics"]
    assert any(value.startswith("item:") for value in logistics["evidence_ids"])
    assert not any(value.startswith("seller:") for value in logistics["evidence_ids"])


def test_verifier_rejects_malformed_evidence():
    result = json.loads((ROOT / "output" / "EC_001.json").read_text())
    result["evidence_ids"].append("tracking:not-in-olist")
    with pytest.raises(VerificationError, match="Malformed evidence"):
        VerifierAgent().verify(result)
