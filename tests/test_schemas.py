"""Contract tests owned by the coordinator/tech-lead role."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.schemas import AffectedEntities, CaseInput, FinancialResolution


def test_official_case_input_parses() -> None:
    raw = json.loads(Path("input/EC_001.json").read_text(encoding="utf-8"))
    case = CaseInput.model_validate(raw)

    assert case.case_id == "EC_001"
    assert case.order_id == raw["customer_request"]["claimed_order_id"]


def test_case_id_format_is_enforced() -> None:
    with pytest.raises(ValidationError):
        CaseInput.model_validate(
            {
                "case_id": "CASE-1",
                "opened_at": "2018-10-18T00:00:00-03:00",
                "customer_request": {
                    "language": "vi",
                    "message": "test",
                    "claimed_order_id": "order-1",
                },
                "policy_version": "EC_POLICY_V1",
            }
        )


def test_entity_limit_is_enforced() -> None:
    with pytest.raises(ValidationError):
        AffectedEntities(order_ids=[f"order-{index}" for index in range(6)])


def test_money_uses_half_up_rounding() -> None:
    resolution = FinancialResolution(
        currency="BRL",
        item_total_brl="1.005",
        freight_total_brl=0,
        payment_total_brl=1.01,
        recommended_refund_brl=0,
    )

    assert resolution.item_total_brl == 1.01
