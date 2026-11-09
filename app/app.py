"""StockWise Solutions web app (Flask).

One app serves both views and a small API:
  /                public landing page: what the store offers; sign up or sign in
  /signup          customers create an account (always a customer account)
  /login           customer sign-in
  /shop            signed-in customers search products, see units in stock and reserve
  /reservations    a customer's reservations (cancel while waiting for pickup)
  /owner/login     owner sign-in (not linked from the public pages)
  /owner           owner dashboard: stock, low-stock list, reservations, sales, restocks
  /logout          sign out
  /api/...         JSON endpoints

Sign-in: accounts are stored in the database with a salted password hash. After
sign-in, Flask gives the browser a signed session cookie (the token). Every owner
page and owner API checks that token for the "owner" role.

Stock, reservations and accounts are saved in Azure Cosmos DB for MongoDB when
MONGODB_URI is set (on Azure), and kept in memory otherwise (on a laptop).
When a sale or reservation makes an item low, the owner gets an email (notify.py).
"""

import logging
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
from inventory import (CANCELLED, MAX_RESERVE_QUANTITY, PICKED_UP,  # noqa: E402
                       RESERVED, STATUS_LABELS, Inventory, StockError)
from notify import LowStockNotifier  # noqa: E402

logging.basicConfig(level=logging.INFO)

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
    inventory.ensure_indexes()
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


# Low-stock email (only sends when the ACS_* settings exist; see notify.py).
notifier = LowStockNotifier.from_environment()


def stock_went_down(product, quantity):
    """Tell the notifier about a sale or reservation that lowered the stock."""
    notifier.stock_changed(product, product["stock"] + int(quantity))


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


def login_required(view):
    """Pages for registered users: not signed in -> customer sign-in page."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            flash("Please sign in or create an account to see our products.", "ok")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapper


def owner_required(view):
    """Owner pages: not signed in -> owner sign-in page; signed in without the owner role -> 403."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("owner_login", next=request.path))
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


# ---------- Public landing page ----------

@app.get("/")
def landing():
    return render_template("landing.html")


# ---------- Shop (registered users only) ----------

@app.get("/shop")
@login_required
def customer():
    query = request.args.get("q", "")
    products = [inventory.public_view(p) for p in inventory.search(query)]
    return render_template("customer.html", products=products, query=query,
                           max_reserve=MAX_RESERVE_QUANTITY)


# ---------- Reservations (customers) ----------

def make_reservation(sku, quantity):
    """Shared by the page and the API. Returns the reservation view."""
    user = current_user()
    product, reservation = inventory.reserve(sku, quantity, user["email"], user["name"])
    stock_went_down(product, reservation["quantity"])
    return reservation


@app.post("/shop/reserve")
@login_required
def reserve():
    if is_owner():
        flash("The owner account cannot reserve items. Record a sale instead.", "error")
        return redirect(url_for("customer"))
    try:
        reservation = make_reservation(request.form.get("sku"), request.form.get("quantity", 1))
        flash(f"Reserved {reservation['quantity']} × {reservation['product_name']}. "
              "We will hold it for you at the store.", "ok")
        return redirect(url_for("my_reservations"))
    except StockError as error:
        flash(str(error), "error")
        return redirect(url_for("customer"))


@app.get("/reservations")
@login_required
def my_reservations():
    return render_template("reservations.html",
                           reservations=inventory.reservations(customer_email=current_user()["email"]))


@app.post("/reservations/<reservation_id>/cancel")
@login_required
def cancel_my_reservation(reservation_id):
    try:
        inventory.set_reservation_status(reservation_id, CANCELLED,
                                         customer_email=current_user()["email"])
        flash("Your reservation is cancelled.", "ok")
    except StockError as error:
        flash(str(error), "error")
    return redirect(url_for("my_reservations"))


# ---------- Customer sign up, sign in, sign out ----------

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
        if user is not None and user["role"] == OWNER:
            # The owner has a separate sign-in page; do not sign in here.
            flash("This is the customer sign-in. The store owner signs in on the owner page.", "error")
            return redirect(url_for("owner_login"))
        if user is None:
            flash("The email or password is not correct.", "error")
            return render_template("login.html", email=request.form.get("email", ""),
                                   next_page=next_page), 401
        sign_in(user)
        return redirect(safe_next(next_page, url_for("customer")))
    return render_template("login.html", email="", next_page=next_page)


@app.post("/logout")
def logout():
    session.clear()
    flash("You have signed out.", "ok")
    return redirect(url_for("landing"))


# ---------- Owner sign-in (separate page, owner accounts only) ----------

@app.route("/owner/login", methods=["GET", "POST"])
def owner_login():
    next_page = request.values.get("next", "")
    if request.method == "POST":
        user = accounts.authenticate(request.form.get("email"), request.form.get("password"))
        if user is None or user["role"] != OWNER:
            # Same message for a wrong password and for a customer account.
            flash("The email or password is not correct.", "error")
            return render_template("owner_signin.html", email=request.form.get("email", ""),
                                   next_page=next_page), 401
        sign_in(user)
        return redirect(safe_next(next_page, url_for("owner")))
    return render_template("owner_signin.html", email="", next_page=next_page)


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
    waiting = inventory.reservations(status=RESERVED)
    summary["reserved"] = len(waiting)
    return render_template(
        "owner.html",
        products=products,
        low_stock=inventory.low_stock(),
        summary=summary,
        waiting=waiting,
        email_on=notifier.enabled,
    )


@app.post("/owner/sale")
@owner_required
def owner_sale():
    try:
        product = inventory.record_sale(request.form["sku"], request.form["quantity"])
        stock_went_down(product, request.form["quantity"])
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


@app.post("/owner/reservations/<reservation_id>/<action>")
@owner_required
def owner_reservation(reservation_id, action):
    new_status = {"pickup": PICKED_UP, "cancel": CANCELLED}.get(action)
    if new_status is None:
        abort(404)
    try:
        _, reservation = inventory.set_reservation_status(reservation_id, new_status)
        flash(f"{reservation['product_name']} for {reservation['customer_name']}: "
              f"{reservation['status_label'].lower()}.", "ok")
    except StockError as error:
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
    # Registered users only: what customers see (name, price, units in stock, status).
    if current_user() is None:
        return jsonify(error="Sign in first."), 401
    return jsonify([inventory.public_view(p) for p in inventory.search(request.args.get("q"))])


@app.get("/api/me")
def api_me():
    # Who is signed in (never includes the password hash).
    user = current_user()
    if user is None:
        return jsonify(error="Sign in first."), 401
    return jsonify(user)


@app.route("/api/reservations", methods=["GET", "POST"])
def api_reservations():
    # GET: the signed-in customer's reservations. POST {"sku", "quantity"}: create one.
    user = current_user()
    if user is None:
        return jsonify(error="Sign in first."), 401
    if request.method == "GET":
        return jsonify(inventory.reservations(customer_email=user["email"]))
    if is_owner():
        return jsonify(error="The owner account cannot reserve items."), 403
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(make_reservation(data.get("sku"), data.get("quantity", 1))), 201
    except StockError as error:
        return jsonify(error=str(error)), 409


@app.get("/api/owner/reservations")
@owner_api
def api_owner_reservations():
    # Owner-only API: all reservations, or ?status=reserved / picked_up / cancelled.
    status = request.args.get("status") or None
    return jsonify(inventory.reservations(status=status))


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
