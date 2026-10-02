#!/usr/bin/env python3
"""The shop's HTTP API.

    python -m shop.server            # http://0.0.0.0:8765

The storefront (frontend/) calls it through the Vite proxy. Everything is
JSON under /api:

    auth      POST /api/auth/register, /api/auth/login   GET /api/auth/me
    checkout  POST /api/checkout/quote   POST /api/orders
    orders    GET /api/orders, /api/orders/{id}   POST /api/orders/{id}/cancel, /return
    account   GET /api/addresses
    admin     GET /api/admin/orders, /api/admin/simulation   PUT /api/admin/simulation
              POST /api/admin/orders/{id}/advance, /hold, /release, /refund
    support   /api/support/*  (shop/support.py)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional
    load_dotenv = None

from scraper.support import routes as desk  # noqa: E402
from shop import auth, catalog, orders, simulation, support, switches  # noqa: E402

MAX_BODY_BYTES = desk.MAX_BODY_BYTES
Response = Tuple[int, Dict[str, Any]]


def load_env() -> None:
    if load_dotenv is None:
        return
    for env_file in (ROOT / ".env", ROOT / "frontend" / ".env"):
        if env_file.is_file():
            load_dotenv(env_file, override=False)


def _fail(status: int, reason: str, message: str) -> Response:
    return status, {"ok": False, "reason": reason, "message": message}


def _session(user: auth.Identity) -> Response:
    return 200, {"ok": True, "token": auth.issue(user), "user": user.public()}


def route(req: support.Request) -> Response:
    """One request in, one (status, JSON) out. Tested without a socket."""
    answer = support.handle(req)
    if answer is not None:
        return answer

    method = req.method.upper()
    parts = [p for p in req.path.split("/") if p]
    if parts[:1] != ["api"]:
        return _fail(404, "not-found", "There is nothing at this address.")
    parts = parts[1:]
    data = req.json() if method in ("POST", "PUT") else {}
    user = req.user

    try:
        if parts == ["health"]:
            return 200, {"ok": True, "products": catalog.count()}

        # ---- Accounts ----
        if parts == ["auth", "register"] and method == "POST":
            if not desk.limiter.allow("register:" + req.client, 20, 3600):
                return _fail(429, "too-many-requests", "Too many new accounts from here. Please try again later.")
            return _session(auth.register(data.get("name"), data.get("email"), data.get("password")))
        if parts == ["auth", "login"] and method == "POST":
            if not desk.limiter.allow("login:" + req.client, 30, 600):
                return _fail(429, "too-many-requests", "Too many sign-in attempts. Please wait a few minutes.")
            # The storefront's old sign-in form sends `username`.
            return _session(auth.login(data.get("email") or data.get("username"), data.get("password")))
        if parts == ["auth", "me"] and method == "GET":
            if user is None:
                return _fail(401, "sign-in-required", "You are not signed in.")
            return 200, {"ok": True, "user": user.public()}

        # ---- Checkout ----
        if parts == ["checkout", "options"] and method == "GET":
            return 200, {
                "ok": True,
                "delivery": [
                    {"key": key, "label": rule["label"], "fee": rule["fee"], "freeOver": rule["free_over"], "days": rule["days"]}
                    for key, rule in orders.DELIVERY.items()
                ],
                "payments": [{"key": key, "label": label} for key, label in orders.PAYMENTS.items()],
                "sizes": list(orders.SIZES),
                "maxQuantity": orders.MAX_QUANTITY,
            }
        if parts == ["checkout", "quote"] and method == "POST":
            return 200, {"ok": True, **orders.quote(data)}

        if parts[:1] in (["orders"], ["addresses"]) and (user is None or user.role != "shopper"):
            return _fail(401, "sign-in-required", "Sign in to continue.")

        if parts == ["addresses"] and method == "GET":
            return 200, {"ok": True, "addresses": orders.addresses(user.id)}

        # ---- Orders ----
        if parts == ["orders"] and method == "POST":
            if not desk.limiter.allow("order:" + user.id, 60, 3600):
                return _fail(429, "too-many-requests", "That is a lot of orders. Please try again later.")
            try:
                return 201, {"ok": True, "order": orders.place(user.id, data)}
            except orders.OrderError as err:
                if err.reason == "payment-failed":
                    simulation.payment_failed(str(data.get("payment")))
                raise
        if parts == ["orders"] and method == "GET":
            return 200, {"ok": True, "orders": orders.list_for(user.id)}
        if len(parts) == 2 and parts[0] == "orders" and method == "GET":
            return 200, {"ok": True, "order": orders.get_for(user.id, parts[1])}
        if len(parts) == 3 and parts[0] == "orders" and method == "POST":
            if parts[2] == "cancel":
                return 200, {"ok": True, "order": orders.cancel(user.id, parts[1], data.get("reason") or "")}
            if parts[2] == "return":
                return 200, {"ok": True, "order": orders.request_return(user.id, parts[1], data.get("reason") or "")}

        # ---- Admin: the warehouse floor and the simulation switches ----
        if parts[:1] == ["admin"]:
            if user is None or user.role != "admin":
                return _fail(401, "sign-in-required", "Sign in as the admin to see this.")
            if parts == ["admin", "orders"] and method == "GET":
                return 200, {"ok": True, "orders": orders.admin_list(), "status": simulation.status()}
            if parts == ["admin", "simulation"] and method == "GET":
                return 200, {"ok": True, "switches": switches.current(), "status": simulation.status()}
            if parts == ["admin", "simulation"] and method == "PUT":
                return 200, {"ok": True, "switches": simulation.set_switches(data), "status": simulation.status()}
            if len(parts) == 4 and parts[1] == "orders" and method == "POST":
                order_id, action = parts[2], parts[3]
                if action == "advance":
                    return 200, {"ok": True, "order": orders.advance(order_id)}
                if action in ("hold", "release"):
                    return 200, {"ok": True, "order": orders.set_hold(order_id, action == "hold")}
                if action == "refund":
                    orders.refund(order_id, "Refund approved by the shop: " + str(data.get("reason") or "")[:200])
                    return 200, {"ok": True, "order": orders.get(order_id)}
    except auth.AuthError as err:
        return _fail(err.status, err.reason, err.message)
    except orders.OrderError as err:
        return _fail(err.status, err.reason, err.message)

    return _fail(404, "not-found", "There is nothing at this address.")


class ShopHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def _handle(self, method: str) -> None:
        parts = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            # Take what is being sent (within reason) and drop it, so the caller can read the refusal.
            remaining = min(length, 8 * 1024 * 1024)
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            self.close_connection = True
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "reason": "too-large"})
            return
        request = support.Request(
            method=method,
            path=unquote(parts.path),
            query=dict(parse_qsl(parts.query)),
            headers={key.lower(): value for key, value in self.headers.items()},
            raw_body=self.rfile.read(length) if length > 0 else b"",
            client=self._client(),
        )
        # A tool call carries the desk's token in the same header; it is not a session.
        if not request.path.startswith(support.PREFIX + "/tools/"):
            request.user = auth.verify(request.bearer())
        try:
            status, payload = route(request)
        except Exception as exc:  # One broken request must not take the shop down.
            print("[shop] %s %s failed: %r" % (method, parts.path, exc), flush=True)
            status, payload = HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "reason": "error"}
        self._send(status, payload)

    def _client(self) -> str:
        """The caller's address. The storefront's dev proxy runs on this machine and says who it speaks for."""
        peer = self.client_address[0]
        forwarded = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return forwarded if forwarded and peer in ("127.0.0.1", "::1") else peer

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-Token")
        self.send_header("Cache-Control", "no-store")

    def _send(self, status: int, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ethnic Threads shop API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--step-seconds",
        type=int,
        default=None,
        help="How long an order stays at each step (default: SHOP_STEP_SECONDS, or %d)" % switches.DEFAULT_STEP_SECONDS,
    )
    args = parser.parse_args()
    load_env()
    if args.step_seconds:
        os.environ["SHOP_STEP_SECONDS"] = str(args.step_seconds)
        switches.update({"step_seconds": args.step_seconds})

    simulation.start()
    server = ThreadingHTTPServer((args.host, args.port), ShopHandler)
    print(
        "Ethnic Threads shop on http://%s:%d (%d products, an order moves every %ds)"
        % (args.host, args.port, catalog.count(), switches.current()["step_seconds"]),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
