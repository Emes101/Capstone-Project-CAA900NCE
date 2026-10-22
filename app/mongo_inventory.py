"""Inventory stored in MongoDB (Azure Cosmos DB for MongoDB).

It has the same methods as the in-memory Inventory in inventory.py, so the
web pages do not change. app.py uses this class when the MONGODB_URI setting
exists (on Azure), and the in-memory class otherwise (on a laptop).
"""

import json

from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError

from inventory import DATA_FILE, STATUS_LABELS, Inventory, StockError


class MongoInventory:
    status = staticmethod(Inventory.status)
    _check_quantity = staticmethod(Inventory._check_quantity)

    def __init__(self, collection):
        self.products = collection

    @classmethod
    def connect(cls, uri, database="stockwise", seed_file=DATA_FILE):
        from pymongo import MongoClient  # imported here so laptops without MongoDB still work
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        inventory = cls(client[database]["products"])
        inventory.seed_if_empty(seed_file)
        return inventory

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
