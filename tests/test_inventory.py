"""Tests for the stock rules. Run from the repository root with: pytest"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from inventory import Inventory, StockError  # noqa: E402


def make_inventory():
    return Inventory([
        {"sku": "A", "name": "Cable", "category": "Accessories", "price": 10.0,
         "stock": 5, "reorder_level": 2, "supplier": "S1"},
        {"sku": "B", "name": "Mouse", "category": "Peripherals", "price": 20.0,
         "stock": 1, "reorder_level": 3, "supplier": "S2"},
    ])


def test_status_in_low_out():
    inv = make_inventory()
    assert Inventory.status(inv.get("A")) == "in"
    assert Inventory.status(inv.get("B")) == "low"
    inv.record_sale("B", 1)
    assert Inventory.status(inv.get("B")) == "out"


def test_sale_reduces_stock():
    inv = make_inventory()
    inv.record_sale("A", 2)
    assert inv.get("A")["stock"] == 3


def test_stock_never_goes_below_zero():
    inv = make_inventory()
    with pytest.raises(StockError):
        inv.record_sale("B", 2)
    assert inv.get("B")["stock"] == 1


@pytest.mark.parametrize("bad", [0, -1, "abc", None])
def test_bad_quantities_are_rejected(bad):
    inv = make_inventory()
    with pytest.raises(StockError):
        inv.record_sale("A", bad)


def test_restock_adds_stock():
    inv = make_inventory()
    inv.restock("B", 10)
    assert inv.get("B")["stock"] == 11


def test_customer_view_hides_exact_stock():
    inv = make_inventory()
    view = inv.public_view(inv.get("A"))
    assert "stock" not in view
    assert view["status"] == "In stock"


def test_low_stock_list():
    inv = make_inventory()
    assert [p["sku"] for p in inv.low_stock()] == ["B"]
