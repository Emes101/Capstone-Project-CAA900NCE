"""Tests for the YOLO shelf-scan comparison logic (no model needed).
Run from the repository root with: pytest"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "yolo"))

import shelf_scan  # noqa: E402

PRODUCTS = [
    {"sku": "CP-4001", "name": "Wireless mouse", "stock": 12},
    {"sku": "CP-4002", "name": "Mechanical keyboard", "stock": 3},
]


def rows_by_object(labels):
    return {r["object"]: r for r in shelf_scan.compare(shelf_scan.count_labels(labels), PRODUCTS)}


def test_counts_and_flags_missing_items():
    rows = rows_by_object(["mouse", "mouse", "mouse", "keyboard", "keyboard", "keyboard"])
    assert rows["mouse"]["seen"] == 3 and rows["mouse"]["expected"] == 12
    assert rows["mouse"]["note"] == "Check: 9 not on this shelf"
    assert rows["keyboard"]["note"] == "Matches the app"


def test_products_not_in_photo_are_listed():
    rows = rows_by_object([])
    assert rows["keyboard"]["seen"] == 0 and rows["keyboard"]["note"] == "Check: 3 not on this shelf"


def test_more_than_expected_and_unknown_objects():
    rows = rows_by_object(["keyboard"] * 5 + ["cup"])
    assert rows["keyboard"]["note"] == "Check: 2 more than the app shows"
    assert rows["cup"]["note"] == "Not one of our products" and rows["cup"]["sku"] is None


def test_sample_stock_file_has_the_mapped_products():
    skus = {p["sku"] for p in shelf_scan.load_products()}
    assert set(shelf_scan.COCO_TO_SKU.values()) <= skus
