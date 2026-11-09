"""Inventory logic for StockWise Solutions.

This module holds the business rules, separate from the web pages, so they can
be tested on their own. Inventory keeps the sample products in memory (laptop
and tests); MongoInventory in mongo_inventory.py has the same methods and saves
to Azure Cosmos DB for MongoDB.

Reservations: a customer reserves units for pickup. The units are taken out of
stock at once, so two customers can never reserve the same last item. Each
reservation is stored inside its product, so taking the units and saving the
reservation happen in one atomic update. The owner later marks it picked up
(the units stay sold) or cancelled (the units go back into stock).
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

DATA_FILE = Path(__file__).parent / "data" / "sample_products.json"

# Status labels shown to users. Each status is always shown as text,
# never by colour alone.
STATUS_LABELS = {"in": "In stock", "low": "Low stock", "out": "Out of stock"}


class StockError(ValueError):
    """Raised when a request would break a stock rule."""


# Reservation states. Only a "reserved" reservation can change.
RESERVED, PICKED_UP, CANCELLED = "reserved", "picked_up", "cancelled"
RESERVATION_LABELS = {RESERVED: "Waiting for pickup", PICKED_UP: "Picked up", CANCELLED: "Cancelled"}
MAX_RESERVE_QUANTITY = 5  # per reservation, so one customer cannot hold all the stock


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_reservation(quantity, customer_email, customer_name):
    stamp = now_iso()
    return {
        "id": uuid.uuid4().hex[:12],
        "quantity": quantity,
        "customer_email": customer_email,
        "customer_name": customer_name,
        "status": RESERVED,
        "created_at": stamp,
        "updated_at": stamp,
    }


def reservation_view(product, reservation):
    """One reservation with its product details, as pages and the API show it."""
    return {
        "id": reservation["id"],
        "sku": product["sku"],
        "product_name": product["name"],
        "price": product["price"],
        "quantity": reservation["quantity"],
        "status": reservation["status"],
        "status_label": RESERVATION_LABELS[reservation["status"]],
        "customer_email": reservation["customer_email"],
        "customer_name": reservation["customer_name"],
        "created_at": reservation["created_at"],
        "updated_at": reservation["updated_at"],
    }


def check_new_status(reservation, new_status, customer_email=None):
    """Shared rules for changing a reservation. Returns the stock to give back."""
    if new_status not in (PICKED_UP, CANCELLED):
        raise StockError("Unknown reservation status.")
    if customer_email is not None and reservation["customer_email"] != customer_email:
        raise StockError("Reservation not found.")  # customers only see their own
    if reservation["status"] != RESERVED:
        raise StockError("This reservation is already " + RESERVATION_LABELS[reservation["status"]].lower() + ".")
    return reservation["quantity"] if new_status == CANCELLED else 0


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
        """What a customer may see: product details and units in stock.
        Suppliers and reorder levels stay internal (owner only)."""
        return {
            "sku": product["sku"],
            "name": product["name"],
            "category": product["category"],
            "price": product["price"],
            "stock": product["stock"],
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

    @classmethod
    def _check_reserve_quantity(cls, quantity):
        quantity = cls._check_quantity(quantity)
        if quantity > MAX_RESERVE_QUANTITY:
            raise StockError(f"You can reserve up to {MAX_RESERVE_QUANTITY} units at a time.")
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

    # ---------- Reservations ----------

    def reserve(self, sku, quantity, customer_email, customer_name):
        """Hold units for a customer. Returns (product, reservation view)."""
        quantity = self._check_reserve_quantity(quantity)
        with self._lock:
            product = self.get(sku)
            if quantity > product["stock"]:
                raise StockError(
                    f"Only {product['stock']} of {product['name']} left; "
                    f"cannot reserve {quantity}."
                )
            reservation = new_reservation(quantity, customer_email, customer_name)
            product["stock"] -= quantity
            product.setdefault("reservations", []).append(reservation)
            return product, reservation_view(product, reservation)

    def _all_pairs(self):
        for product in self._products.values():
            for reservation in product.get("reservations", []):
                yield product, reservation

    def reservations(self, customer_email=None, status=None):
        """Reservations, newest first; optionally for one customer or one status."""
        views = [
            reservation_view(p, r) for p, r in self._all_pairs()
            if (customer_email is None or r["customer_email"] == customer_email)
            and (status is None or r["status"] == status)
        ]
        return sorted(views, key=lambda v: v["created_at"], reverse=True)

    def set_reservation_status(self, reservation_id, new_status, customer_email=None):
        """Mark picked up or cancelled. Cancelling puts the units back into stock.
        Pass customer_email to allow a customer to change only their own."""
        with self._lock:
            for product, reservation in self._all_pairs():
                if reservation["id"] == reservation_id:
                    give_back = check_new_status(reservation, new_status, customer_email)
                    reservation["status"] = new_status
                    reservation["updated_at"] = now_iso()
                    product["stock"] += give_back
                    return product, reservation_view(product, reservation)
        raise StockError("Reservation not found.")
