"""StockWise Solutions web app (Flask).

One app serves both views and a small API:
  /                customer view: search products and see how many are in stock
  /signup          customers create an account
  /login, /logout  sign in and out (customers and the owner use the same page)
  /owner           owner dashboard: stock levels, low-stock list, sales and restocks
  /api/...         JSON endpoints

Sign-in: accounts are stored in the database with a salted password hash. After
sign-in, Flask gives the browser a signed session cookie (the token). Every owner
page and owner API checks that token for the "owner" role.

Stock and accounts are saved in Azure Cosmos DB for MongoDB when MONGODB_URI is
set (on Azure), and kept in memory otherwise (on a laptop).
"""

import os
from datetime import timedelta
from functools import wraps

# Application Insights: on Azure the connection string is an app setting, so
# requests, errors and logs are sent to Azure Monitor. On a laptop it is not set.
if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(enable_live_metrics=True)

from flask import (Flask, abort, flash, jsonify, redirect, render_template,  # noqa: E402
                   request, session, url_for)

from accounts import OWNER, AccountError, MemoryAccounts, MongoAccounts  # noqa: E402
from inventory import STATUS_LABELS, Inventory, StockError  # noqa: E402

ON_AZURE = bool(os.environ.get("WEBSITE_SITE_NAME"))  # set by App Service

app = Flask(__name__)

# The secret key signs the session cookie, so nobody can change it (for example,
# to give themselves the owner role). On Azure it comes from Key Vault.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,     # page scripts cannot read the cookie
    SESSION_COOKIE_SAMESITE="Lax",    # other sites cannot send forms with it
    SESSION_COOKIE_SECURE=ON_AZURE,   # HTTPS only on Azure
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

# ---------- Storage ----------

MONGODB_URI = os.environ.get("MONGODB_URI")
if MONGODB_URI:
    from pymongo import MongoClient

    from mongo_inventory import MongoInventory
    _db = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)[os.environ.get("MONGODB_DB", "stockwise")]
    inventory = MongoInventory(_db["products"])
    inventory.seed_if_empty()
    accounts = MongoAccounts(_db["users"])
else:
    inventory = Inventory.from_file()
    accounts = MemoryAccounts()

# The owner account. On Azure, both values come from GitHub secrets via Key Vault.
# On a laptop, a local test owner is created so the dashboard can be tried.
if MONGODB_URI or ON_AZURE:
    accounts.ensure_owner(os.environ.get("OWNER_EMAIL"), os.environ.get("OWNER_PASSWORD"))
else:
    accounts.ensure_owner(os.environ.get("OWNER_EMAIL", "owner@stockwise.test"),
                          os.environ.get("OWNER_PASSWORD", "owner-pass-123"))


# ---------- Who is signed in ----------

def current_user():
    return session.get("user")


def is_owner():
    user = current_user()
    return bool(user and user.get("role") == OWNER)


def sign_in(user):
    session.clear()  # a fresh session at every sign-in
    session.permanent = True
    session["user"] = user


def safe_next(target, default):
    # Only allow paths on our own site, so the login page cannot send people elsewhere.
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return default


@app.context_processor
def shared_values():
    # Values every page template can use.
    return {
        "status_of": Inventory.status,
        "labels": STATUS_LABELS,
        "user": current_user(),
        "is_owner": is_owner(),
    }


def owner_required(view):
    """Pages: not signed in -> sign-in page; signed in without the owner role -> 403."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login", next=request.path))
        if not is_owner():
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def owner_api(view):
    """API: not signed in -> 401; signed in without the owner role -> 403 (JSON)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return jsonify(error="Sign in first."), 401
        if not is_owner():
            return jsonify(error="Owner role required."), 403
        return view(*args, **kwargs)
    return wrapper


@app.errorhandler(403)
def forbidden(_error):
    return render_template("forbidden.html"), 403


# ---------- Customer view ----------

@app.get("/")
def customer():
    query = request.args.get("q", "")
    products = [inventory.public_view(p) for p in inventory.search(query)]
    return render_template("customer.html", products=products, query=query)


# ---------- Sign up, sign in, sign out ----------

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            user = accounts.sign_up(request.form.get("name"), request.form.get("email"),
                                    request.form.get("password"))
        except AccountError as error:
            flash(str(error), "error")
            return render_template("signup.html", name=request.form.get("name", ""),
                                   email=request.form.get("email", "")), 400
        sign_in(user)
        flash(f"Welcome, {user['name']}. Your account is ready.", "ok")
        return redirect(url_for("customer"))
    return render_template("signup.html", name="", email="")


@app.route("/login", methods=["GET", "POST"])
def login():
    next_page = request.values.get("next", "")
    if request.method == "POST":
        user = accounts.authenticate(request.form.get("email"), request.form.get("password"))
        if user is None:
            flash("The email or password is not correct.", "error")
            return render_template("login.html", email=request.form.get("email", ""),
                                   next_page=next_page), 401
        sign_in(user)
        default = url_for("owner") if user["role"] == OWNER else url_for("customer")
        return redirect(safe_next(next_page, default))
    return render_template("login.html", email="", next_page=next_page)


@app.post("/logout")
def logout():
    session.clear()
    flash("You have signed out.", "ok")
    return redirect(url_for("customer"))


@app.get("/owner/login")
def owner_login():
    # Old link: the owner now signs in on the shared sign-in page.
    return redirect(url_for("login", next="/owner"))


# ---------- Owner dashboard (owner role required) ----------

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


@app.get("/owner/test-error")
@owner_required
def owner_test_error():
    # Owner-only: causes a server error (HTTP 500) so we can test the alert.
    raise RuntimeError("Test error for the StockWise 5xx alert")


# ---------- API ----------

@app.get("/api/health")
def health():
    # Used by monitoring and by us to check the app is running.
    return jsonify(status="ok", storage="database" if MONGODB_URI else "memory")


@app.get("/api/products")
def api_products():
    # Public endpoint: what customers see (name, price, units in stock, status).
    return jsonify([inventory.public_view(p) for p in inventory.search(request.args.get("q"))])


@app.get("/api/me")
def api_me():
    # Who is signed in (never includes the password hash).
    user = current_user()
    if user is None:
        return jsonify(error="Sign in first."), 401
    return jsonify(user)


@app.get("/api/owner/low-stock")
@owner_api
def api_low_stock():
    # Owner-only API: products that are low or out of stock.
    return jsonify([
        {"sku": p["sku"], "name": p["name"], "stock": p["stock"], "status": Inventory.status(p)}
        for p in inventory.low_stock()
    ])


if __name__ == "__main__":
    # Local run only. On Azure, gunicorn starts the app (see infra/main.bicep).
    app.run(debug=True, port=5001)
