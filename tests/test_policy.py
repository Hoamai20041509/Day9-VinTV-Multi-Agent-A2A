"""Tests for EC_POLICY_V1 rule precedence and resolutions."""
from services.policy_engine import CaseFacts, decide


def _facts(**overrides) -> CaseFacts:
    base = dict(
        order_found=True,
        order_status="delivered",
        payment_total_brl=115.0,
        freight_total_brl=15.0,
        payment_count=1,
        reconciled=True,
        delivered_late=False,
        late_seller_ids=[],
    )
    base.update(overrides)
    return CaseFacts(**base)


def test_canceled_order_paid_full_refund() -> None:
    decision = decide(_facts(order_status="canceled"))
    assert decision.primary_issue == "canceled_order_paid"
    assert decision.root_cause_code == "ORDER_CANCELED_AFTER_PAYMENT"
    assert decision.responsible_parties == [
        {"party_type": "platform", "party_id": "OLIST_PLATFORM"}
    ]
    assert decision.recommended_refund_brl == 115.0
    assert decision.action == "issue_full_refund"
    assert decision.case_status == "action_required"


def test_unavailable_order_paid_full_refund() -> None:
    decision = decide(_facts(order_status="unavailable", freight_total_brl=0.0))
    assert decision.primary_issue == "unavailable_order_paid"
    assert decision.root_cause_code == "ORDER_UNAVAILABLE_AFTER_PAYMENT"
    assert decision.recommended_refund_brl == 115.0


def test_late_delivery_seller_when_handoff_after_limit() -> None:
    decision = decide(_facts(delivered_late=True, late_seller_ids=["seller-1"]))
    assert decision.primary_issue == "late_delivery_seller"
    assert decision.root_cause_code == "SELLER_HANDOFF_AFTER_LIMIT"
    assert decision.responsible_parties == [
        {"party_type": "seller", "party_id": "seller-1"}
    ]
    assert decision.recommended_refund_brl == 15.0
    assert decision.action == "refund_freight"


def test_late_delivery_logistics_when_handoff_on_time() -> None:
    decision = decide(_facts(delivered_late=True))
    assert decision.primary_issue == "late_delivery_logistics"
    assert decision.root_cause_code == "CARRIER_DELIVERED_AFTER_ESTIMATE"
    assert decision.responsible_parties == [
        {"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}
    ]
    assert decision.recommended_refund_brl == 15.0


def test_valid_split_payment_no_refund() -> None:
    decision = decide(_facts(payment_count=2))
    assert decision.primary_issue == "valid_split_payment"
    assert decision.root_cause_code == "MULTIPLE_PAYMENTS_RECONCILED"
    assert decision.responsible_parties == []
    assert decision.recommended_refund_brl == 0.0
    assert decision.case_status == "no_action"


def test_unsupported_late_claim_when_on_time_and_reconciled() -> None:
    decision = decide(_facts())
    assert decision.primary_issue == "unsupported_late_claim"
    assert decision.root_cause_code == "DELIVERY_WITHIN_ESTIMATE"
    assert decision.action == "reject_late_refund"
    assert decision.case_status == "no_action"


def test_cancellation_beats_late_delivery() -> None:
    decision = decide(
        _facts(order_status="canceled", delivered_late=True, late_seller_ids=["seller-1"])
    )
    assert decision.primary_issue == "canceled_order_paid"


def test_late_delivery_beats_split_payment() -> None:
    decision = decide(_facts(delivered_late=True, payment_count=3))
    assert decision.primary_issue == "late_delivery_logistics"


def test_split_payment_beats_unsupported_claim() -> None:
    decision = decide(_facts(payment_count=2, delivered_late=False))
    assert decision.primary_issue == "valid_split_payment"


def test_canceled_without_payment_is_not_full_refund() -> None:
    decision = decide(_facts(order_status="canceled", payment_total_brl=0.0, reconciled=False))
    assert decision.primary_issue != "canceled_order_paid"
    assert decision.recommended_refund_brl == 0.0
