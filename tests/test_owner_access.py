"""Tests for the owner access code. Run from the repository root with: pytest"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
os.environ.setdefault("OWNER_ACCESS_CODE", "ACS730")

from app import app  # noqa: E402


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def sign_in(client, code="ACS730"):
    return client.post("/owner/login", data={"code": code})


def test_dashboard_needs_the_code(client):
    response = client.get("/owner")
    assert response.status_code == 302
    assert "/owner/login" in response.headers["Location"]


def test_wrong_code_is_rejected(client):
    sign_in(client, "WRONG")
    assert client.get("/owner").status_code == 302


def test_correct_code_opens_dashboard(client):
    assert sign_in(client).status_code == 302
    response = client.get("/owner")
    assert response.status_code == 200
    assert b"Owner dashboard" in response.data


def test_restock_blocked_without_code(client):
    response = client.post("/owner/restock", data={"sku": "EL-1001", "quantity": 5})
    assert response.status_code == 302
    assert "/owner/login" in response.headers["Location"]


def test_sign_out_locks_dashboard_again(client):
    sign_in(client)
    client.post("/owner/logout")
    assert client.get("/owner").status_code == 302


def test_customers_see_units_in_stock(client):
    response = client.get("/")
    assert b"units in stock" in response.data or b"unit in stock" in response.data


def test_customer_page_has_no_owner_link(client):
    response = client.get("/")
    assert b'href="/owner' not in response.data
