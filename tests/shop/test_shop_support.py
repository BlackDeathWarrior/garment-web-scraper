"""The shop's support desk integration: requests about orders, and the AI's order tools."""

import base64
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from scraper.support import tokens
from scraper.support.tms_support import sign_webhook
from shop import orders, server

from tests.support.conftest import TOOL_TOKEN, WEB_KEY, WEBHOOK_SECRET

from .conftest import ADDRESS, Shopper, call, deliver

TOOL = {"Authorization": "Bearer " + TOOL_TOKEN}


def ticket_of(reference, shopper_id, order_id=None, state="open"):
    return {
        "reference": reference,
        "subject": "Where is my order? Order %s" % order_id,
        "status": {"key": "new", "name": "New", "state": state},
        "externalRef": order_id,
        "customer": {"name": "Asha Verma", "email": "asha@shopper.example", "externalId": shopper_id},
        "createdAt": "2026-10-02T10:00:00.000Z",
        "updatedAt": "2026-10-02T10:05:00.000Z",
    }


# ---- Raising requests ----


def test_help_with_an_order_carries_the_order_from_our_records(asha, desk):
    order = asha.order([{"productId": "kurta-001", "quantity": 2, "size": "M"}], payment="cod")
    desk.answer("POST /api/v1/integration/tickets", 201, {"reference": "TMS-41"})
    status, body = call(
        "POST",
        "/api/support/tickets",
        {
            "kind": "order",
            "orderId": order["id"],
            "issue": "where",
            "message": "It was due yesterday.",
            "requestId": "help-0001-abcd",
            # A browser could send anything; none of it may reach the ticket.
            "total": 1,
            "metadata": {"status": "delivered"},
        },
        asha.token,
    )
    assert (status, body) == (201, {"ok": True, "reference": "TMS-41"})

    (sent,) = desk.calls("POST", "/integration/tickets")
    assert sent["headers"]["authorization"] == "Bearer " + WEB_KEY
    assert sent["headers"]["idempotency-key"] == "et-help-0001-abcd"
    ticket = sent["body"]
    # The desk knows the shopper by the shop's own id for them.
    assert ticket["customer"] == {"externalId": asha.id, "email": "asha@shopper.example", "name": "Asha Verma"}
    assert ticket["subject"] == "Where is my order? Order %s" % order["id"]
    assert ticket["externalRef"] == order["id"]
    assert ticket["category"] == "Orders and delivery"
    assert ticket["tags"] == ["order", "where"]
    assert ticket["metadata"] == {
        "form": "order_help",
        "issue": "Where is my order?",
        "order_id": order["id"],
        "status": "order placed",
        "placed_at": order["placedAt"],
        "estimated_delivery": order["delivery"]["expected"],
        "delayed": False,
        "total": 1798.0,
        "currency": "INR",
        "payment_method": "Cash on delivery",
        "payment_status": "pay on delivery",
        "items": "Cotton Straight Kurta x2",
        "item_count": 2,
        "first_item": "Cotton Straight Kurta",
        "can_cancel": True,
        "can_return": False,
    }


def test_help_is_only_for_your_own_order_and_only_when_signed_in(asha, ravi, desk):
    order = asha.order()
    request = {"kind": "order", "orderId": order["id"], "issue": "cancel", "message": "x", "requestId": "help-0002-abcd"}
    assert call("POST", "/api/support/tickets", request)[0] == 401
    status, body = call("POST", "/api/support/tickets", request, ravi.token)
    assert (status, body["reason"]) == (404, "not-found")
    assert desk.calls("POST", "/integration/tickets") == []


def test_a_guest_can_write_in_and_gets_a_tracking_token(desk):
    desk.answer("POST /api/v1/integration/tickets", 201, {"reference": "TMS-50"})
    status, body = call(
        "POST",
        "/api/support/tickets",
        {
            "name": "Passing Visitor",
            "email": "visitor@shopper.example",
            "subject": "Product question",
            "message": "Do you have this saree in green?",
            "requestId": "form-0001-abcd",
        },
    )
    assert status == 201
    assert body["token"] == tokens.tracking_token(WEB_KEY, "TMS-50")
    (sent,) = desk.calls("POST", "/integration/tickets")
    # No id of ours: a guest is only an email address.
    assert sent["body"]["customer"] == {"email": "visitor@shopper.example", "name": "Passing Visitor"}
    assert sent["body"]["category"] == "Products"
    assert sent["body"]["metadata"] == {"form": "contact", "topic": "Product question"}
    assert call("POST", "/api/support/tickets", {"message": "x", "requestId": "form-0002-abcd"})[0] == 400


# ---- Reading them back ----


def test_my_requests_lists_what_the_desk_has_for_this_shopper(asha, desk):
    desk.answer(
        "GET /api/v1/integration/tickets",
        200,
        {"items": [ticket_of("TMS-41", asha.id, "ET-100001"), ticket_of("TMS-40", asha.id, None, "resolved")], "total": 2},
    )
    status, body = call("GET", "/api/support/requests", token=asha.token)
    assert status == 200
    assert [(r["reference"], r["orderId"], r["state"]) for r in body["requests"]] == [
        ("TMS-41", "ET-100001", "open"),
        ("TMS-40", None, "resolved"),
    ]
    # Asked for by the shop's id for the shopper, never by something the browser sent.
    assert "customer=%s" % asha.id in desk.calls("GET", "/integration/tickets")[0]["path"]
    assert call("GET", "/api/support/requests")[0] == 401


def test_a_request_is_read_by_its_shopper_and_nobody_else(asha, ravi, admin_token, desk):
    def read(token=None, headers=None):
        desk.answer("GET /api/v1/integration/tickets/TMS-41/messages", 200, [{"id": "m1", "from": "customer", "body": "Hi"}])
        desk.answer("GET /api/v1/integration/tickets/TMS-41", 200, ticket_of("TMS-41", asha.id, "ET-100001"))
        return call("GET", "/api/support/requests/TMS-41", token=token, headers=headers)

    status, body = read(asha.token)
    assert (status, body["orderId"], body["mine"]) == (200, "ET-100001", True)
    assert "customer" not in body
    # Another shopper, and someone not signed in, are told it does not exist.
    assert read(ravi.token)[0] == 404
    assert read()[0] == 404
    # The admin reads it, but may not speak or rate for the shopper.
    status, body = read(admin_token)
    assert (status, body["mine"]) == (200, False)
    reply = {"message": "Speaking for the shopper", "requestId": "reply-0009-abcd"}
    assert call("POST", "/api/support/requests/TMS-41/messages", reply, admin_token)[0] == 404
    assert desk.calls("POST", "/tickets/TMS-41/") == []


def test_the_shopper_replies_and_rates(asha, desk):
    def mine():
        desk.answer("GET /api/v1/integration/tickets/TMS-41", 200, ticket_of("TMS-41", asha.id))

    mine()
    reply = {"message": "Still not here.", "requestId": "reply-0001-abcd"}
    assert call("POST", "/api/support/requests/TMS-41/messages", reply, asha.token)[0] == 201
    assert desk.calls("POST", "/tickets/TMS-41/messages")[0]["body"] == {"body": "Still not here."}
    mine()
    assert call("POST", "/api/support/requests/TMS-41/rating", {"rating": 4}, asha.token)[0] == 200
    assert desk.calls("POST", "/tickets/TMS-41/rating")[0]["body"] == {"rating": 4}
    mine()
    assert call("POST", "/api/support/requests/TMS-41/rating", {"rating": 0}, asha.token)[0] == 400


def test_a_guest_reads_their_request_with_the_token_from_its_link(desk):
    headers = {"X-Request-Token": tokens.tracking_token(WEB_KEY, "TMS-50")}
    desk.answer("GET /api/v1/integration/tickets/TMS-50", 200, ticket_of("TMS-50", None))
    assert call("GET", "/api/support/requests/TMS-50", headers=headers)[0] == 200
    assert call("GET", "/api/support/requests/TMS-50", headers={"X-Request-Token": "0" * 32})[0] == 404


def test_the_chat_is_told_who_is_signed_in(asha, admin_token, desk):
    status, body = call("GET", "/api/support/identity", token=asha.token)
    claims = body["token"].split(".")[1]
    decoded = json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))
    assert (decoded["sub"], decoded["name"], decoded["email"]) == (asha.id, "Asha Verma", "asha@shopper.example")
    admin = call("GET", "/api/support/identity", token=admin_token)[1]["token"].split(".")[1]
    assert json.loads(base64.urlsafe_b64decode(admin + "=" * (-len(admin) % 4)))["sub"] == "admin"
    assert call("GET", "/api/support/identity")[0] == 401


def test_webhooks_are_verified_and_feed_the_admin_overview(asha, admin_token, desk):
    payload = {
        "id": "d-1",
        "type": "message.created",
        "createdAt": "2026-10-02T10:05:00.000Z",
        "data": {"ticket": ticket_of("TMS-41", asha.id), "message": {"from": "support", "name": "Maya", "body": "On its way."}},
    }
    raw = json.dumps(payload)
    signed = {"X-TMS-Signature": sign_webhook(raw, WEBHOOK_SECRET, int(time.time()))}
    assert call("POST", "/api/support/webhook", raw=raw.encode(), headers=signed)[0] == 200
    forged = {"X-TMS-Signature": sign_webhook(raw, "whsec_someone_else", int(time.time()))}
    assert call("POST", "/api/support/webhook", raw=raw.encode(), headers=forged)[0] == 401

    desk.answer("GET /api/v1/integration/tickets", 200, {"items": [ticket_of("TMS-41", asha.id)], "total": 1})
    desk.answer("GET /api/v1/integration/incidents", 200, [])
    status, body = call("GET", "/api/support/admin/overview", token=admin_token)
    assert status == 200 and [e["id"] for e in body["events"]] == ["d-1"]
    assert call("GET", "/api/support/admin/overview", token=asha.token)[0] == 401


# ---- Tools the desk's AI calls ----


def test_tools_need_the_tool_token(asha, desk):
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Bearer " + asha.token}):
        assert call("GET", "/api/support/tools/shop-status", headers=headers)[0] == 401


def test_an_order_is_shown_only_to_the_customer_it_belongs_to(asha, ravi, desk):
    order = asha.order(payment="cod")
    orders.advance(order["id"])
    orders.advance(order["id"])
    path = "/api/support/tools/orders/" + order["id"]

    status, body = call("GET", path, headers=TOOL, query={"customer_email": "Asha@Shopper.example"})
    assert status == 200
    assert (body["order_id"], body["status"], body["carrier"]) == (order["id"], "shipped", "SwiftShip")
    assert body["tracking_number"].startswith("SW") and body["estimated_delivery"] == order["delivery"]["expected"]
    assert (body["can_cancel"], body["payment_status"]) == (False, "pay on delivery")
    # The address the desk bound the call to decides, not the order number someone typed.
    status, body = call("GET", path, headers=TOOL, query={"customer_email": ravi.email})
    assert (status, body) == (404, {"message": "This customer has no order with that number."})
    assert call("GET", path, headers=TOOL, query={"customer_email": "nobody@shopper.example"})[0] == 404
    assert call("GET", path, headers=TOOL)[0] == 400

    status, body = call("GET", "/api/support/tools/orders", headers=TOOL, query={"customer_email": asha.email})
    assert (status, body["count"], body["orders"][0]["order_id"]) == (200, 1, order["id"])
    assert call("GET", "/api/support/tools/orders", headers=TOOL, query={"customer_email": ravi.email})[1]["count"] == 0


def test_the_cancel_tool_cancels_for_the_customer_and_refunds(asha, ravi, desk):
    order = asha.order(payment="upi")
    path = "/api/support/tools/orders/%s/cancel" % order["id"]
    assert call("POST", path, {"customer_email": ravi.email}, headers=TOOL)[0] == 404
    status, body = call("POST", path, {"customer_email": asha.email, "reason": "asked in chat"}, headers=TOOL)
    assert (status, body["status"], body["amount"]) == (200, "cancelled", order["total"])
    assert body["refund_id"].startswith("RF-")
    assert orders.get(order["id"])["cancelReason"] == "Cancelled by support: asked in chat"

    shipped = asha.order()
    orders.advance(shipped["id"])
    orders.advance(shipped["id"])
    status, body = call(
        "POST", "/api/support/tools/orders/%s/cancel" % shipped["id"], {"customer_email": asha.email}, headers=TOOL
    )
    assert status == 409 and "already shipped" in body["message"]


def test_the_refund_tool_refunds_a_delivered_order_once(asha, ravi, desk):
    order = asha.order()
    refund = {"order_id": order["id"], "customer_email": asha.email, "reason": "arrived torn"}
    status, body = call("POST", "/api/support/tools/refunds", refund, headers=TOOL)
    assert status == 409 and "refunded when it is cancelled" in body["message"]

    deliver(order["id"])
    assert call("POST", "/api/support/tools/refunds", {**refund, "customer_email": ravi.email}, headers=TOOL)[0] == 404
    status, body = call("POST", "/api/support/tools/refunds", refund, headers=TOOL)
    assert status == 200
    assert body == {
        "refund_id": body["refund_id"],
        "order_id": order["id"],
        "amount": order["total"],
        "currency": "INR",
        "arrives_in": "5 to 7 business days",
    }
    assert call("POST", "/api/support/tools/refunds", refund, headers=TOOL)[1] == body
    assert orders.get(order["id"])["status"] == "refunded"


def test_product_and_shop_status_tools(asha, admin_token, desk):
    status, body = call("GET", "/api/support/tools/products/saree-002", headers=TOOL)
    assert (status, body["title"], body["price_current"]) == (200, "Banarasi Silk Saree with Blouse Piece", 2199.0)
    assert call("GET", "/api/support/tools/products/nope", headers=TOOL)[0] == 404
    found = call("GET", "/api/support/tools/products", headers=TOOL, query={"query": "cotton kurta"})[1]
    assert [p["id"] for p in found["products"]] == ["kurta-001"]

    asha.order()
    call("PUT", "/api/admin/simulation", {"payments_down": True}, admin_token)
    assert call("GET", "/api/support/tools/shop-status", headers=TOOL)[1] == {
        "payments": "failing",
        "cash_on_delivery": "working",
        "carrier": "on time",
        "orders_in_progress": 1,
        "delayed_orders": 0,
    }


# ---- Over HTTP ----


def test_the_shop_over_http(desk):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.ShopHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_port

    def request(method, path, body=None, token=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"{}")

    try:
        assert request("GET", "/api/health") == (200, {"ok": True, "products": 4})
        status, body = request(
            "POST", "/api/auth/register", {"name": "Asha Verma", "email": "asha@shopper.example", "password": "kurta-lover-1"}
        )
        token = body["token"]
        order = {"items": [{"productId": "kurta-001", "quantity": 1}], "address": ADDRESS, "payment": "cod"}
        status, body = request("POST", "/api/orders", order, token)
        assert (status, body["order"]["id"]) == (201, "ET-100001")
        assert request("GET", "/api/orders/ET-100001", token=token)[1]["order"]["status"] == "placed"
        assert request("GET", "/api/orders/ET-100001")[0] == 401
        # A session token is not a tool token, and the other way round.
        assert request("GET", "/api/support/tools/shop-status", token=token)[0] == 401
        assert request("GET", "/api/auth/me", token=TOOL_TOKEN)[0] == 401
        assert request("GET", "/api/support/config")[1]["tickets"] is True
        assert request("POST", "/api/support/webhook", {"padding": "x" * (300 * 1024)})[0] == 413
        assert request("GET", "/nowhere")[0] == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_shopper_fixture_is_usable_twice():
    first = Shopper("One", "one@shopper.example")
    second = Shopper("Two", "two@shopper.example")
    assert first.id != second.id
