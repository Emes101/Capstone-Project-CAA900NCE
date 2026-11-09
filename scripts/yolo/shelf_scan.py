"""YOLO shelf-scan prototype for StockWise.

Michael takes a photo of a shelf. A ready-made YOLO model (YOLOv8n, trained on
the COCO dataset's 80 everyday objects) finds the products in the photo and
counts them. The script then compares the count with the stock the app expects
and flags products to check: for example, the app says 12 wireless mice but the
shelf photo shows only 3, so some may be in the back room, misplaced or missing.

It runs on a laptop, not on Azure (the model needs more memory than our B1 plan).

  pip install -r scripts/yolo/requirements.txt
  python3 scripts/yolo/shelf_scan.py shelf.jpg
  python3 scripts/yolo/shelf_scan.py shelf.jpg --from-database   # live stock (needs MONGODB_URI)

The first run downloads the model file (yolov8n.pt, about 6 MB).
The photo with boxes drawn on it is saved in scan-results/.

Limits of the prototype: COCO only knows some of our products (mouse, keyboard,
phone, laptop). Recognising every product would need our own training photos,
which is the next step after the capstone.
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_STOCK = ROOT / "app" / "data" / "sample_products.json"

# COCO object name -> our product SKU. Edit this list when products change.
COCO_TO_SKU = {
    "mouse": "CP-4001",      # Wireless mouse
    "keyboard": "CP-4002",   # Mechanical keyboard
}


def count_labels(labels):
    """['mouse', 'mouse', 'cup'] -> Counter({'mouse': 2, 'cup': 1})"""
    return Counter(labels)


def compare(counts, products, mapping=COCO_TO_SKU):
    """Rows comparing what the photo shows with what the app expects.

    Each row: object, seen, sku, product, expected, note. Products that the
    model knows but that are not in the photo are listed too (seen = 0)."""
    by_sku = {p["sku"]: p for p in products}
    rows = []
    for obj in sorted(set(counts) | set(mapping)):
        seen = counts.get(obj, 0)
        sku = mapping.get(obj)
        product = by_sku.get(sku) if sku else None
        if product is None:
            rows.append({"object": obj, "seen": seen, "sku": None, "product": None,
                         "expected": None, "note": "Not one of our products"})
            continue
        expected = product["stock"]
        if seen == expected:
            note = "Matches the app"
        elif seen < expected:
            note = f"Check: {expected - seen} not on this shelf"
        else:
            note = f"Check: {seen - expected} more than the app shows"
        rows.append({"object": obj, "seen": seen, "sku": sku, "product": product["name"],
                     "expected": expected, "note": note})
    return rows


def load_products(from_database=False):
    if from_database:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            sys.exit("Set MONGODB_URI first (see docs/YOLO-SHELF-SCAN.md).")
        db = MongoClient(uri, serverSelectionTimeoutMS=15000)[os.environ.get("MONGODB_DB", "stockwise")]
        return list(db["products"].find({}, {"_id": 0, "sku": 1, "name": 1, "stock": 1}))  # read only
    return json.loads(SAMPLE_STOCK.read_text(encoding="utf-8"))


def detect(image, confidence, out_dir):
    """Run YOLO on one photo. Returns the object names found and the saved image path."""
    from ultralytics import YOLO  # imported here so the tests do not need it
    model = YOLO("yolov8n.pt")
    result = model(str(image), conf=confidence, verbose=False)[0]
    labels = [result.names[int(c)] for c in result.boxes.cls]
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = out_dir / f"{Path(image).stem}-scanned.jpg"
    result.save(filename=str(saved))
    return labels, saved


def print_table(rows):
    print(f"{'Object':<12}{'Seen':>5}  {'Product':<26}{'App stock':>10}  Note")
    print("-" * 80)
    for r in rows:
        expected = "" if r["expected"] is None else r["expected"]
        print(f"{r['object']:<12}{r['seen']:>5}  {(r['product'] or '-'):<26}{expected:>10}  {r['note']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Count products in a shelf photo with YOLO.")
    parser.add_argument("image", help="photo of a shelf (jpg or png)")
    parser.add_argument("--confidence", type=float, default=0.35, help="0 to 1; higher = fewer, surer boxes")
    parser.add_argument("--from-database", action="store_true", help="compare with live stock (MONGODB_URI)")
    parser.add_argument("--out", default="scan-results", help="folder for the photo with boxes")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)

    if not Path(args.image).is_file():
        sys.exit(f"Photo not found: {args.image}")
    labels, saved = detect(args.image, args.confidence, Path(args.out))
    rows = compare(count_labels(labels), load_products(args.from_database))
    if args.json:
        print(json.dumps({"image": args.image, "saved": str(saved), "rows": rows}, indent=2))
    else:
        print(f"Found {len(labels)} object(s) in {args.image}. Photo with boxes: {saved}\n")
        print_table(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
