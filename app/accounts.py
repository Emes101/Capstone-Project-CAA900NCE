"""User accounts for StockWise.

- Customers create their own account (name, email, password) on /signup.
- The owner account is created when the app starts, from the OWNER_EMAIL and
  OWNER_PASSWORD settings (on Azure they come from Key Vault).
- Passwords are never stored. We store only a salted hash (Werkzeug, scrypt),
  so even we cannot read a password.

MemoryAccounts keeps accounts in memory (laptop and tests). MongoAccounts keeps
them in the "users" collection in Azure Cosmos DB for MongoDB.
"""

import re
import threading

from werkzeug.security import check_password_hash, generate_password_hash

OWNER = "owner"
CUSTOMER = "customer"
MIN_PASSWORD_LENGTH = 8
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Checked when an email is unknown, so a wrong email takes as long as a wrong
# password and nobody can find out which emails have accounts.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


class AccountError(Exception):
    """A problem the user can fix, shown on the page."""


def normalize_email(email):
    return (email or "").strip().lower()


def public(user):
    """The parts of an account that are safe to keep in the session."""
    return {"email": user["email"], "name": user["name"], "role": user["role"]}


class _Accounts:
    def sign_up(self, name, email, password):
        name = (name or "").strip()
        email = normalize_email(email)
        password = password or ""
        if not name or len(name) > 80:
            raise AccountError("Please enter your name (up to 80 characters).")
        if not EMAIL_PATTERN.match(email) or len(email) > 254:
            raise AccountError("Please enter a valid email address.")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise AccountError(f"Your password must have at least {MIN_PASSWORD_LENGTH} characters.")
        user = {
            "email": email,
            "name": name,
            "role": CUSTOMER,  # nobody can sign up as the owner
            "password_hash": generate_password_hash(password),
        }
        if not self._insert(user):
            raise AccountError("An account with this email already exists. Please sign in.")
        return public(user)

    def authenticate(self, email, password):
        """Return the account if the email and password match, otherwise None."""
        user = self._find(normalize_email(email))
        if user is None:
            check_password_hash(_DUMMY_HASH, password or "")
            return None
        if not check_password_hash(user["password_hash"], password or ""):
            return None
        return public(user)

    def ensure_owner(self, email, password, name="Michael Chen"):
        """Create or update the owner account from the app settings."""
        email = normalize_email(email)
        if not email or not password:
            return False
        self._save_owner({
            "email": email,
            "name": name,
            "role": OWNER,
            "password_hash": generate_password_hash(password),
        })
        return True


class MemoryAccounts(_Accounts):
    def __init__(self):
        self._users = {}
        self._lock = threading.Lock()

    def _find(self, email):
        return self._users.get(email)

    def _insert(self, user):
        with self._lock:
            if user["email"] in self._users:
                return False
            self._users[user["email"]] = dict(user)
            return True

    def _save_owner(self, user):
        with self._lock:
            self._users[user["email"]] = dict(user)


class MongoAccounts(_Accounts):
    def __init__(self, collection):
        from pymongo.errors import DuplicateKeyError
        self._duplicate = DuplicateKeyError
        self.users = collection
        if not collection.count_documents({}, limit=1):
            try:
                # Cosmos DB only allows a unique index on an empty collection.
                collection.create_index("email", unique=True)
            except Exception:
                pass  # index exists already, or the service refused; _insert still checks

    def _find(self, email):
        return self.users.find_one({"email": email}, {"_id": 0})

    def _insert(self, user):
        if self._find(user["email"]) is not None:
            return False
        try:
            self.users.insert_one(dict(user))
        except self._duplicate:
            return False
        return True

    def _save_owner(self, user):
        self.users.update_one({"email": user["email"]}, {"$set": user}, upsert=True)
