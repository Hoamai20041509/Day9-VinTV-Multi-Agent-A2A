"""Read-only access to Olist order items and sellers."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_ITEMS_PATH = DATA_DIR / "olist_order_items_dataset.csv"
DEFAULT_SELLERS_PATH = DATA_DIR / "olist_sellers_dataset.csv"


def _item_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    value = str(item.get("order_item_id", ""))
    try:
        return int(value), value
    except ValueError:
        return 0, value


class ItemRepository:
    """Index item rows by order and seller records by seller ID."""

    def __init__(
        self,
        items_csv_path: str | Path = DEFAULT_ITEMS_PATH,
        sellers_csv_path: str | Path = DEFAULT_SELLERS_PATH,
    ) -> None:
        self.items_csv_path = Path(items_csv_path)
        self.sellers_csv_path = Path(sellers_csv_path)
        self._items: dict[str, list[dict[str, Any]]] | None = None
        self._sellers: dict[str, dict[str, Any]] | None = None

    def _load_items(self) -> None:
        if self._items is not None:
            return
        indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
        with self.items_csv_path.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source):
                indexed[row["order_id"]].append(dict(row))
        for items in indexed.values():
            items.sort(key=_item_sort_key)
        self._items = dict(indexed)

    def _load_sellers(self) -> None:
        if self._sellers is not None:
            return
        with self.sellers_csv_path.open(encoding="utf-8", newline="") as source:
            self._sellers = {
                row["seller_id"]: dict(row) for row in csv.DictReader(source)
            }

    def get_items(self, order_id: str) -> list[dict[str, Any]]:
        self._load_items()
        assert self._items is not None
        return [dict(item) for item in self._items.get(order_id, [])]

    def get_items_by_order_id(self, order_id: str) -> list[dict[str, Any]]:
        return self.get_items(order_id)

    def get_seller(self, seller_id: str) -> dict[str, Any] | None:
        self._load_sellers()
        assert self._sellers is not None
        seller = self._sellers.get(seller_id)
        return dict(seller) if seller is not None else None

    def get_sellers(self, seller_ids: Iterable[str]) -> list[dict[str, Any]]:
        sellers = []
        for seller_id in dict.fromkeys(seller_ids):
            seller = self.get_seller(seller_id)
            if seller is not None:
                sellers.append(seller)
        return sellers
