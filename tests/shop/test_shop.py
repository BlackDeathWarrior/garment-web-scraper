"""The shop itself: accounts, checkout, orders and the simulated warehouse."""

from datetime import timedelta

from shop import auth, db, orders, simulation, switches

from .conftest import ADDRESS, call, deliver


def later(seconds):
    return db.now() + timedelta(seconds=seconds)


# ---- Accounts ----


def test_register_sign_in_and_read_yourself(asha):
    status, body = call("GET", "/api/auth/me", token=asha.token)
    assert (status, body["user"]) == (
        200,
        {"id": asha.id, "role": "shopper", "name": "Asha Verma", "email": "asha@shopper.example"},
    )
    assert call("POST", "/api/auth/login", {"email": "ASHA@shopper.example", "password": "kurta-lover-1"})[0] == 200
    status, body = call("POST", "/api/auth/login", {"email": "asha@shopper.example", "password": "wrong"})
    assert (status, body["reason"]) == (401, "invalid-credentials")
    # The same answer for an account that does not exist.
    assert call("POST", "/api/auth/login", {"email": "nobody@shopper.example", "password": "x"})[0] == 401
    assert call("GET", "/api/auth/me")[0] == 401


def test_registration_refuses_bad_input_and_a_second_account_for_one_email(asha):
    base = {"name": "A", "email": "a@shopper.example", "password": "long-enough-1"}
    for change in ({"name": " "}, {"email": "nope"}, {"password": "short"}):
        status, body = call("POST", "/api/auth/register", {**base, **change})
        assert (status, body["reason"]) == (400, "invalid"), change
    status, body = call("POST", "/api/auth/register", {**base, "email": "Asha@Shopper.example"})
    assert (status, body["reason"]) == (409, "email-taken")


def test_passwords_are_stored_hashed():
    call("POST", "/api/auth/register", {"name": "Asha", "email": "asha@shopper.example", "password": "kurta-lover-1"})
    with db.read() as conn:
        row = conn.execute("SELECT password_hash, salt FROM users").fetchone()
    assert "kurta-lover-1" not in row["password_hash"]
    assert len(row["password_hash"]) == 64 and len(row["salt"]) == 32


def test_sessions_expire_and_cannot_be_forged(asha):
    identity = auth.verify(asha.token)
    assert identity.id == asha.id
    old = auth.issue(identity, now=1_000_000)
    assert auth.verify(old, now=1_000_100).id == asha.id
    assert auth.verify(old, now=1_000_000 + auth.SESSION_TTL_SECONDS + 1) is None
    parts = asha.token.split(".")
    assert auth.verify(".".join([parts[0], "admin", *parts[2:]])) is None
    assert auth.verify(".".join([*parts[:3], "9999999999", parts[4]])) is None
    for bad in (None, "", "user_session_active", "v1.shopper.x"):
        assert auth.verify(bad) is None


def test_the_admin_signs_in_with_the_configured_password(admin_token, asha):
    assert call("GET", "/api/auth/me", token=admin_token)[1]["user"]["role"] == "admin"
    assert call("POST", "/api/auth/login", {"username": "shop_admin", "password": "nope"})[0] == 401
    # A shopper is not an admin, and the admin has no orders of their own.
    assert call("GET", "/api/admin/orders", token=asha.token)[0] == 401
    assert call("GET", "/api/admin/orders")[0] == 401
    assert call("GET", "/api/orders", token=admin_token)[0] == 401


# ---- Checkout ----


def test_a_quote_uses_our_prices_and_the_delivery_rules():
    cheap = call("POST", "/api/checkout/quote", {"items": [{"productId": "dupatta-003", "quantity": 1}]})[1]
    assert (cheap["subtotal"], cheap["shippingFee"], cheap["total"]) == (249.0, 49.0, 298.0)
    free = call("POST", "/api/checkout/quote", {"items": [{"productId": "dupatta-003", "quantity": 2}]})[1]
    assert (free["subtotal"], free["shippingFee"]) == (498.0, 49.0)
    free = call("POST", "/api/checkout/quote", {"items": [{"productId": "kurta-001", "quantity": 1}]})[1]
    assert (free["subtotal"], free["shippingFee"]) == (899.0, 0.0)
    express = call(
        "POST", "/api/checkout/quote", {"items": [{"productId": "kurta-001", "quantity": 1}], "delivery": "express"}
    )[1]
    assert express["total"] == 998.0
    # A price sent by the browser is ignored.
    forged = call("POST", "/api/checkout/quote", {"items": [{"productId": "kurta-001", "quantity": 1, "price": 1}]})[1]
    assert forged["total"] == 899.0


def test_placing_an_order(asha):
    order = asha.order(
        [{"productId": "kurta-001", "quantity": 2, "size": "M"}, {"productId": "dupatta-003", "quantity": 1}],
        saveAddress=True,
    )
    assert order["id"] == "ET-100001"
    assert (order["status"], order["statusLabel"]) == ("placed", "Order placed")
    assert (order["subtotal"], order["shippingFee"], order["total"]) == (2047.0, 0.0, 2047.0)
    assert order["payment"] == {"method": "upi", "label": "UPI", "status": "paid", "statusLabel": "Paid"}
    assert [(i["title"], i["quantity"], i["size"], i["price"]) for i in order["items"]] == [
        ("Cotton Straight Kurta", 2, "M", 899.0),
        ("Chiffon Dupatta", 1, None, 249.0),
    ]
    assert order["address"]["pincode"] == "560001" and order["address"]["phone"] == "9830055555"
    assert [t["done"] for t in order["timeline"]] == [True, False, False, False, False]
    assert order["canCancel"] is True and order["canReturn"] is False
    # Numbers go up; the address is offered next time.
    assert asha.order()["id"] == "ET-100002"
    assert call("GET", "/api/addresses", token=asha.token)[1]["addresses"][0]["line1"] == "12 MG Road"
    assert [o["id"] for o in call("GET", "/api/orders", token=asha.token)[1]["orders"]] == ["ET-100002", "ET-100001"]


def test_checkout_refuses_what_it_cannot_sell(asha):
    def place(**change):
        payload = {"items": [{"productId": "kurta-001", "quantity": 1}], "address": ADDRESS, "payment": "cod", **change}
        status, body = call("POST", "/api/orders", payload, asha.token)
        return status, body.get("reason")

    assert place(items=[]) == (400, "empty-cart")
    assert place(items=[{"productId": "gone", "quantity": 1}]) == (409, "unavailable")
    assert place(items=[{"productId": "sherwani-004", "quantity": 1}]) == (409, "sold-out")
    assert place(items=[{"productId": "kurta-001", "quantity": 6}]) == (400, "invalid")
    assert place(payment="bitcoin") == (400, "invalid")
    assert place(address={**ADDRESS, "pincode": "123"}) == (400, "invalid")
    assert place(address={**ADDRESS, "phone": "12"}) == (400, "invalid")
    assert call("POST", "/api/orders", {"items": []})[0] == 401
    assert call("GET", "/api/orders", token=asha.token)[1]["orders"] == []


def test_an_order_is_its_owners_alone(asha, ravi):
    order = asha.order()
    status, body = call("GET", "/api/orders/" + order["id"], token=ravi.token)
    assert (status, body["reason"]) == (404, "not-found")
    assert call("POST", "/api/orders/%s/cancel" % order["id"], {}, ravi.token)[0] == 404
    assert call("GET", "/api/orders/" + order["id"].lower(), token=asha.token)[0] == 200


# ---- The warehouse clock ----


def test_an_order_moves_one_step_at_a_time_until_it_is_delivered(asha):
    switches.update({"step_seconds": 30})
    order = asha.order(payment="cod")
    assert order["payment"]["status"] == "pay_on_delivery"
    assert simulation.tick(later(10)) == {"advanced": 0, "newly_late": 0}

    seen = []
    for step in range(1, 5):
        assert simulation.tick(later(31 * step))["advanced"] == 1
        seen.append(orders.get(order["id"])["status"])
    assert seen == ["packed", "shipped", "out_for_delivery", "delivered"]

    done = call("GET", "/api/orders/" + order["id"], token=asha.token)[1]["order"]
    assert all(t["done"] for t in done["timeline"])
    assert done["delivery"]["carrier"] == "SwiftShip" and done["delivery"]["trackingNumber"].startswith("SW")
    # Cash was collected at the door.
    assert done["payment"]["status"] == "paid"
    assert (done["canCancel"], done["canReturn"]) == (False, True)
    # Nothing more happens to a delivered order.
    assert simulation.tick(later(10_000)) == {"advanced": 0, "newly_late": 0}


def test_the_admin_can_hold_release_and_push_an_order(asha, admin_token):
    order = asha.order()
    status, body = call("POST", "/api/admin/orders/%s/hold" % order["id"], {}, admin_token)
    assert (status, body["order"]["held"]) == (200, True)
    assert simulation.tick(later(120))["advanced"] == 0
    call("POST", "/api/admin/orders/%s/release" % order["id"], {}, admin_token)
    status, body = call("POST", "/api/admin/orders/%s/advance" % order["id"], {}, admin_token)
    assert body["order"]["status"] == "packed"
    assert body["order"]["customer"] == {"name": "Asha Verma", "email": "asha@shopper.example"}
    listing = call("GET", "/api/admin/orders", token=admin_token)[1]
    assert [o["id"] for o in listing["orders"]] == [order["id"]]
    assert listing["status"]["orders_in_progress"] == 1


# ---- Cancelling, returning, refunding ----


def test_cancelling_before_it_ships_refunds_what_was_paid(asha):
    paid = asha.order(payment="card")
    status, body = call("POST", "/api/orders/%s/cancel" % paid["id"], {"reason": "Ordered by mistake"}, asha.token)
    order = body["order"]
    assert (status, order["status"], order["payment"]["status"]) == (200, "cancelled", "refunded")
    assert order["refund"]["amount"] == paid["total"] and order["refund"]["id"].startswith("RF-")
    assert order["cancelReason"] == "Ordered by mistake"
    assert simulation.tick(later(10_000))["advanced"] == 0

    cod = asha.order(payment="cod")
    order = call("POST", "/api/orders/%s/cancel" % cod["id"], {}, asha.token)[1]["order"]
    assert (order["payment"]["status"], order["refund"]) == ("not_charged", None)


def test_an_order_that_has_shipped_cannot_be_cancelled(asha):
    order = asha.order()
    orders.advance(order["id"])
    orders.advance(order["id"])
    status, body = call("POST", "/api/orders/%s/cancel" % order["id"], {}, asha.token)
    assert (status, body["reason"]) == (409, "too-late")


def test_a_delivered_order_can_be_returned_and_then_refunded(asha, admin_token):
    order = asha.order()
    status, body = call("POST", "/api/orders/%s/return" % order["id"], {"reason": "Too small"}, asha.token)
    assert (status, body["reason"]) == (409, "not-returnable")
    deliver(order["id"])
    status, body = call("POST", "/api/orders/%s/return" % order["id"], {"reason": "Too small"}, asha.token)
    assert (body["order"]["status"], body["order"]["returnReason"]) == ("return_requested", "Too small")

    status, body = call("POST", "/api/admin/orders/%s/refund" % order["id"], {"reason": "Return accepted"}, admin_token)
    assert (status, body["order"]["status"], body["order"]["payment"]["status"]) == (200, "refunded", "refunded")
    # Asking again refunds nothing more.
    first = orders.refund(order["id"])
    assert orders.refund(order["id"]) == first
    assert first["amount"] == order["total"]


def test_only_a_delivered_paid_order_is_refunded(asha):
    in_flight = asha.order()
    try:
        orders.refund(in_flight["id"])
        raise AssertionError("an order on its way was refunded")
    except orders.OrderError as err:
        assert (err.status, err.reason) == (409, "not-refundable")


# ---- When things go wrong (the admin's switches) ----


def test_payments_down_fails_prepaid_checkouts_and_tells_the_desk(asha, admin_token, desk):
    status, body = call("PUT", "/api/admin/simulation", {"payments_down": True}, admin_token)
    assert (status, body["switches"]["payments_down"], body["status"]["payments"]) == (200, True, "failing")

    payload = {"items": [{"productId": "kurta-001", "quantity": 1}], "address": ADDRESS, "payment": "upi"}
    status, body = call("POST", "/api/orders", payload, asha.token)
    assert (status, body["reason"]) == (402, "payment-failed")
    assert "not been charged" in body["message"]
    # Nothing was created, and cash on delivery still works.
    assert call("GET", "/api/orders", token=asha.token)[1]["orders"] == []
    assert asha.order(payment="cod")["status"] == "placed"

    reports = _wait_for(lambda: desk.calls("POST", "/integration/events"))
    assert reports[0]["body"] == {
        "fingerprint": "shop.payments_failing",
        "status": "firing",
        "title": "Payments are failing at checkout",
        "severity": "critical",
        "source": "shop/checkout",
        "message": "A shopper could not pay by UPI. Cash on delivery still works.",
        "details": {"method": "upi"},
    }

    call("PUT", "/api/admin/simulation", {"payments_down": False}, admin_token)
    resolved = _wait_for(lambda: [c for c in desk.calls("POST", "/integration/events") if c["body"]["status"] == "resolved"])
    assert resolved[0]["body"]["fingerprint"] == "shop.payments_failing"
    assert asha.order(payment="upi")["payment"]["status"] == "paid"


def test_a_carrier_delay_holds_shipped_orders_and_tells_the_desk(asha, admin_token, desk):
    switches.update({"step_seconds": 30})
    with_carrier = asha.order()
    orders.advance(with_carrier["id"])
    orders.advance(with_carrier["id"])
    in_warehouse = asha.order()
    call("PUT", "/api/admin/simulation", {"carrier_delay": True}, admin_token)

    assert simulation.tick(later(31)) == {"advanced": 1, "newly_late": 1}
    late = call("GET", "/api/orders/" + with_carrier["id"], token=asha.token)[1]["order"]
    assert (late["status"], late["delayed"]) == ("shipped", True)
    assert late["events"][-1]["note"] == "Delayed with the carrier"
    # The warehouse still works: only what is with the carrier stops.
    assert orders.get(in_warehouse["id"])["status"] == "packed"
    # Still late on the next round, and said once.
    assert simulation.tick(later(62))["newly_late"] == 0

    (report,) = _wait_for(lambda: desk.calls("POST", "/integration/events"))
    assert report["body"]["fingerprint"] == "shop.shipping_delayed"
    assert report["body"]["title"] == "Orders are delayed with the carrier"
    assert report["body"]["details"] == {"carrier": "SwiftShip", "delayed_orders": 1}

    call("PUT", "/api/admin/simulation", {"carrier_delay": False}, admin_token)
    moving = orders.get(with_carrier["id"])
    assert moving["delayed"] is False and moving["events"][-1]["note"] == "Moving again"
    resolved = _wait_for(lambda: [c for c in desk.calls("POST", "/integration/events") if c["body"]["status"] == "resolved"])
    assert "1 order back on the way" in resolved[0]["body"]["message"]
    assert simulation.tick(later(120))["advanced"] >= 1


def test_the_switches_change_nothing_else_when_no_desk_is_set_up(asha, admin_token):
    call("PUT", "/api/admin/simulation", {"payments_down": True, "step_seconds": 5}, admin_token)
    state = call("GET", "/api/admin/simulation", token=admin_token)[1]
    assert state["switches"] == {"payments_down": True, "carrier_delay": False, "step_seconds": 5}
    payload = {"items": [{"productId": "kurta-001", "quantity": 1}], "address": ADDRESS, "payment": "card"}
    assert call("POST", "/api/orders", payload, asha.token)[0] == 402
    assert call("PUT", "/api/admin/simulation", {"step_seconds": 0}, admin_token)[1]["switches"]["step_seconds"] == 2


def _wait_for(check, seconds=5.0):
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(0.05)
    raise AssertionError("timed out")
