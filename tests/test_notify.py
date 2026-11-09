"""Tests for the low-stock email alert. No real email is sent: a fake sender records it.
Run from the repository root with: pytest"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from inventory import Inventory  # noqa: E402
from notify import LowStockNotifier, crossed_low_stock, message_for  # noqa: E402


def product(stock, level=5):
    return {"sku": "EL-1002", "name": "Power bank", "stock": stock, "reorder_level": level,
            "supplier": "Northline"}


@pytest.mark.parametrize("before,after,expected", [
    (8, 6, False),   # still above the reorder level
    (6, 5, True),    # reached the reorder level
    (9, 2, True),    # jumped below it
    (5, 4, False),   # was already low: no second email
    (3, 0, True),    # ran out
    (0, 0, False),   # nothing changed
])
def test_when_an_alert_is_due(before, after, expected):
    assert crossed_low_stock(product(after), before) is expected


def test_message_text():
    subject, body = message_for(product(2))
    assert subject == "Low stock: Power bank (2 left)" and "Northline" in body
    assert message_for(product(0))[0] == "Out of stock: Power bank"


def test_sends_one_email_with_fake_sender():
    sent = []
    notifier = LowStockNotifier(recipient="owner@example.com", send=lambda *a: sent.append(a))
    assert notifier.enabled
    assert notifier.stock_changed(product(5), 7) is True
    assert notifier.stock_changed(product(4), 5) is False
    assert sent == [("owner@example.com", "Low stock: Power bank (5 left)", message_for(product(5))[1])]


def test_off_without_settings(monkeypatch):
    for name in ("ACS_CONNECTION_STRING", "ACS_SENDER_ADDRESS", "LOW_STOCK_EMAIL_TO", "OWNER_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    notifier = LowStockNotifier.from_environment()
    assert notifier.enabled is False
    assert notifier.stock_changed(product(5), 7) is False  # logged only, no error


def test_owner_email_is_the_default_recipient(monkeypatch):
    monkeypatch.setenv("ACS_CONNECTION_STRING", "endpoint=https://x.communication.azure.com/;accesskey=abc")
    monkeypatch.setenv("ACS_SENDER_ADDRESS", "DoNotReply@example.azurecomm.net")
    monkeypatch.delenv("LOW_STOCK_EMAIL_TO", raising=False)
    monkeypatch.setenv("OWNER_EMAIL", "michael@example.com")
    notifier = LowStockNotifier.from_environment()
    assert notifier.enabled and notifier.recipient == "michael@example.com"


def test_sale_on_the_dashboard_triggers_the_alert(monkeypatch):
    import app as app_module
    sent = []
    monkeypatch.setattr(app_module, "inventory", Inventory.from_file())
    monkeypatch.setattr(app_module, "notifier",
                        LowStockNotifier(recipient="owner@example.com", send=lambda *a: sent.append(a)))
    with app_module.app.test_client() as client:
        client.post("/owner/login", data={"email": "owner@stockwise.test", "password": "owner-pass-123"})
        client.post("/owner/sale", data={"sku": "EL-1001", "quantity": 12})  # 18 -> 6, reorder level 6
        client.post("/owner/sale", data={"sku": "EL-1001", "quantity": 1})   # already low: no second email
    assert [s[1] for s in sent] == ["Low stock: USB-C charger, 30 W (6 left)"]


def test_reservation_triggers_the_alert(monkeypatch):
    import app as app_module
    sent = []
    monkeypatch.setattr(app_module, "inventory", Inventory.from_file())
    monkeypatch.setattr(app_module, "notifier",
                        LowStockNotifier(recipient="owner@example.com", send=lambda *a: sent.append(a)))
    with app_module.app.test_client() as client:
        client.post("/signup", data={"name": "Dee", "email": "dee-notify@example.com", "password": "dee-pass-123"})
        client.post("/shop/reserve", data={"sku": "CP-4003", "quantity": 2})  # webcam 6 -> 4, level 4
    assert [s[1] for s in sent] == ["Low stock: HD webcam, 1080p (4 left)"]
