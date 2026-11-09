"""Tests for reservations: the stock rules (in memory and in MongoDB) and the pages and API.
Run from the repository root with: pytest"""

import sys
import uuid
from pathlib import Path

import mongomock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from inventory import CANCELLED, PICKED_UP, Inventory, StockError  # noqa: E402
from mongo_inventory import MongoInventory  # noqa: E402

ANA, BEN = "ana@example.com", "ben@example.com"


@pytest.fixture(params=["memory", "mongo"])
def inv(request):
    if request.param == "memory":
        return Inventory.from_file()
    collection = mongomock.MongoClient()["stockwise"]["products"]
    inventory = MongoInventory(collection)
    inventory.seed_if_empty()
    inventory.ensure_indexes()
    return inventory


# ---------- Rules ----------

def test_reserving_takes_units_out_of_stock(inv):
    before = inv.get("EL-1001")["stock"]
    product, r = inv.reserve("EL-1001", 2, ANA, "Ana")
    assert product["stock"] == before - 2
    assert inv.get("EL-1001")["stock"] == before - 2
    assert r["status"] == "reserved" and r["quantity"] == 2 and r["product_name"] == "USB-C charger, 30 W"


def test_cannot_reserve_more_than_in_stock(inv):
    stock = inv.get("CP-4002")["stock"]  # mechanical keyboard: 3
    with pytest.raises(StockError):
        inv.reserve("CP-4002", stock + 1, ANA, "Ana")
    assert inv.get("CP-4002")["stock"] == stock


def test_cannot_reserve_out_of_stock_item(inv):
    with pytest.raises(StockError):
        inv.reserve("MA-2002", 1, ANA, "Ana")  # 0 in stock


def test_last_units_cannot_be_reserved_twice(inv):
    stock = inv.get("CP-4002")["stock"]
    inv.reserve("CP-4002", stock, ANA, "Ana")
    with pytest.raises(StockError):
        inv.reserve("CP-4002", 1, BEN, "Ben")
    assert inv.get("CP-4002")["stock"] == 0


@pytest.mark.parametrize("bad", [0, -1, "abc", 6])
def test_bad_quantities_are_refused(inv, bad):
    with pytest.raises(StockError):
        inv.reserve("EL-1001", bad, ANA, "Ana")


def test_unknown_product(inv):
    with pytest.raises(StockError):
        inv.reserve("NOPE-1", 1, ANA, "Ana")


def test_cancel_gives_units_back_once(inv):
    before = inv.get("EL-1001")["stock"]
    _, r = inv.reserve("EL-1001", 2, ANA, "Ana")
    product, changed = inv.set_reservation_status(r["id"], CANCELLED)
    assert product["stock"] == before and changed["status"] == "cancelled"
    with pytest.raises(StockError):
        inv.set_reservation_status(r["id"], CANCELLED)  # not twice
    assert inv.get("EL-1001")["stock"] == before


def test_pickup_keeps_units_sold(inv):
    before = inv.get("EL-1001")["stock"]
    _, r = inv.reserve("EL-1001", 1, ANA, "Ana")
    product, changed = inv.set_reservation_status(r["id"], PICKED_UP)
    assert product["stock"] == before - 1 and changed["status_label"] == "Picked up"
    with pytest.raises(StockError):
        inv.set_reservation_status(r["id"], CANCELLED)  # finished reservations cannot change


def test_customers_only_see_and_cancel_their_own(inv):
    _, r = inv.reserve("EL-1001", 1, ANA, "Ana")
    inv.reserve("OS-3001", 1, BEN, "Ben")
    assert [x["id"] for x in inv.reservations(customer_email=ANA)] == [r["id"]]
    with pytest.raises(StockError):
        inv.set_reservation_status(r["id"], CANCELLED, customer_email=BEN)
    inv.set_reservation_status(r["id"], CANCELLED, customer_email=ANA)


def test_owner_lists_waiting_reservations(inv):
    _, a = inv.reserve("EL-1001", 1, ANA, "Ana")
    _, b = inv.reserve("OS-3001", 1, BEN, "Ben")
    inv.set_reservation_status(b["id"], PICKED_UP)
    assert [x["id"] for x in inv.reservations(status="reserved")] == [a["id"]]
    assert len(inv.reservations()) == 2


def test_unknown_reservation(inv):
    with pytest.raises(StockError):
        inv.set_reservation_status("does-not-exist", CANCELLED)


def test_customer_view_never_shows_reservations(inv):
    inv.reserve("EL-1001", 1, ANA, "Ana")
    assert "reservations" not in inv.public_view(inv.get("EL-1001"))


# ---------- Pages and API ----------

from app import app  # noqa: E402

app_module = sys.modules["app"]


@pytest.fixture
def client(monkeypatch):
    # A fresh in-memory shop for every test, so tests do not affect each other.
    monkeypatch.setattr(app_module, "inventory", Inventory.from_file())
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def customer(client, name="Cara"):
    email = f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com"
    client.post("/signup", data={"name": name, "email": email, "password": "customer-pass-1"})
    return email


def owner(client):
    client.post("/owner/login", data={"email": "owner@stockwise.test", "password": "owner-pass-123"})


def test_shop_shows_reserve_button(client):
    customer(client)
    page = client.get("/shop").data
    assert b"Reserve for pickup" in page and b'href="/reservations"' in page


def test_customer_reserves_and_sees_it(client):
    customer(client)
    response = client.post("/shop/reserve", data={"sku": "EL-1001", "quantity": 2})
    assert response.headers["Location"].endswith("/reservations")
    page = client.get("/reservations").data
    assert b"USB-C charger, 30 W" in page and b"Waiting for pickup" in page
    assert app_module.inventory.get("EL-1001")["stock"] == 16


def test_reserving_too_many_shows_a_message(client):
    customer(client)
    response = client.post("/shop/reserve", data={"sku": "MA-2002", "quantity": 1}, follow_redirects=True)
    assert b"cannot reserve" in response.data


def test_reserve_needs_sign_in(client):
    response = client.post("/shop/reserve", data={"sku": "EL-1001", "quantity": 1})
    assert "/login" in response.headers["Location"]
    assert app_module.inventory.get("EL-1001")["stock"] == 18


def test_customer_cancels_own_reservation(client):
    customer(client)
    client.post("/shop/reserve", data={"sku": "EL-1001", "quantity": 1})
    rid = app_module.inventory.reservations()[0]["id"]
    client.post(f"/reservations/{rid}/cancel")
    assert app_module.inventory.get("EL-1001")["stock"] == 18


def test_customer_cannot_cancel_someone_elses(client):
    customer(client, "Ana")
    client.post("/shop/reserve", data={"sku": "EL-1001", "quantity": 1})
    rid = app_module.inventory.reservations()[0]["id"]
    client.post("/logout")
    customer(client, "Ben")
    response = client.post(f"/reservations/{rid}/cancel", follow_redirects=True)
    assert b"Reservation not found" in response.data
    assert app_module.inventory.get("EL-1001")["stock"] == 17


def test_owner_sees_and_completes_reservations(client):
    customer(client, "Ana")
    client.post("/shop/reserve", data={"sku": "EL-1001", "quantity": 1})
    rid = app_module.inventory.reservations()[0]["id"]
    client.post("/logout")
    owner(client)
    page = client.get("/owner").data
    assert b"Reservations waiting for pickup" in page and b"Ana" in page
    client.post(f"/owner/reservations/{rid}/pickup")
    assert app_module.inventory.reservations()[0]["status"] == "picked_up"
    assert app_module.inventory.get("EL-1001")["stock"] == 17


def test_owner_cancel_returns_stock(client):
    customer(client)
    client.post("/shop/reserve", data={"sku": "EL-1001", "quantity": 3})
    rid = app_module.inventory.reservations()[0]["id"]
    client.post("/logout")
    owner(client)
    client.post(f"/owner/reservations/{rid}/cancel")
    assert app_module.inventory.get("EL-1001")["stock"] == 18


def test_customer_cannot_use_owner_reservation_actions(client):
    customer(client)
    client.post("/shop/reserve", data={"sku": "EL-1001", "quantity": 1})
    rid = app_module.inventory.reservations()[0]["id"]
    assert client.post(f"/owner/reservations/{rid}/pickup").status_code == 403


def test_owner_cannot_reserve(client):
    owner(client)
    client.post("/shop/reserve", data={"sku": "EL-1001", "quantity": 1})
    assert app_module.inventory.reservations() == []


def test_api_create_and_list_reservations(client):
    assert client.post("/api/reservations", json={"sku": "EL-1001"}).status_code == 401
    customer(client)
    response = client.post("/api/reservations", json={"sku": "EL-1001", "quantity": 2})
    assert response.status_code == 201
    created = response.get_json()
    assert created["quantity"] == 2 and created["status"] == "reserved"
    assert [r["id"] for r in client.get("/api/reservations").get_json()] == [created["id"]]
    assert client.post("/api/reservations", json={"sku": "MA-2002"}).status_code == 409


def test_api_owner_reservations(client):
    customer(client)
    client.post("/api/reservations", json={"sku": "EL-1001"})
    assert client.get("/api/owner/reservations").status_code == 403
    client.post("/logout")
    owner(client)
    data = client.get("/api/owner/reservations?status=reserved").get_json()
    assert len(data) == 1 and data[0]["sku"] == "EL-1001"
