"""Fixtures for the shop's tests: a fresh database, a small catalogue, and (when a
test asks for it) the stand-in support desk from tests/support."""

import json

import pytest

# Imported so pytest sees them here too: every SUPPORT_* setting is cleared before
# each test, and `desk` is a local HTTP server that records what the shop sends.
from tests.support.conftest import clean_support_state, desk  # noqa: F401

from shop import auth, catalog, db, orders, server, support, switches
from scraper.support import routes as desk_routes

PRODUCTS = [
    {
        "id": "kurta-001",
        "title": "Cotton Straight Kurta",
        "brand": "Biba",
        "source": "myntra",
        "price_current": 899.0,
        "price_original": 1799.0,
        "image_url": "https://example.com/kurta.jpg",
        "category": "Kurta",
        "target_gender": "Women",
        "in_stock": True,
    },
    {
        "id": "saree-002",
        "title": "Banarasi Silk Saree with Blouse Piece",
        "brand": "Kalini",
        "price_current": 2199.0,
        "category": "Saree",
        "target_gender": "Women",
        "in_stock": True,
    },
    {"id": "dupatta-003", "title": "Chiffon Dupatta", "brand": "Rangoli", "price_current": 249.0, "in_stock": True},
    {"id": "sherwani-004", "title": "Wedding Sherwani", "price_current": 5999.0, "in_stock": False},
]

ADDRESS = {
    "name": "Asha Verma",
    "phone": "98300 55555",
    "line1": "12 MG Road",
    "city": "Bengaluru",
    "state": "Karnataka",
    "pincode": "560001",
}


@pytest.fixture(autouse=True)
def shop(monkeypatch, tmp_path):
    """A shop with an empty database, four products, and no pause between hashing rounds."""
    monkeypatch.setattr(db, "DB_FILE", tmp_path / "shop.db")
    db.reset_for_tests()
    catalogue = tmp_path / "products.json"
    catalogue.write_text(json.dumps(PRODUCTS), encoding="utf-8")
    monkeypatch.setattr(catalog, "CATALOG_FILE", catalogue)
    catalog._cache.update(path=None, mtime=None, by_id={}, all=[])
    # Real key stretching is slow by design; the tests do not need to wait for it.
    monkeypatch.setattr(auth, "PBKDF2_ROUNDS", 1000)
    monkeypatch.setenv("ADMIN_USERNAME", "shop_admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.delenv("SHOP_STEP_SECONDS", raising=False)
    monkeypatch.delenv("SHOP_SESSION_SECRET", raising=False)
    desk_routes.limiter.reset()
    yield
    db.reset_for_tests()


def call(method, path, body=None, token=None, query=None, headers=None, client="203.0.113.9", raw=None):
    """One request through the shop's router, as the HTTP handler would hand it over."""
    all_headers = {k.lower(): v for k, v in (headers or {}).items()}
    if token:
        all_headers["authorization"] = "Bearer " + token
    request = support.Request(
        method=method,
        path=path,
        query=query or {},
        headers=all_headers,
        raw_body=raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else b""),
        client=client,
    )
    if not path.startswith(support.PREFIX + "/tools/"):
        request.user = auth.verify(request.bearer())
    return server.route(request)


class Shopper:
    def __init__(self, name, email):
        status, body = call("POST", "/api/auth/register", {"name": name, "email": email, "password": "kurta-lover-1"})
        assert status == 200, body
        self.token = body["token"]
        self.id = body["user"]["id"]
        self.email = body["user"]["email"]
        self.name = name

    def order(self, items=None, payment="upi", **extra):
        payload = {
            "items": items or [{"productId": "kurta-001", "quantity": 1, "size": "M"}],
            "address": ADDRESS,
            "payment": payment,
            **extra,
        }
        status, body = call("POST", "/api/orders", payload, self.token)
        assert status == 201, body
        return body["order"]


@pytest.fixture
def asha():
    return Shopper("Asha Verma", "asha@shopper.example")


@pytest.fixture
def ravi():
    return Shopper("Ravi Menon", "ravi@shopper.example")


@pytest.fixture
def admin_token():
    status, body = call("POST", "/api/auth/login", {"username": "shop_admin", "password": "test-admin-password"})
    assert status == 200, body
    return body["token"]


def deliver(order_id):
    """Walks an order to Delivered, as the clock would."""
    while orders.get(order_id)["status"] != "delivered":
        orders.advance(order_id)
    return orders.get(order_id)


__all__ = ["ADDRESS", "PRODUCTS", "Shopper", "call", "deliver", "switches"]
