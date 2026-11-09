"""Back up and restore the StockWise database (Azure Cosmos DB for MongoDB).

  backup    saves the products and users collections to one JSON file
  restore   puts the products from a backup file back into the database
  verify    compares a backup file with the database, without changing anything

Run it in Azure Cloud Shell (Bash). The connection string is read from the
MONGODB_URI environment variable, so it is never typed on the command line or
saved in a file. See docs/BACKUP-RESTORE.md for the full test.

  python3 scripts/backup_restore.py backup
  python3 scripts/backup_restore.py verify  backups/stockwise-YYYYmmdd-HHMMSS.json
  python3 scripts/backup_restore.py restore backups/stockwise-YYYYmmdd-HHMMSS.json --yes

Restore replaces each product in the database with its copy from the backup
(matched by SKU) and adds products that are missing. Products that are not in the
backup are left alone. User accounts are only restored with --include-users.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

COLLECTIONS = {"products": "sku", "users": "email"}  # collection -> unique key


def connect(uri=None, database=None):
    from pymongo import MongoClient
    uri = uri or os.environ.get("MONGODB_URI")
    if not uri:
        sys.exit("MONGODB_URI is not set. See docs/BACKUP-RESTORE.md, step 2.")
    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    return client[database or os.environ.get("MONGODB_DB", "stockwise")]


def backup(db, folder="backups"):
    data = {name: list(db[name].find({}, {"_id": 0})) for name in COLLECTIONS}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = Path(folder) / f"stockwise-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {"created_at": stamp, "database": db.name, "collections": data}
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o600)  # it holds customer emails and password hashes: owner-only file
    counts = {name: len(docs) for name, docs in data.items()}
    return path, counts


def load(path):
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    if "collections" not in content:
        sys.exit(f"{path} is not a StockWise backup file.")
    return content


def differences(db, content, name="products"):
    """Documents whose saved copy differs from the database (or is missing there)."""
    key = COLLECTIONS[name]
    current = {d[key]: d for d in db[name].find({}, {"_id": 0})}
    changed = []
    for doc in content["collections"].get(name, []):
        if current.get(doc[key]) != doc:
            changed.append(doc[key])
    return changed


def restore(db, content, include_users=False):
    restored = {}
    for name, key in COLLECTIONS.items():
        if name == "users" and not include_users:
            continue
        docs = content["collections"].get(name, [])
        for doc in docs:
            db[name].replace_one({key: doc[key]}, doc, upsert=True)
        restored[name] = len(docs)
    return restored


def main(argv=None, db=None):
    parser = argparse.ArgumentParser(description="Back up and restore the StockWise database.")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup", help="save products and users to a JSON file")
    b.add_argument("--folder", default="backups")
    v = sub.add_parser("verify", help="compare a backup file with the database")
    v.add_argument("file")
    r = sub.add_parser("restore", help="put products from a backup back into the database")
    r.add_argument("file")
    r.add_argument("--include-users", action="store_true", help="also restore user accounts")
    r.add_argument("--yes", action="store_true", help="confirm: this overwrites live data")
    args = parser.parse_args(argv)

    db = db if db is not None else connect()

    if args.command == "backup":
        path, counts = backup(db, args.folder)
        print(f"Backup saved: {path}")
        for name, count in counts.items():
            print(f"  {name}: {count} documents")
        return 0

    content = load(args.file)
    if args.command == "verify":
        changed = differences(db, content)
        if changed:
            print(f"{len(changed)} product(s) differ from the backup: {', '.join(changed)}")
        else:
            print("The products in the database match the backup.")
        return 0

    # restore
    if not args.yes:
        print("Restore overwrites live data. Run it again with --yes to confirm.")
        return 1
    changed = differences(db, content)
    restored = restore(db, content, args.include_users)
    print(f"Restored from {args.file} (taken {content['created_at']} UTC):")
    for name, count in restored.items():
        print(f"  {name}: {count} documents written")
    print(f"  products that were different before the restore: {', '.join(changed) or 'none'}")
    remaining = differences(db, content)
    print("Check: the products now match the backup." if not remaining
          else f"Check FAILED for: {', '.join(remaining)}")
    return 0 if not remaining else 2


if __name__ == "__main__":
    sys.exit(main())
