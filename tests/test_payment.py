"""Tests for the Payment Agent's deterministic reconciliation core.

Ground truth below was cross-checked directly against data/olist_order_payments_dataset.csv
and data/olist_order_items_dataset.csv for the official EC_001-EC_050 claimed_order_ids
(item_total_brl/freight_total_brl are what the Order & Seller Agent would hand off).
No test here loads the LLM - PaymentAgent.analyze() never depends on it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.payment_agent import MAX_PAYMENT_IDS, compute_reconciliation


def test_single_payment_reconciles_ec001():
    r = compute_reconciliation(
        "e2a03ccf5ea816036608b2d8c3ab8e60", item_total_brl=119.90, freight_total_brl=12.04
    )
    assert r.payment_total_brl == 131.94
    assert r.payment_count == 1
    assert r.is_split_payment is False
    assert r.reconciled is True
    assert r.payment_ids == ["payment:e2a03ccf5ea816036608b2d8c3ab8e60:1"]


def test_two_way_split_payment_reconciles_ec004():
    r = compute_reconciliation(
        "fd28a6dfe413804d0b89b7c9abf5b1f3", item_total_brl=179.90, freight_total_brl=32.06
    )
    assert r.payment_total_brl == 211.96
    assert r.payment_count == 2
    assert r.is_split_payment is True
    assert r.reconciled is True


def test_three_way_split_payment_reconciles_ec030():
    r = compute_reconciliation(
        "405be8487a7fde1db0bc31ad6b08050a", item_total_brl=15.90, freight_total_brl=9.94
    )
    assert r.payment_total_brl == 25.84
    assert r.payment_count == 3
    assert r.is_split_payment is True
    assert r.reconciled is True


def test_unavailable_order_no_items_reports_raw_totals_ec005():
    # No item rows -> TV2 hands off 0.0/0.0. Payment Agent reports the numbers
    # honestly (reconciled=False against 0); the Coordinator/Policy Agent, not
    # this agent, decides unavailable_order_paid overrides the split-payment rule.
    r = compute_reconciliation(
        "9a31fd9d697e9670777501f720773fd9", item_total_brl=0.0, freight_total_brl=0.0
    )
    assert r.payment_total_brl == 1191.50
    assert r.payment_count == 1
    assert r.is_split_payment is False
    assert r.reconciled is False
    assert r.payment_ids == ["payment:9a31fd9d697e9670777501f720773fd9:1"]


def test_canceled_order_paid_totals_ec003():
    r = compute_reconciliation(
        "71303d7e93b399f5bcd537d124c0bcfa", item_total_brl=100.0, freight_total_brl=9.34
    )
    assert r.payment_total_brl == 109.34
    assert r.payment_count == 1


def test_missing_order_returns_zeroed_result():
    r = compute_reconciliation("does-not-exist", item_total_brl=10.0, freight_total_brl=1.0)
    assert r.payment_total_brl == 0.0
    assert r.payment_count == 0
    assert r.is_split_payment is False
    assert r.payment_ids == []


def test_payment_ids_capped_at_five_but_total_sums_all_rows():
    # Real order with 29 payment rows (outside the official 50, used only to
    # exercise the cap): total must include all 29, payment_ids only the first 5.
    order_id = "fa65dad1b0e818e3ccc5cb0e39231352"
    r = compute_reconciliation(order_id, item_total_brl=0.0, freight_total_brl=457.99)
    assert r.payment_count == 29
    assert r.payment_total_brl == 457.99
    assert len(r.payment_ids) == MAX_PAYMENT_IDS
    assert r.payment_ids == [f"payment:{order_id}:{i}" for i in range(1, 6)]
