import csv
from pathlib import Path

import pytest

from agents.order_seller_agent import OrderSellerAgent
from services.item_repository import ItemRepository
from services.order_repository import OrderRepository


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def agent(tmp_path: Path) -> OrderSellerAgent:
    orders = tmp_path / "orders.csv"
    items = tmp_path / "items.csv"
    sellers = tmp_path / "sellers.csv"
    _write_csv(
        orders,
        ["order_id", "order_status", "order_delivered_carrier_date"],
        [
            {
                "order_id": "late-order",
                "order_status": "delivered",
                "order_delivered_carrier_date": "2018-02-02 10:00:00",
            },
            {
                "order_id": "empty-order",
                "order_status": "canceled",
                "order_delivered_carrier_date": "",
            },
            {
                "order_id": "many-order",
                "order_status": "shipped",
                "order_delivered_carrier_date": "2018-02-01 10:00:00",
            },
        ],
    )
    item_rows = [
        {
            "order_id": "late-order",
            "order_item_id": "1",
            "product_id": "p1",
            "seller_id": "seller-late",
            "shipping_limit_date": "2018-02-01 10:00:00",
            "price": "10.005",
            "freight_value": "2.335",
        },
        {
            "order_id": "late-order",
            "order_item_id": "2",
            "product_id": "p2",
            "seller_id": "seller-on-time",
            "shipping_limit_date": "2018-02-03 10:00:00",
            "price": "20.005",
            "freight_value": "3.335",
        },
    ]
    item_rows.extend(
        {
            "order_id": "many-order",
            "order_item_id": str(index),
            "product_id": f"p{index}",
            "seller_id": f"seller-{index}",
            "shipping_limit_date": "2018-01-01 10:00:00",
            "price": "1.00",
            "freight_value": "0.10",
        }
        for index in range(1, 8)
    )
    _write_csv(
        items,
        [
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
        ],
        item_rows,
    )
    _write_csv(
        sellers,
        ["seller_id", "seller_city"],
        [
            {"seller_id": "seller-late", "seller_city": "a"},
            {"seller_id": "seller-on-time", "seller_city": "b"},
            *[
                {"seller_id": f"seller-{index}", "seller_city": "c"}
                for index in range(1, 8)
            ],
        ],
    )
    return OrderSellerAgent(OrderRepository(orders), ItemRepository(items, sellers))


def test_returns_status_entities_totals_and_exact_late_seller(
    agent: OrderSellerAgent,
) -> None:
    result = agent.analyze("late-order")

    assert result["order_found"] is True
    assert result["order_status"] == "delivered"
    assert result["item_ids"] == ["late-order:1", "late-order:2"]
    assert result["seller_ids"] == ["seller-late", "seller-on-time"]
    assert result["item_total_brl"] == 30.01
    assert result["freight_total_brl"] == 5.67
    assert result["late_handoff"] is True
    assert result["late_item_ids"] == ["late-order:1"]
    assert result["late_seller_ids"] == ["seller-late"]
    assert "order:late-order" in result["evidence_ids"]
    assert "item:late-order:1" in result["evidence_ids"]
    assert "seller:seller-late" in result["evidence_ids"]


def test_missing_order(agent: OrderSellerAgent) -> None:
    result = agent.analyze("does-not-exist")
    assert result["order_found"] is False
    assert result["order_status"] is None
    assert result["evidence_ids"] == []


def test_order_without_items_has_zero_totals(agent: OrderSellerAgent) -> None:
    result = agent.analyze("empty-order")
    assert result["order_status"] == "canceled"
    assert result["item_ids"] == []
    assert result["seller_ids"] == []
    assert result["item_total_brl"] == 0.0
    assert result["freight_total_brl"] == 0.0
    assert result["late_handoff"] is False


def test_entity_lists_are_capped_but_totals_use_every_item(
    agent: OrderSellerAgent,
) -> None:
    result = agent.analyze("many-order")
    assert len(result["item_ids"]) == 5
    assert len(result["seller_ids"]) == 5
    assert len(result["late_item_ids"]) == 5
    assert len(result["late_seller_ids"]) == 5
    assert result["item_total_brl"] == 7.0
    assert result["freight_total_brl"] == 0.7


def test_rejects_entity_limit_above_schema_maximum() -> None:
    with pytest.raises(ValueError, match="between 1 and 5"):
        OrderSellerAgent(max_entities=6)
