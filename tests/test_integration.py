"""End-to-end coordinator tests over real input cases (LLM disabled).

Expected values were derived by an independent rule implementation reading the
raw CSVs directly (no shared code with the pipeline), one case per policy rule.
"""
import json
from pathlib import Path

import pytest

from agents.coordinator_agent import CoordinatorAgent
from shared.schemas import validate_case_output

ROOT = Path(__file__).resolve().parents[1]

# case_id -> (primary_issue, recommended_refund_brl, payment_total_brl)
EXPECTED = {
    "EC_001": ("late_delivery_seller", 12.04, 131.94),
    "EC_002": ("unsupported_late_claim", 0.0, 180.62),
    "EC_003": ("canceled_order_paid", 109.34, 109.34),
    "EC_004": ("valid_split_payment", 0.0, 211.96),
    "EC_005": ("unavailable_order_paid", 1191.50, 1191.50),
}


@pytest.fixture(scope="module")
def coordinator() -> CoordinatorAgent:
    return CoordinatorAgent(use_llm=False)


def _load_case(case_id: str) -> dict:
    return json.loads((ROOT / "input" / f"{case_id}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case_id", sorted(EXPECTED))
def test_case_end_to_end(coordinator: CoordinatorAgent, case_id: str) -> None:
    issue, refund, payment_total = EXPECTED[case_id]
    output = coordinator.handle_case(_load_case(case_id))

    assert output["case_id"] == case_id
    assert output["assessment"]["primary_issue"] == issue
    assert output["financial_resolution"]["recommended_refund_brl"] == refund
    assert output["financial_resolution"]["payment_total_brl"] == payment_total
    expected_status = "action_required" if refund > 0 else "no_action"
    assert output["assessment"]["case_status"] == expected_status
    assert validate_case_output(output) == []
    assert any(e.startswith("policy:") for e in output["evidence_ids"])
    assert output["affected_entities"]["order_ids"] == [
        _load_case(case_id)["customer_request"]["claimed_order_id"]
    ]


def test_unavailable_case_has_empty_items_and_zero_totals(
    coordinator: CoordinatorAgent,
) -> None:
    output = coordinator.handle_case(_load_case("EC_005"))
    assert output["affected_entities"]["item_ids"] == []
    assert output["affected_entities"]["seller_ids"] == []
    assert output["financial_resolution"]["item_total_brl"] == 0.0
    assert output["financial_resolution"]["freight_total_brl"] == 0.0


def test_seller_case_names_responsible_seller(coordinator: CoordinatorAgent) -> None:
    output = coordinator.handle_case(_load_case("EC_001"))
    parties = output["root_cause_analysis"]["responsible_parties"]
    assert parties and all(p["party_type"] == "seller" for p in parties)
    assert any(e.startswith("seller:") for e in output["evidence_ids"])
