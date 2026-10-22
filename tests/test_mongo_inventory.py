"""Tests for the MongoDB inventory, using mongomock (an in-memory MongoDB).
Run from the repository root with: pytest"""

import sys
from pathlib import Path

import mongomock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from inventory import StockError  # noqa: E402
from mongo_inventory import MongoInventory  # noqa: E402


@pytest.fixture
def inv():
    collection = mongomock.MongoClient()["stockwise"]["products"]
    collection.create_index("sku", unique=True)
    inventory = MongoInventory(collection)
    inventory.seed_if_empty()
    return inventory


def test_seeds_sample_products_once(inv):
    count = len(inv.all())
    inv.seed_if_empty()
    assert count == 12
    assert len(inv.all()) == 12


def test_sale_is_saved(inv):
    before = inv.get("EL-1001")["stock"]
    inv.record_sale("EL-1001", 2)
    assert inv.get("EL-1001")["stock"] == before - 2


def test_stock_never_goes_below_zero(inv):
    with pytest.raises(StockError):
        inv.record_sale("MA-2002", 1)  # sample data: 0 in stock
    assert inv.get("MA-2002")["stock"] == 0


def test_restock_is_saved(inv):
    inv.restock("MA-2002", 5)
    assert inv.get("MA-2002")["stock"] == 5


def test_unknown_product(inv):
    with pytest.raises(StockError):
        inv.record_sale("NOPE", 1)


def test_no_database_ids_leak_to_pages(inv):
    assert "_id" not in inv.all()[0]
    assert "_id" not in inv.get("EL-1001")
