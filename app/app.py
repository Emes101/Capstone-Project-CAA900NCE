"""StockWise Solutions web app (Flask).

One app serves both views and a small API:
  /            customer view: search products and see availability
  /owner       owner view: stock levels, low-stock list, record sales and restocks
  /api/...     JSON endpoints used now for testing and later by the pages

Sample data only. Owner sign-in (Entra External ID) and the Azure SQL database
are added in Progress Submission 3.
"""

import os

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from inventory import STATUS_LABELS, Inventory, StockError

app = Flask(__name__)

# The secret key signs the short messages shown after a form is sent.
# It is read from an App Service setting, never written in the code.
# If none is set (for example on your laptop), a random one is made at start-up.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)

inventory = Inventory.from_file()


@app.context_processor
def shared_values():
    # Values every page template can use.
    return {"status_of": Inventory.status, "labels": STATUS_LABELS}


# ---------- Customer view ----------

@app.get("/")
def customer():
    query = request.args.get("q", "")
    products = [inventory.public_view(p) for p in inventory.search(query)]
    return render_template("customer.html", products=products, query=query)


# ---------- Owner view ----------

@app.get("/owner")
def owner():
    products = inventory.all()
    summary = {
        "total": len(products),
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
def owner_sale():
    try:
        product = inventory.record_sale(request.form["sku"], request.form["quantity"])
        flash(f"Sale recorded. {product['name']}: {product['stock']} left.", "ok")
    except (StockError, KeyError) as error:
        flash(str(error), "error")
    return redirect(url_for("owner"))


@app.post("/owner/restock")
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
    return jsonify(status="ok")


@app.get("/api/products")
def api_products():
    # Public endpoint: availability only, no exact stock counts.
    return jsonify([inventory.public_view(p) for p in inventory.search(request.args.get("q"))])


if __name__ == "__main__":
    # Local run only. On Azure, gunicorn starts the app (see infra/main.bicep).
    app.run(debug=True)
