"""StockWise Solutions web app (Flask).

One app serves both views and a small API:
  /              customer view: search products and see how many are in stock
  /owner/login   owner enters the access code
  /owner         owner dashboard: stock levels, low-stock list, sales and restocks
  /api/...       JSON endpoints used now for testing and later by the pages

Stock is saved in Azure Cosmos DB for MongoDB when MONGODB_URI is set (on Azure),
and kept in memory from the sample file otherwise (on a laptop). The access code is
a simple first step; full owner sign-in (Entra External ID) comes next.
"""

import hmac
import os
from functools import wraps

from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   session, url_for)

from inventory import STATUS_LABELS, Inventory, StockError

app = Flask(__name__)

# The secret key signs the session cookie that remembers the owner is signed in.
# It is read from an App Service setting, never written in the code.
# If none is set (for example on your laptop), a random one is made at start-up.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)

# The owner access code. On Azure it is read from the OWNER_ACCESS_CODE app
# setting. The default below is only for running on a laptop.
OWNER_ACCESS_CODE = os.environ.get("OWNER_ACCESS_CODE", "ACS730")

# On Azure, MONGODB_URI is set by infra/main.bicep, so stock is saved in the
# database. On a laptop it is not set, so the app uses the sample file in memory.
MONGODB_URI = os.environ.get("MONGODB_URI")
if MONGODB_URI:
    from mongo_inventory import MongoInventory
    inventory = MongoInventory.connect(MONGODB_URI, os.environ.get("MONGODB_DB", "stockwise"))
else:
    inventory = Inventory.from_file()


@app.context_processor
def shared_values():
    # Values every page template can use.
    return {
        "status_of": Inventory.status,
        "labels": STATUS_LABELS,
        "is_owner": session.get("is_owner", False),
    }


def owner_required(view):
    """Send anyone without the access code to the code page."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_owner"):
            return redirect(url_for("owner_login"))
        return view(*args, **kwargs)
    return wrapper


# ---------- Customer view ----------

@app.get("/")
def customer():
    query = request.args.get("q", "")
    products = [inventory.public_view(p) for p in inventory.search(query)]
    return render_template("customer.html", products=products, query=query)


# ---------- Owner access code ----------

@app.route("/owner/login", methods=["GET", "POST"])
def owner_login():
    if request.method == "POST":
        entered = request.form.get("code", "").strip()
        # compare_digest compares safely, without revealing how close a guess was.
        if hmac.compare_digest(entered.upper(), OWNER_ACCESS_CODE.upper()):
            session.clear()
            session["is_owner"] = True
            return redirect(url_for("owner"))
        flash("That code is not correct. Please try again.", "error")
    return render_template("owner_login.html")


@app.post("/owner/logout")
def owner_logout():
    session.clear()
    flash("You have signed out of the owner dashboard.", "ok")
    return redirect(url_for("customer"))


# ---------- Owner dashboard (code required) ----------

@app.get("/owner")
@owner_required
def owner():
    products = inventory.all()
    summary = {
        "total": len(products),
        "units": sum(p["stock"] for p in products),
        "low": sum(1 for p in products if Inventory.status(p) == "low"),
        "out": sum(1 for p in products if Inventory.status(p) == "out"),
    }
    return render_template(
        "owner.html",
        products=products,
        low_stock=inventory.low_stock(),
        summary=summary,
    )


@app.post("/owner/sale")
@owner_required
def owner_sale():
    try:
        product = inventory.record_sale(request.form["sku"], request.form["quantity"])
        flash(f"Sale recorded. {product['name']}: {product['stock']} left.", "ok")
    except (StockError, KeyError) as error:
        flash(str(error), "error")
    return redirect(url_for("owner"))


@app.post("/owner/restock")
@owner_required
def owner_restock():
    try:
        product = inventory.restock(request.form["sku"], request.form["quantity"])
        flash(f"Restock recorded. {product['name']}: {product['stock']} in stock.", "ok")
    except (StockError, KeyError) as error:
        flash(str(error), "error")
    return redirect(url_for("owner"))


# ---------- API ----------

@app.get("/api/health")
def health():
    # Used by monitoring and by us to check the app is running.
    return jsonify(status="ok", storage="database" if MONGODB_URI else "memory")


@app.get("/api/products")
def api_products():
    # Public endpoint: what customers see (name, price, units in stock, status).
    return jsonify([inventory.public_view(p) for p in inventory.search(request.args.get("q"))])


if __name__ == "__main__":
    # Local run only. On Azure, gunicorn starts the app (see infra/main.bicep).
    app.run(debug=True, port=5001)
