"""Inventory logic for StockWise Solutions.

This module holds the business rules, separate from the web pages, so they can
be tested on their own. For now the data comes from a JSON file of sample
products and is kept in memory. In Progress Submission 3 the same methods will
read and write Azure SQL Database instead.
"""

import json
from pathlib import Path
from threading import Lock

DATA_FILE = Path(__file__).parent / "data" / "sample_products.json"

# Status labels shown to users. Each status is always shown as text,
# never by colour alone.
STATUS_LABELS = {"in": "In stock", "low": "Low stock", "out": "Out of stock"}


class StockError(ValueError):
    """Raised when a request would break a stock rule."""


class Inventory:
    def __init__(self, products):
        # Store products by SKU so each lookup is fast and unique.
        self._products = {p["sku"]: dict(p) for p in products}
        # The lock makes each stock update happen one at a time, so two sales
        # of the last item can never both succeed.
        self._lock = Lock()

    @classmethod
    def from_file(cls, path=DATA_FILE):
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    @staticmethod
    def status(product):
        """Return 'out', 'low' or 'in' for a product."""
        if product["stock"] <= 0:
            return "out"
        if product["stock"] <= product["reorder_level"]:
            return "low"
        return "in"

    def all(self):
        return sorted(self._products.values(), key=lambda p: p["name"])

    def get(self, sku):
        product = self._products.get(sku)
        if product is None:
            raise StockError(f"Unknown product: {sku}")
        return product

    def search(self, text):
        """Products whose name or category contains the search text."""
        text = (text or "").strip().lower()
        if not text:
            return self.all()
        return [
            p for p in self.all()
            if text in p["name"].lower() or text in p["category"].lower()
        ]

    def low_stock(self):
        """Products at or below their reorder level, lowest stock first."""
        items = [p for p in self.all() if self.status(p) != "in"]
        return sorted(items, key=lambda p: p["stock"])

    def public_view(self, product):
        """What a customer may see: availability only, never exact counts."""
        return {
            "sku": product["sku"],
            "name": product["name"],
            "category": product["category"],
            "price": product["price"],
            "status": STATUS_LABELS[self.status(product)],
        }

    @staticmethod
    def _check_quantity(quantity):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise StockError("Quantity must be a whole number.")
        if quantity <= 0:
            raise StockError("Quantity must be greater than zero.")
        return quantity

    def record_sale(self, sku, quantity):
        """Reduce stock for a sale. Stock can never go below zero."""
        quantity = self._check_quantity(quantity)
        with self._lock:
            product = self.get(sku)
            if quantity > product["stock"]:
                raise StockError(
                    f"Only {product['stock']} of {product['name']} left; "
                    f"cannot sell {quantity}."
                )
            product["stock"] -= quantity
            return product

    def restock(self, sku, quantity):
        """Add stock when a delivery arrives."""
        quantity = self._check_quantity(quantity)
        with self._lock:
            product = self.get(sku)
            product["stock"] += quantity
            return product
