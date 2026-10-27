"""Tests for the landing page and customer sign-up and sign-in.
Run from the repository root with: pytest"""

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app import app  # noqa: E402


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def new_email():
    return f"customer-{uuid.uuid4().hex[:8]}@example.com"


def sign_up(client, email, password="customer-pass-1", name="Test Customer"):
    return client.post("/signup", data={"name": name, "email": email, "password": password})


def test_customer_can_sign_up_and_is_signed_in(client):
    email = new_email()
    response = sign_up(client, email)
    assert response.status_code == 302
    me = client.get("/api/me").get_json()
    assert me == {"email": email, "name": "Test Customer", "role": "customer"}


def test_customer_can_sign_out_and_sign_in_again(client):
    email = new_email()
    sign_up(client, email)
    client.post("/logout")
    assert client.get("/api/me").status_code == 401
    response = client.post("/login", data={"email": email.upper(), "password": "customer-pass-1"})
    assert response.status_code == 302
    assert client.get("/api/me").get_json()["role"] == "customer"


def test_customer_cannot_open_owner_area(client):
    sign_up(client, new_email())
    response = client.get("/owner")
    assert response.status_code == 403
    assert b"does not have the owner role" in response.data


def test_customer_cannot_record_a_sale(client):
    sign_up(client, new_email())
    response = client.post("/owner/sale", data={"sku": "EL-1001", "quantity": 1})
    assert response.status_code == 403


def test_customer_cannot_call_owner_api(client):
    sign_up(client, new_email())
    assert client.get("/api/owner/low-stock").status_code == 403


def test_nobody_can_sign_up_with_the_owner_email(client):
    response = sign_up(client, "owner@stockwise.test")
    assert response.status_code == 400
    assert b"already exists" in response.data


def test_short_password_is_refused(client):
    response = sign_up(client, new_email(), password="short")
    assert response.status_code == 400
    assert b"at least 8 characters" in response.data


def test_login_does_not_redirect_to_other_sites(client):
    email = new_email()
    sign_up(client, email)
    client.post("/logout")
    response = client.post("/login", data={"email": email, "password": "customer-pass-1",
                                           "next": "//evil.example.com"})
    assert response.headers["Location"] == "/shop"


def test_api_me_never_shows_the_password_hash(client):
    sign_up(client, new_email())
    assert "password_hash" not in client.get("/api/me").get_json()


def test_landing_page_is_public_and_shows_no_products(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'href="/login"' in response.data and b'href="/signup"' in response.data
    assert b"USB-C charger, 30 W" not in response.data  # a product name from the sample data


def test_products_need_an_account(client):
    response = client.get("/shop")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert client.get("/api/products").status_code == 401


def test_signed_in_customer_sees_products_and_units(client):
    response = sign_up(client, new_email())
    assert response.headers["Location"] == "/shop"
    page = client.get("/shop?q=usb")
    assert page.status_code == 200
    assert b"in stock" in page.data
    assert client.get("/api/products").status_code == 200


def test_sign_in_returns_to_the_page_asked_for(client):
    email = new_email()
    sign_up(client, email)
    client.post("/logout")
    response = client.post("/login", data={"email": email, "password": "customer-pass-1",
                                           "next": "/shop?q=paper"})
    assert response.headers["Location"] == "/shop?q=paper"
