"""Low-stock email alert for the owner.

When a sale or a reservation brings a product down to its reorder level (or to
zero), the app emails the owner once, through Azure Communication Services Email.

The email is optional. It is switched on only when these app settings exist:
  ACS_CONNECTION_STRING  Communication Services connection string (from Key Vault)
  ACS_SENDER_ADDRESS     the "MailFrom" address of the email domain,
                         e.g. DoNotReply@xxxxxxxx.azurecomm.net
  LOW_STOCK_EMAIL_TO     who receives it (default: the owner's email)
Without them, the app only writes the alert to its log, and the low-stock list
on the owner dashboard still shows every item to reorder.
"""

import logging
import os
import threading

log = logging.getLogger("stockwise.notify")


def crossed_low_stock(product, stock_before):
    """True when this change took the product to its reorder level or to zero."""
    level, after = product["reorder_level"], product["stock"]
    reached_level = stock_before > level >= after
    ran_out = stock_before > 0 and after <= 0
    return reached_level or ran_out


def message_for(product):
    if product["stock"] <= 0:
        subject = f"Out of stock: {product['name']}"
        first = f"{product['name']} ({product['sku']}) is now out of stock."
    else:
        subject = f"Low stock: {product['name']} ({product['stock']} left)"
        first = (f"{product['name']} ({product['sku']}) is down to {product['stock']} "
                 f"units. Its reorder level is {product['reorder_level']}.")
    body = (f"{first}\n\nSupplier: {product.get('supplier', 'not recorded')}\n\n"
            "Open the owner dashboard to restock it.\n\n— StockWise")
    return subject, body


class LowStockNotifier:
    def __init__(self, connection_string=None, sender=None, recipient=None, send=None):
        self.recipient = recipient
        self._connection_string = connection_string
        self._sender = sender
        self._send = send  # tests pass a fake; None = send with Azure
        self.enabled = bool(recipient and (send or (connection_string and sender)))

    @classmethod
    def from_environment(cls):
        return cls(
            connection_string=os.environ.get("ACS_CONNECTION_STRING"),
            sender=os.environ.get("ACS_SENDER_ADDRESS"),
            recipient=os.environ.get("LOW_STOCK_EMAIL_TO") or os.environ.get("OWNER_EMAIL"),
        )

    def stock_changed(self, product, stock_before):
        """Call after any change that lowers stock. Returns True if an email was sent."""
        if not crossed_low_stock(product, stock_before):
            return False
        subject, body = message_for(product)
        if not self.enabled:
            log.warning("Low-stock alert (email is not set up): %s", subject)
            return False
        if self._send:
            self._send(self.recipient, subject, body)
        else:
            # Send in the background so the owner's page is not slowed down.
            threading.Thread(target=self._send_with_azure, args=(subject, body), daemon=True).start()
        return True

    def _send_with_azure(self, subject, body):
        try:
            from azure.communication.email import EmailClient
            client = EmailClient.from_connection_string(self._connection_string)
            poller = client.begin_send({
                "senderAddress": self._sender,
                "recipients": {"to": [{"address": self.recipient}]},
                "content": {"subject": subject, "plainText": body},
            })
            poller.result()
            log.info("Low-stock email sent: %s", subject)
        except Exception:
            # Never break a sale because an email failed; the error goes to App Insights.
            log.exception("Low-stock email failed: %s", subject)
