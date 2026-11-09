"""Tests for the owner role: only the owner account can use the owner pages and API.
Run from the repository root with: pytest"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app import app  # noqa: E402

# On a laptop (and in these tests) the app creates this local test owner.
OWNER_EMAIL, OWNER_PASSWORD = "owner@stockwise.test", "owner-pass-123"


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def sign_in(client, email=OWNER_EMAIL, password=OWNER_PASSWORD):
    return client.post("/owner/login", data={"email": email, "password": password})


def test_dashboard_needs_owner_sign_in(client):
    response = client.get("/owner")
    assert response.status_code == 302
    assert "/owner/login" in response.headers["Location"]


def test_wrong_password_is_rejected(client):
    assert sign_in(client, password="wrong-password").status_code == 401
    assert client.get("/owner").status_code == 302


def test_owner_goes_straight_to_dashboard(client):
    response = sign_in(client)
    assert response.headers["Location"].endswith("/owner")
    page = client.get("/owner")
    assert page.status_code == 200
    assert b"Owner dashboard" in page.data


def test_owner_can_record_a_sale(client):
    sign_in(client)
    response = client.post("/owner/sale", data={"sku": "EL-1001", "quantity": 1}, follow_redirects=True)
    assert b"Sale recorded" in response.data


def test_restock_blocked_without_sign_in(client):
    response = client.post("/owner/restock", data={"sku": "EL-1001", "quantity": 5})
    assert response.status_code == 302
    assert "/owner/login" in response.headers["Location"]


def test_sign_out_locks_dashboard_again(client):
    sign_in(client)
    client.post("/logout")
    assert client.get("/owner").status_code == 302


def test_owner_sign_in_page_is_separate(client):
    response = client.get("/owner/login")
    assert response.status_code == 200
    assert b"Owner sign-in" in response.data


def test_customer_account_cannot_use_owner_sign_in(client):
    client.post("/signup", data={"name": "Cara", "email": "cara@example.com", "password": "cara-pass-1"})
    client.post("/logout")
    response = sign_in(client, "cara@example.com", "cara-pass-1")
    assert response.status_code == 401
    assert client.get("/owner").status_code == 302


def test_owner_is_not_signed_in_on_customer_page(client):
    response = client.post("/login", data={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert "/owner/login" in response.headers["Location"]
    assert client.get("/api/me").status_code == 401


def test_owner_api_checks_the_token(client):
    assert client.get("/api/owner/low-stock").status_code == 401
    sign_in(client)
    response = client.get("/api/owner/low-stock")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_public_pages_have_no_owner_link(client):
    for page in ("/", "/login", "/signup"):
        assert b'href="/owner' not in client.get(page).data
    client.post("/signup", data={"name": "Dan", "email": "dan@example.com", "password": "dan-pass-12"})
    assert b'href="/owner' not in client.get("/shop").data
