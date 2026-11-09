"""Inventory stored in MongoDB (Azure Cosmos DB for MongoDB).

It has the same methods as the in-memory Inventory in inventory.py, so the
web pages do not change. app.py uses this class when the MONGODB_URI setting
exists (on Azure), and the in-memory class otherwise (on a laptop).
"""

import json

from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError

from inventory import (DATA_FILE, STATUS_LABELS, Inventory,
                       StockError, check_new_status, new_reservation, now_iso,
                       reservation_view)


class MongoInventory:
    status = staticmethod(Inventory.status)
    _check_quantity = staticmethod(Inventory._check_quantity)
    _check_reserve_quantity = classmethod(Inventory._check_reserve_quantity.__func__)

    def __init__(self, collection):
        self.products = collection

    @classmethod
    def connect(cls, uri, database="stockwise", seed_file=DATA_FILE):
        from pymongo import MongoClient  # imported here so laptops without MongoDB still work
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        inventory = cls(client[database]["products"])
        inventory.seed_if_empty(seed_file)
        inventory.ensure_indexes()
        return inventory

    def ensure_indexes(self):
        """Indexes that make reservation lookups fast. Safe to run every start."""
        for field in ("reservations.id", "reservations.customer_email"):
            try:
                self.products.create_index(field)
            except Exception:
                pass  # the app still works without them, just a little slower

    def seed_if_empty(self, seed_file=DATA_FILE):
        """Load the sample products the first time the database is used."""
        if self.products.count_documents({}, limit=1):
            return
        try:
            # One document per product. Cosmos DB only allows a unique index on an
            # empty collection, so it is created here, before the first insert.
            self.products.create_index("sku", unique=True)
        except Exception:
            pass  # index already exists, or the service refused it; the app still works
        with open(seed_file, encoding="utf-8") as f:
            products = json.load(f)
        try:
            self.products.insert_many(products, ordered=False)
        except BulkWriteError:
            pass  # another app instance seeded at the same moment; the unique sku index keeps one copy

    @staticmethod
    def _clean(doc):
        if doc is not None:
            doc.pop("_id", None)
        return doc

    def all(self):
        return [self._clean(d) for d in self.products.find({}).sort("name", 1)]

    def get(self, sku):
        product = self._clean(self.products.find_one({"sku": sku}))
        if product is None:
            raise StockError(f"Unknown product: {sku}")
        return product

    def search(self, text):
        text = (text or "").strip().lower()
        items = self.all()
        if not text:
            return items
        return [p for p in items if text in p["name"].lower() or text in p["category"].lower()]

    def low_stock(self):
        items = [p for p in self.all() if self.status(p) != "in"]
        return sorted(items, key=lambda p: p["stock"])

    def public_view(self, product):
        return {
            "sku": product["sku"],
            "name": product["name"],
            "category": product["category"],
            "price": product["price"],
            "stock": product["stock"],
            "status": STATUS_LABELS[self.status(product)],
        }

    def record_sale(self, sku, quantity):
        """One atomic update: it only succeeds if enough stock is left,
        so two sales of the last item can never both succeed."""
        quantity = self._check_quantity(quantity)
        updated = self.products.find_one_and_update(
            {"sku": sku, "stock": {"$gte": quantity}},
            {"$inc": {"stock": -quantity}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            product = self.get(sku)  # raises StockError if the product does not exist
            raise StockError(
                f"Only {product['stock']} of {product['name']} left; cannot sell {quantity}."
            )
        return self._clean(updated)

    def restock(self, sku, quantity):
        quantity = self._check_quantity(quantity)
        updated = self.products.find_one_and_update(
            {"sku": sku},
            {"$inc": {"stock": quantity}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise StockError(f"Unknown product: {sku}")
        return self._clean(updated)

    # ---------- Reservations ----------
    # Each reservation is stored in its product document, so one atomic update
    # both takes the units out of stock and saves the reservation.

    def reserve(self, sku, quantity, customer_email, customer_name):
        quantity = self._check_reserve_quantity(quantity)
        reservation = new_reservation(quantity, customer_email, customer_name)
        updated = self.products.find_one_and_update(
            {"sku": sku, "stock": {"$gte": quantity}},
            {"$inc": {"stock": -quantity}, "$push": {"reservations": reservation}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            product = self.get(sku)  # raises StockError if the product does not exist
            raise StockError(
                f"Only {product['stock']} of {product['name']} left; cannot reserve {quantity}."
            )
        product = self._clean(updated)
        return product, reservation_view(product, reservation)

    def reservations(self, customer_email=None, status=None):
        query = {"reservations.customer_email": customer_email} if customer_email else {"reservations": {"$exists": True, "$ne": []}}
        views = []
        for doc in self.products.find(query, {"_id": 0}):
            for r in doc.get("reservations", []):
                if (customer_email is None or r["customer_email"] == customer_email) and \
                        (status is None or r["status"] == status):
                    views.append(reservation_view(doc, r))
        return sorted(views, key=lambda v: v["created_at"], reverse=True)

    def set_reservation_status(self, reservation_id, new_status, customer_email=None):
        doc = self.products.find_one({"reservations.id": reservation_id}, {"_id": 0})
        reservation = next((r for r in (doc or {}).get("reservations", []) if r["id"] == reservation_id), None)
        if reservation is None:
            raise StockError("Reservation not found.")
        give_back = check_new_status(reservation, new_status, customer_email)
        update = {"$set": {"reservations.$.status": new_status, "reservations.$.updated_at": now_iso()}}
        if give_back:
            update["$inc"] = {"stock": give_back}
        # Only succeeds if the reservation is still "reserved", so a reservation
        # can never be cancelled twice (which would add the units back twice).
        updated = self.products.find_one_and_update(
            {"sku": doc["sku"], "reservations": {"$elemMatch": {"id": reservation_id, "status": "reserved"}}},
            update,
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise StockError("This reservation was just changed. Please refresh the page.")
        product = self._clean(updated)
        changed = next(r for r in product["reservations"] if r["id"] == reservation_id)
        return product, reservation_view(product, changed)
