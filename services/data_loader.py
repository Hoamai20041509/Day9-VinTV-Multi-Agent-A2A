"""Shared repository instances so every agent reads one in-memory copy."""
from __future__ import annotations

from functools import lru_cache

from services.item_repository import ItemRepository
from services.order_repository import OrderRepository


@lru_cache(maxsize=1)
def get_order_repository() -> OrderRepository:
    return OrderRepository()


@lru_cache(maxsize=1)
def get_item_repository() -> ItemRepository:
    return ItemRepository()
