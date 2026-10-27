"""Tests for account storage, in memory and in MongoDB (mongomock).
Run from the repository root with: pytest"""

import sys
from pathlib import Path

import mongomock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from accounts import AccountError, MemoryAccounts, MongoAccounts  # noqa: E402


@pytest.fixture(params=["memory", "mongo"])
def accounts(request):
    if request.param == "memory":
        return MemoryAccounts()
    return MongoAccounts(mongomock.MongoClient()["stockwise"]["users"])


def test_sign_up_then_sign_in(accounts):
    accounts.sign_up("Ada", "Ada@Example.com", "password123")
    user = accounts.authenticate("ada@example.com", "password123")
    assert user == {"email": "ada@example.com", "name": "Ada", "role": "customer"}


def test_wrong_password_and_unknown_email_fail(accounts):
    accounts.sign_up("Ada", "ada@example.com", "password123")
    assert accounts.authenticate("ada@example.com", "wrong-pass") is None
    assert accounts.authenticate("nobody@example.com", "password123") is None


def test_duplicate_email_is_refused(accounts):
    accounts.sign_up("Ada", "ada@example.com", "password123")
    with pytest.raises(AccountError):
        accounts.sign_up("Ada again", "ADA@example.com", "password456")


def test_owner_account_from_settings(accounts):
    assert accounts.ensure_owner("michael@example.com", "owner-secret-1")
    assert accounts.authenticate("michael@example.com", "owner-secret-1")["role"] == "owner"
    # A new password in Key Vault replaces the old one at the next start.
    accounts.ensure_owner("michael@example.com", "owner-secret-2")
    assert accounts.authenticate("michael@example.com", "owner-secret-1") is None
    assert accounts.authenticate("michael@example.com", "owner-secret-2")["role"] == "owner"


def test_no_owner_without_settings(accounts):
    assert accounts.ensure_owner("", "") is False


def test_password_is_stored_only_as_a_hash():
    collection = mongomock.MongoClient()["stockwise"]["users"]
    MongoAccounts(collection).sign_up("Ada", "ada@example.com", "password123")
    stored = collection.find_one({"email": "ada@example.com"})
    assert "password" not in stored
    assert "password123" not in stored["password_hash"]
    assert stored["password_hash"].startswith(("scrypt:", "pbkdf2:"))
