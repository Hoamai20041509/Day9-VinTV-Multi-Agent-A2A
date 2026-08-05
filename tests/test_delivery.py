"""Tests for delivery analysis (actual delivery vs estimate)."""
from services.delivery_analysis import delivered_late


def test_delivered_after_estimate_is_late() -> None:
    assert (
        delivered_late(
            {
                "order_delivered_customer_date": "2018-10-20 12:00:00",
                "order_estimated_delivery_date": "2018-10-18 00:00:00",
            }
        )
        is True
    )


def test_delivered_on_estimate_day_boundary_is_not_late() -> None:
    # Estimate carries a 00:00:00 time; equality must not count as late.
    assert (
        delivered_late(
            {
                "order_delivered_customer_date": "2018-10-18 00:00:00",
                "order_estimated_delivery_date": "2018-10-18 00:00:00",
            }
        )
        is False
    )


def test_delivered_before_estimate_is_not_late() -> None:
    assert (
        delivered_late(
            {
                "order_delivered_customer_date": "2018-10-10 08:30:00",
                "order_estimated_delivery_date": "2018-10-18 00:00:00",
            }
        )
        is False
    )


def test_undelivered_order_returns_none() -> None:
    assert (
        delivered_late(
            {
                "order_delivered_customer_date": "",
                "order_estimated_delivery_date": "2018-10-18 00:00:00",
            }
        )
        is None
    )
