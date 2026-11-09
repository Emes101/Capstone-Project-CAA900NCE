"""Tests for scripts/backup_restore.py against mongomock (an in-memory MongoDB).
Run from the repository root with: pytest"""

import json
import stat
import sys
from pathlib import Path

import mongomock
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

import backup_restore  # noqa: E402
from accounts import MongoAccounts  # noqa: E402
from mongo_inventory import MongoInventory  # noqa: E402


@pytest.fixture
def db():
    database = mongomock.MongoClient()["stockwise"]
    MongoInventory(database["products"]).seed_if_empty()
    MongoAccounts(database["users"]).sign_up("Ana", "ana@example.com", "password123")
    return database


def run(db, *args):
    return backup_restore.main(list(args), db=db)


def test_backup_writes_both_collections(db, tmp_path, capsys):
    assert run(db, "backup", "--folder", str(tmp_path)) == 0
    files = list(tmp_path.glob("stockwise-*.json"))
    assert len(files) == 1
    content = json.loads(files[0].read_text())
    assert len(content["collections"]["products"]) == 12
    assert content["collections"]["users"][0]["email"] == "ana@example.com"
    assert "_id" not in content["collections"]["products"][0]
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert "products: 12 documents" in capsys.readouterr().out


def test_restore_brings_back_changed_and_deleted_data(db, tmp_path, capsys):
    run(db, "backup", "--folder", str(tmp_path))
    file = str(next(tmp_path.glob("*.json")))
    inventory = MongoInventory(db["products"])
    inventory.record_sale("EL-1001", 5)                      # 18 -> 13
    db["products"].delete_one({"sku": "OS-3001"})            # "lost" a product
    run(db, "verify", file)
    assert "2 product(s) differ" in capsys.readouterr().out
    assert run(db, "restore", file, "--yes") == 0
    assert inventory.get("EL-1001")["stock"] == 18
    assert inventory.get("OS-3001")["name"] == "Printer paper, A4, 500 sheets"
    out = capsys.readouterr().out
    assert "EL-1001, OS-3001" in out and "the products now match the backup" in out


def test_restore_needs_confirmation(db, tmp_path):
    run(db, "backup", "--folder", str(tmp_path))
    file = str(next(tmp_path.glob("*.json")))
    MongoInventory(db["products"]).record_sale("EL-1001", 5)
    assert run(db, "restore", file) == 1
    assert MongoInventory(db["products"]).get("EL-1001")["stock"] == 13


def test_users_are_restored_only_when_asked(db, tmp_path):
    run(db, "backup", "--folder", str(tmp_path))
    file = str(next(tmp_path.glob("*.json")))
    db["users"].delete_many({})
    run(db, "restore", file, "--yes")
    assert db["users"].count_documents({}) == 0
    run(db, "restore", file, "--yes", "--include-users")
    assert MongoAccounts(db["users"]).authenticate("ana@example.com", "password123")["name"] == "Ana"
