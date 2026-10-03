"""Orders: placing them, reading them, and what can happen to them afterwards.

An order moves placed → packed → shipped → out for delivery → delivered on
the simulation's clock (simulation.py). Before it ships it can be cancelled;
after delivery it can be returned and refunded. No money moves anywhere:
"paid" and "refunded" are states of the order.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from shop import catalog, db, switches

FLOW = ("placed", "packed", "shipped", "out_for_delivery", "delivered")
LABELS = {
    "placed": "Order placed",
    "packed": "Packed",
    "shipped": "Shipped",
    "out_for_delivery": "Out for delivery",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
    "return_requested": "Return requested",
    "refunded": "Refunded",
}
DELIVERY = {
    "standard": {"label": "Standard delivery", "fee": 49.0, "free_over": 499.0, "days": 4},
    "express": {"label": "Express delivery", "fee": 99.0, "free_over": None, "days": 2},
}
PAYMENTS = {"cod": "Cash on delivery", "upi": "UPI", "card": "Card"}
PAYMENT_STATUS = {
    "paid": "Paid",
    "pay_on_delivery": "Pay on delivery",
    "not_charged": "Not charged",
    "refunded": "Refunded",
}
# How support says where an order is: "Order ET-100001 is <this>".
STATUS_WORDS = {
    "placed": "confirmed and being prepared",
    "packed": "packed and waiting for the carrier",
    "shipped": "shipped",
    "out_for_delivery": "out for delivery",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "return_requested": "waiting for its return to be approved",
    "refunded": "returned and refunded",
}
# An invented carrier: nothing is handed to a real one.
CARRIER = "SwiftShip"
CURRENCY = "INR"
MAX_LINES = 20
MAX_QUANTITY = 5
RETURN_DAYS = 7
REFUND_ARRIVES_IN = "5 to 7 business days"
SIZES = ("S", "M", "L", "XL", "XXL", "Free size")

ORDER_ID = re.compile(r"^ET-\d{6,9}$")


class OrderError(Exception):
    def __init__(self, status: int, reason: str, message: str):
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.message = message


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _address(raw: Any) -> Dict[str, str]:
    raw = raw if isinstance(raw, dict) else {}
    address = {
        "name": _clean(raw.get("name"), 80),
        "phone": re.sub(r"[^\d+]", "", str(raw.get("phone") or ""))[:16],
        "line1": _clean(raw.get("line1"), 120),
        "line2": _clean(raw.get("line2"), 120),
        "city": _clean(raw.get("city"), 60),
        "state": _clean(raw.get("state"), 60),
        "pincode": re.sub(r"\D", "", str(raw.get("pincode") or ""))[:6],
    }
    if not address["name"]:
        raise OrderError(400, "invalid", "Enter the name of the person receiving the order.")
    if len(re.sub(r"\D", "", address["phone"])) < 10:
        raise OrderError(400, "invalid", "Enter a phone number with at least 10 digits.")
    if not address["line1"] or not address["city"] or not address["state"]:
        raise OrderError(400, "invalid", "Enter the full delivery address.")
    if len(address["pincode"]) != 6:
        raise OrderError(400, "invalid", "Enter a 6-digit PIN code.")
    return address


def _lines(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise OrderError(400, "empty-cart", "Your cart is empty.")
    if len(raw) > MAX_LINES:
        raise OrderError(400, "invalid", "An order can have at most %d different items." % MAX_LINES)
    lines = []
    for entry in raw:
        entry = entry if isinstance(entry, dict) else {}
        product = catalog.get(entry.get("productId"))
        if product is None:
            raise OrderError(409, "unavailable", "An item in your cart is no longer available. Remove it and try again.")
        price = catalog.price(product)
        if price is None:
            raise OrderError(409, "unavailable", "%s has no price at the moment." % _clean(product.get("title"), 60))
        if product.get("in_stock") is False:
            raise OrderError(409, "sold-out", "%s is sold out." % _clean(product.get("title"), 60))
        try:
            quantity = int(entry.get("quantity"))
        except (TypeError, ValueError):
            quantity = 0
        if quantity < 1 or quantity > MAX_QUANTITY:
            raise OrderError(400, "invalid", "You can order 1 to %d of each item." % MAX_QUANTITY)
        size = entry.get("size") if entry.get("size") in SIZES else None
        lines.append({"product": product, "price": price, "quantity": quantity, "size": size})
    return lines


def shipping_fee(option: str, subtotal: float) -> float:
    rule = DELIVERY[option]
    if rule["free_over"] is not None and subtotal >= rule["free_over"]:
        return 0.0
    return rule["fee"]


def quote(payload: Dict[str, Any]) -> Dict[str, Any]:
    """What an order would cost, from the catalogue's prices (never the browser's)."""
    option = payload.get("delivery") if payload.get("delivery") in DELIVERY else "standard"
    lines = _lines(payload.get("items"))
    subtotal = round(sum(l["price"] * l["quantity"] for l in lines), 2)
    fee = shipping_fee(option, subtotal)
    return {
        "subtotal": subtotal,
        "shippingFee": fee,
        "total": round(subtotal + fee, 2),
        "currency": CURRENCY,
        "delivery": option,
        "items": [
            {
                "productId": str(l["product"]["id"]),
                "title": l["product"].get("title"),
                "price": l["price"],
                "quantity": l["quantity"],
                "size": l["size"],
            }
            for l in lines
        ],
    }


def _next_order_id(conn: sqlite3.Connection) -> str:
    number = int(db.get_setting(conn, "order_seq", "100000") or 100000) + 1
    db.set_setting(conn, "order_seq", str(number))
    return "ET-%d" % number


def _event(conn: sqlite3.Connection, order_id: str, status: str, note: str = "", at: Optional[str] = None) -> None:
    conn.execute(
        "INSERT INTO order_events(order_id, status, note, at) VALUES(?,?,?,?)",
        (order_id, status, note, at or db.iso()),
    )


def place(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Places an order. Raises OrderError: bad input, or a payment that does not go through."""
    payload = payload if isinstance(payload, dict) else {}
    option = payload.get("delivery") if payload.get("delivery") in DELIVERY else "standard"
    method = payload.get("payment")
    if method not in PAYMENTS:
        raise OrderError(400, "invalid", "Choose how you want to pay.")
    lines = _lines(payload.get("items"))
    address = _address(payload.get("address"))
    subtotal = round(sum(l["price"] * l["quantity"] for l in lines), 2)
    fee = shipping_fee(option, subtotal)
    total = round(subtotal + fee, 2)

    with db.write() as conn:
        state = switches.read(conn)
        if method != "cod" and state["payments_down"]:
            # Nothing is created: the shopper is told, and the caller reports the failure.
            raise OrderError(
                402,
                "payment-failed",
                "Your payment could not be completed, and you have not been charged. "
                "Please try again in a little while, or choose Cash on delivery.",
            )
        placed = db.now()
        order_id = _next_order_id(conn)
        conn.execute(
            """INSERT INTO orders(id, user_id, status, placed_at, updated_at, address, delivery_option,
                 payment_method, payment_status, subtotal, shipping_fee, total, expected_delivery, next_step_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                order_id,
                user_id,
                "placed",
                db.iso(placed),
                db.iso(placed),
                json.dumps(address),
                option,
                method,
                "pay_on_delivery" if method == "cod" else "paid",
                subtotal,
                fee,
                total,
                (placed + timedelta(days=DELIVERY[option]["days"])).date().isoformat(),
                db.iso(placed + timedelta(seconds=state["step_seconds"])),
            ),
        )
        for index, line in enumerate(lines):
            product = line["product"]
            conn.execute(
                """INSERT INTO order_items(order_id, line, product_id, title, brand, image_url, size, price, quantity)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    order_id,
                    index,
                    str(product["id"]),
                    _clean(product.get("title"), 300),
                    product.get("brand"),
                    product.get("image_url"),
                    line["size"],
                    line["price"],
                    line["quantity"],
                ),
            )
        _event(conn, order_id, "placed", at=db.iso(placed))
        if payload.get("saveAddress"):
            _save_address(conn, user_id, address)
        return _view(conn, _row(conn, order_id))


def _save_address(conn: sqlite3.Connection, user_id: str, address: Dict[str, str]) -> None:
    same = conn.execute(
        "SELECT 1 FROM addresses WHERE user_id = ? AND line1 = ? AND pincode = ? AND name = ?",
        (user_id, address["line1"], address["pincode"], address["name"]),
    ).fetchone()
    if same:
        return
    conn.execute(
        """INSERT INTO addresses(id, user_id, name, phone, line1, line2, city, state, pincode, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            "a" + secrets.token_hex(6),
            user_id,
            address["name"],
            address["phone"],
            address["line1"],
            address["line2"],
            address["city"],
            address["state"],
            address["pincode"],
            db.iso(),
        ),
    )


def addresses(user_id: str) -> List[Dict[str, Any]]:
    with db.read() as conn:
        rows = conn.execute(
            "SELECT * FROM addresses WHERE user_id = ? ORDER BY created_at DESC LIMIT 10", (user_id,)
        ).fetchall()
    keys = ("id", "name", "phone", "line1", "line2", "city", "state", "pincode")
    return [{key: row[key] for key in keys} for row in rows]


def _row(conn: sqlite3.Connection, order_id: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM orders WHERE id = ?", (str(order_id).upper(),)).fetchone()


def _returnable(conn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    if row["status"] != "delivered":
        return False
    delivered = conn.execute(
        "SELECT at FROM order_events WHERE order_id = ? AND status = 'delivered' ORDER BY id LIMIT 1",
        (row["id"],),
    ).fetchone()
    if not delivered:
        return True
    return db.now() - datetime.fromisoformat(delivered["at"]) <= timedelta(days=RETURN_DAYS)


def _view(conn: sqlite3.Connection, row: sqlite3.Row, admin: bool = False) -> Dict[str, Any]:
    items = conn.execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY line", (row["id"],)).fetchall()
    events = conn.execute("SELECT * FROM order_events WHERE order_id = ? ORDER BY id", (row["id"],)).fetchall()
    reached = {}
    for event in events:
        reached.setdefault(event["status"], event["at"])
    status = row["status"]
    position = FLOW.index(status) if status in FLOW else max(
        (FLOW.index(s) for s in reached if s in FLOW), default=0
    )
    view: Dict[str, Any] = {
        "id": row["id"],
        "status": status,
        "statusLabel": LABELS[status],
        "placedAt": row["placed_at"],
        "updatedAt": row["updated_at"],
        "items": [
            {
                "productId": item["product_id"],
                "title": item["title"],
                "brand": item["brand"],
                "imageUrl": item["image_url"],
                "size": item["size"],
                "price": item["price"],
                "quantity": item["quantity"],
            }
            for item in items
        ],
        "itemCount": sum(item["quantity"] for item in items),
        "address": json.loads(row["address"]),
        "delivery": {
            "option": row["delivery_option"],
            "label": DELIVERY[row["delivery_option"]]["label"],
            "expected": row["expected_delivery"],
            "carrier": row["carrier"],
            "trackingNumber": row["tracking_number"],
        },
        "payment": {
            "method": row["payment_method"],
            "label": PAYMENTS[row["payment_method"]],
            "status": row["payment_status"],
            "statusLabel": PAYMENT_STATUS[row["payment_status"]],
        },
        "subtotal": row["subtotal"],
        "shippingFee": row["shipping_fee"],
        "total": row["total"],
        "currency": CURRENCY,
        "delayed": bool(row["delayed"]),
        "timeline": [
            {
                "key": step,
                "label": LABELS[step],
                "at": reached.get(step),
                "done": step in reached,
                "current": status in FLOW and index == position,
            }
            for index, step in enumerate(FLOW)
        ],
        "events": [
            {"status": e["status"], "label": LABELS.get(e["status"], e["status"]), "note": e["note"], "at": e["at"]}
            for e in events
        ],
        "canCancel": status in ("placed", "packed"),
        "canReturn": _returnable(conn, row),
        "refund": (
            {"id": row["refund_id"], "amount": row["refund_amount"], "at": row["refunded_at"], "arrivesIn": REFUND_ARRIVES_IN}
            if row["refund_id"]
            else None
        ),
        "cancelReason": row["cancel_reason"],
        "returnReason": row["return_reason"],
    }
    if admin:
        view["held"] = bool(row["held"])
        view["nextStepAt"] = row["next_step_at"]
        customer = conn.execute("SELECT name, email FROM users WHERE id = ?", (row["user_id"],)).fetchone()
        view["customer"] = {"name": customer["name"], "email": customer["email"]} if customer else None
    return view


def list_for(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    with db.read() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY placed_at DESC, id DESC LIMIT ?", (user_id, limit)
        ).fetchall()
        return [_view(conn, row) for row in rows]


def get_for(user_id: str, order_id: str) -> Dict[str, Any]:
    """The order, if it is this shopper's. Someone else's order is as absent as one that does not exist."""
    with db.read() as conn:
        row = _row(conn, order_id)
        if row is None or row["user_id"] != user_id:
            raise OrderError(404, "not-found", "We could not find that order.")
        return _view(conn, row)


def get(order_id: str) -> Dict[str, Any]:
    with db.read() as conn:
        row = _row(conn, order_id)
        if row is None:
            raise OrderError(404, "not-found", "We could not find that order.")
        return _view(conn, row, admin=True)


def admin_list(limit: int = 50) -> List[Dict[str, Any]]:
    with db.read() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY placed_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [_view(conn, row, admin=True) for row in rows]


def _owned(conn: sqlite3.Connection, user_id: Optional[str], order_id: str) -> sqlite3.Row:
    row = _row(conn, order_id)
    if row is None or (user_id is not None and row["user_id"] != user_id):
        raise OrderError(404, "not-found", "We could not find that order.")
    return row


def _refund_now(conn: sqlite3.Connection, row: sqlite3.Row, status: str, note: str) -> None:
    conn.execute(
        """UPDATE orders SET status = ?, payment_status = 'refunded', refund_id = ?, refund_amount = ?,
             refunded_at = ?, next_step_at = NULL, delayed = 0, updated_at = ? WHERE id = ?""",
        (status, "RF-%06d" % secrets.randbelow(1_000_000), row["total"], db.iso(), db.iso(), row["id"]),
    )
    _event(conn, row["id"], "refunded", note)


def cancel(user_id: Optional[str], order_id: str, reason: str = "") -> Dict[str, Any]:
    """Cancels an order that has not shipped. What was paid is refunded at once."""
    with db.write() as conn:
        row = _owned(conn, user_id, order_id)
        if row["status"] == "cancelled":
            return _view(conn, row)
        if row["status"] not in ("placed", "packed"):
            raise OrderError(
                409,
                "too-late",
                "This order has already shipped, so it cannot be cancelled. You can return it once it is delivered.",
            )
        conn.execute(
            "UPDATE orders SET status = 'cancelled', cancel_reason = ?, next_step_at = NULL, updated_at = ? WHERE id = ?",
            (_clean(reason, 300) or None, db.iso(), row["id"]),
        )
        _event(conn, row["id"], "cancelled", _clean(reason, 300))
        if row["payment_status"] == "paid":
            _refund_now(conn, row, "cancelled", "Refunded in full after cancellation")
        else:
            conn.execute("UPDATE orders SET payment_status = 'not_charged' WHERE id = ?", (row["id"],))
        return _view(conn, _row(conn, row["id"]))


def request_return(user_id: Optional[str], order_id: str, reason: str = "") -> Dict[str, Any]:
    with db.write() as conn:
        row = _owned(conn, user_id, order_id)
        if row["status"] == "return_requested":
            return _view(conn, row)
        if not _returnable(conn, row):
            raise OrderError(
                409,
                "not-returnable",
                "Only delivered orders can be returned, within %d days of delivery." % RETURN_DAYS,
            )
        conn.execute(
            "UPDATE orders SET status = 'return_requested', return_reason = ?, updated_at = ? WHERE id = ?",
            (_clean(reason, 300) or None, db.iso(), row["id"]),
        )
        _event(conn, row["id"], "return_requested", _clean(reason, 300))
        return _view(conn, _row(conn, row["id"]))


def refund(order_id: str, reason: str = "", user_id: Optional[str] = None) -> Dict[str, Any]:
    """Refunds a delivered (or returned) order in full. Asking twice refunds once."""
    with db.write() as conn:
        row = _owned(conn, user_id, order_id)
        if not row["refund_id"]:
            if row["status"] not in ("delivered", "return_requested"):
                raise OrderError(
                    409,
                    "not-refundable",
                    "This order is %s. An order is refunded when it is cancelled before it ships, "
                    "or returned after delivery." % LABELS[row["status"]].lower(),
                )
            if row["payment_status"] != "paid":
                raise OrderError(409, "not-refundable", "Nothing has been paid for this order.")
            _refund_now(conn, row, "refunded", _clean(reason, 300))
            row = _row(conn, row["id"])
        return {
            "refund_id": row["refund_id"],
            "order_id": row["id"],
            "amount": row["refund_amount"],
            "currency": CURRENCY,
            "arrives_in": REFUND_ARRIVES_IN,
        }


def set_hold(order_id: str, held: bool) -> Dict[str, Any]:
    with db.write() as conn:
        row = _owned(conn, None, order_id)
        conn.execute("UPDATE orders SET held = ?, updated_at = ? WHERE id = ?", (1 if held else 0, db.iso(), row["id"]))
        return _view(conn, _row(conn, row["id"]), admin=True)


def step(conn: sqlite3.Connection, row: sqlite3.Row, step_seconds: int, at: Optional[datetime] = None) -> Optional[str]:
    """Moves an order one step along. Returns the new status, or None at the end of the line."""
    if row["status"] not in FLOW or row["status"] == "delivered":
        return None
    moment = at or db.now()
    new_status = FLOW[FLOW.index(row["status"]) + 1]
    changes = {
        "status": new_status,
        "updated_at": db.iso(moment),
        "delayed": 0,
        "next_step_at": None if new_status == "delivered" else db.iso(moment + timedelta(seconds=step_seconds)),
    }
    if new_status == "shipped":
        changes["carrier"] = CARRIER
        changes["tracking_number"] = "SW%09d" % secrets.randbelow(1_000_000_000)
    if new_status == "delivered" and row["payment_status"] == "pay_on_delivery":
        changes["payment_status"] = "paid"
    conn.execute(
        "UPDATE orders SET %s WHERE id = ?" % ", ".join("%s = ?" % key for key in changes),
        (*changes.values(), row["id"]),
    )
    _event(conn, row["id"], new_status, at=db.iso(moment))
    return new_status


def advance(order_id: str) -> Dict[str, Any]:
    """The admin pushes an order to its next step now."""
    with db.write() as conn:
        row = _owned(conn, None, order_id)
        if step(conn, row, switches.read(conn)["step_seconds"]) is None:
            raise OrderError(409, "final", "This order is %s: there is no next step." % LABELS[row["status"]].lower())
        return _view(conn, _row(conn, row["id"]), admin=True)


# ---- What the support desk is told ----


def facts(order: Dict[str, Any]) -> Dict[str, Any]:
    """An order as plain facts: the context of a support ticket, and what the AI's order tool returns."""
    titles = [item["title"] for item in order["items"]]
    return {
        "order_id": order["id"],
        "status": STATUS_WORDS[order["status"]],
        "placed_at": order["placedAt"],
        "estimated_delivery": order["delivery"]["expected"],
        "delayed": order["delayed"],
        "carrier": order["delivery"]["carrier"],
        "tracking_number": order["delivery"]["trackingNumber"],
        "total": order["total"],
        "currency": order["currency"],
        "payment_method": order["payment"]["label"],
        "payment_status": order["payment"]["statusLabel"].lower(),
        "items": "; ".join("%s x%d" % (item["title"][:60], item["quantity"]) for item in order["items"][:5]),
        "item_count": order["itemCount"],
        "first_item": titles[0][:80] if titles else None,
        "can_cancel": order["canCancel"],
        "can_return": order["canReturn"],
        "refund_id": order["refund"]["id"] if order["refund"] else None,
    }


def for_email(email: str, order_id: str) -> Dict[str, Any]:
    """An order, if it belongs to the shopper with this email. Raises OrderError(404) otherwise."""
    with db.read() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (str(email or "").strip().lower(),)).fetchone()
        row = _row(conn, order_id)
        if user is None or row is None or row["user_id"] != user["id"]:
            raise OrderError(404, "not-found", "This customer has no order with that number.")
        return _view(conn, row)


def recent_for_email(email: str, limit: int = 5) -> List[Dict[str, Any]]:
    with db.read() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (str(email or "").strip().lower(),)).fetchone()
        if user is None:
            return []
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY placed_at DESC, id DESC LIMIT ?", (user["id"], limit)
        ).fetchall()
        return [_view(conn, row) for row in rows]


def record_failed_payment(user_id: str, payload: Dict[str, Any]) -> None:
    """Keeps a failed checkout for support: the method and the amount, never a payment detail."""
    payload = payload if isinstance(payload, dict) else {}
    try:
        option = payload.get("delivery") if payload.get("delivery") in DELIVERY else "standard"
        subtotal = round(sum(l["price"] * l["quantity"] for l in _lines(payload.get("items"))), 2)
        amount = round(subtotal + shipping_fee(option, subtotal), 2)
    except OrderError:
        amount = 0.0
    with db.write() as conn:
        conn.execute(
            "INSERT INTO payment_attempts(user_id, method, amount, failed_at) VALUES(?,?,?,?)",
            (user_id, str(payload.get("payment") or "")[:20], amount, db.iso()),
        )


def payments_for_email(email: str, limit: int = 10) -> Dict[str, Any]:
    """What support may tell a shopper about their payments: failed checkouts, and how their orders were paid."""
    with db.read() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (str(email or "").strip().lower(),)).fetchone()
        if user is None:
            return {"failed_payments": [], "orders": [], "note": "No account has this email address."}
        failed = conn.execute(
            "SELECT method, amount, failed_at FROM payment_attempts WHERE user_id = ? ORDER BY failed_at DESC LIMIT ?",
            (user["id"], limit),
        ).fetchall()
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY placed_at DESC, id DESC LIMIT ?", (user["id"], limit)
        ).fetchall()
        paid = [_view(conn, row) for row in rows]
    return {
        "failed_payments": [
            {
                "method": f["method"],
                "amount": f["amount"],
                "failed_at": f["failed_at"],
                "charged": False,
                "order_created": False,
            }
            for f in failed
        ],
        "orders": [
            {
                k: v
                for k, v in {
                    "order_id": o.get("id"),
                    "status": o.get("status"),
                    "payment_method": (o.get("payment") or {}).get("label"),
                    "payment_status": (o.get("payment") or {}).get("statusLabel"),
                    "total": o.get("total"),
                    "refund": o.get("refund"),
                }.items()
                if v is not None
            }
            for o in paid
        ],
        "note": "A failed payment creates no order and charges nothing. Each order is paid once.",
    }


def user_id_for_email(email: str) -> Optional[str]:
    with db.read() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (str(email or "").strip().lower(),)).fetchone()
    return user["id"] if user else None
