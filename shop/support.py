"""/api/support/*: the shop's side of the support desk.

The plumbing (the desk's client, the webhook receiver, the event log, the
incident reports) is shared with scraper/support. What is the shop's own is
here: requests are about orders, they belong to signed-in shoppers, and the
tools the desk's AI calls read and change orders.

Who may do what:

- A signed-in shopper raises requests as themselves (the desk knows them by
  the shop's own id for them) and reads only their own.
- A guest can still write in from the contact form; they read that one
  request back with the tracking token in its link.
- The admin reads any request, and replies to or rates none.
- The desk's AI calls /api/support/tools/* with SUPPORT_TOOL_TOKEN. Every
  order tool takes the customer's email, which the desk fills in from the
  ticket, and answers only about that customer's orders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from scraper.support import config, events, tokens
from scraper.support import routes as desk
from scraper.support.tms_support import TmsError, sign_chat_identity
from shop import catalog, orders, simulation
from shop.auth import Identity

PREFIX = desk.PREFIX
Response = Tuple[int, Dict[str, Any]]

# What a shopper can ask about an order, and the desk's category for it.
ORDER_ISSUES = {
    "where": ("Where is my order?", "Orders and delivery"),
    "cancel": ("Cancel this order", "Orders and delivery"),
    "return": ("Return or refund", "Returns and refunds"),
    "item": ("Wrong or damaged item", "Returns and refunds"),
    "payment": ("Payment problem", "Payments"),
    "other": ("Something else", None),
}
CONTACT_TOPICS = {
    "Order or delivery": "Orders and delivery",
    "Returns and refunds": "Returns and refunds",
    "Payments": "Payments",
    "Product question": "Products",
    "Site problem": "Site problem",
    "Feedback": "Feedback",
}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_REQUEST_ID = re.compile(r"^[\x21-\x7e]{8,100}$")
_REFERENCE = re.compile(r"^[A-Za-z]{2,10}-\d{1,12}$")


@dataclass
class Request(desk.Request):
    user: Optional[Identity] = None
    """Who is signed in, shopper or admin."""


def _shopper(req: Request) -> Optional[Identity]:
    return req.user if req.user and req.user.role == "shopper" else None


def _is_admin(req: Request) -> bool:
    return bool(req.user and req.user.role == "admin")


def _order_error(err: orders.OrderError) -> Response:
    return err.status, {"ok": False, "reason": err.reason, "message": err.message}


# ---- Shoppers ----


def _config(req: Request) -> Response:
    status, body = desk.desk_config(req)
    body["issues"] = [{"key": key, "label": label} for key, (label, _) in ORDER_ISSUES.items()]
    body["topics"] = list(CONTACT_TOPICS)
    return status, body


def _create_ticket(req: Request) -> Response:
    settings = config.load()
    if not settings.tickets_enabled:
        return desk.fail(503, "support-not-configured", "Support requests are not set up on this site.")
    data = req.json()
    message = desk.text(data.get("message"), 5000)
    request_id = desk.text(data.get("requestId"), 100)
    if not message:
        return desk.fail(400, "invalid", "Please write a message.")
    if not _REQUEST_ID.match(request_id):
        return desk.fail(400, "invalid", "The form is out of date. Reload the page and try again.")

    shopper = _shopper(req)
    external_ref = None
    if data.get("kind") == "order":
        if shopper is None:
            return desk.fail(401, "sign-in-required", "Sign in to get help with an order.")
        try:
            order = orders.get_for(shopper.id, desk.text(data.get("orderId"), 20))
        except orders.OrderError as err:
            return _order_error(err)
        issue_key = data.get("issue") if data.get("issue") in ORDER_ISSUES else "other"
        issue, category = ORDER_ISSUES[issue_key]
        subject = "%s Order %s" % (issue if issue.endswith("?") else issue + ":", order["id"])
        tags = ["order", issue_key]
        external_ref = order["id"]
        # The order's facts come from our own records, never from the browser.
        metadata: Dict[str, Any] = {"form": "order_help", "issue": issue}
        metadata.update({k: v for k, v in orders.facts(order).items() if v is not None})
    else:
        topic = desk.text(data.get("subject"), 100)
        if topic not in CONTACT_TOPICS:
            topic = "Feedback"
        subject = "%s: %s" % (topic, " ".join(message.split())[:80])
        category = CONTACT_TOPICS[topic]
        tags = ["contact-form"]
        metadata = {"form": "contact", "topic": topic}
        if topic == "Payments" and data.get("payment") == "failed":
            # Straight from a checkout whose payment did not go through: support's
            # priority rules and the AI's payment lookup take it from there.
            metadata["payment"] = "failed"
            tags.append("payment-failed")

    if shopper is not None:
        customer = {"externalId": shopper.id, "email": shopper.email, "name": shopper.name}
        limit_key = shopper.id
    elif _is_admin(req):
        customer = {"externalId": "admin", "name": req.user.name}
        limit_key = "admin"
    else:
        name = desk.text(data.get("name"), 200)
        email = desk.text(data.get("email"), 320)
        if not name:
            return desk.fail(400, "invalid", "Please enter your name.")
        if not _EMAIL.match(email):
            return desk.fail(400, "invalid", "Please enter a valid email address.")
        customer = {"email": email, "name": name}
        limit_key = req.client
    if not desk.limiter.allow("ticket:" + limit_key, settings.tickets_per_hour, 3600):
        return desk.fail(429, "too-many-requests", "You have sent several requests already. Please try again later.")

    client = desk.tickets_client(settings)

    def create(with_category: Optional[str]) -> Dict[str, Any]:
        return client.create_ticket(
            customer,
            subject[:300],
            message,
            category=with_category,
            tags=tags,
            external_ref=external_ref,
            metadata=metadata,
            idempotency_key="et-" + request_id,
        )

    try:
        try:
            ticket = create(category)
        except TmsError as err:
            # A category the desk does not have is left out rather than failing the request.
            if not (category and err.status == 400 and "category" in err.message.lower()):
                raise
            ticket = create(None)
    except TmsError as err:
        return desk.from_desk(err)

    reference = str(ticket.get("reference"))
    body: Dict[str, Any] = {"ok": True, "reference": reference}
    if shopper is None and not _is_admin(req):
        # A guest has no account to find the request under: the link carries its key.
        body["token"] = tokens.tracking_token(desk.tracking_secret(settings), reference)
    return 201, body


def _my_requests(req: Request) -> Response:
    shopper = _shopper(req)
    if shopper is None:
        return desk.fail(401, "sign-in-required", "Sign in to see your requests.")
    settings = config.load()
    if not settings.tickets_enabled:
        return 200, {"ok": True, "requests": []}
    try:
        page = desk.tickets_client(settings).list_tickets(customer=shopper.id, limit=50)
    except TmsError as err:
        return desk.from_desk(err)
    return 200, {
        "ok": True,
        "requests": [
            {
                "reference": t.get("reference"),
                "subject": t.get("subject"),
                "status": (t.get("status") or {}).get("name"),
                "state": (t.get("status") or {}).get("state"),
                "orderId": t.get("externalRef") if orders.ORDER_ID.match(str(t.get("externalRef") or "")) else None,
                "createdAt": t.get("createdAt"),
                "updatedAt": t.get("updatedAt"),
            }
            for t in page.get("items", [])
        ],
    }


def _load_owned(req: Request, reference: str, write: bool = False) -> Tuple[Optional[Response], Optional[Dict[str, Any]]]:
    """(refusal, ticket). The ticket is returned when it had to be read to decide."""
    settings = config.load()
    not_found = desk.fail(404, "not-found", "That request was not found.")
    if not settings.tickets_enabled:
        return desk.fail(503, "support-not-configured", "Support requests are not set up on this site."), None
    if not _REFERENCE.match(reference):
        return not_found, None
    if _is_admin(req) and not write:
        return None, None
    if tokens.verify_tracking(desk.tracking_secret(settings), reference, req.headers.get(desk.TOKEN_HEADER)):
        return None, None
    shopper = _shopper(req)
    if shopper is None:
        return not_found, None
    try:
        ticket = desk.tickets_client(settings).get_ticket(reference)
    except TmsError as err:
        return desk.from_desk(err), None
    # Someone else's request is as absent as one that does not exist.
    if (ticket.get("customer") or {}).get("externalId") != shopper.id:
        return not_found, None
    return None, ticket


def _read_request(req: Request, reference: str) -> Response:
    refusal, ticket = _load_owned(req, reference)
    if refusal:
        return refusal
    client = desk.tickets_client(config.load())
    try:
        ticket = ticket or client.get_ticket(reference)
        messages = client.messages(reference)
    except TmsError as err:
        return desk.from_desk(err)
    view = desk.request_view(ticket, messages)
    order_id = str(ticket.get("externalRef") or "")
    view["orderId"] = order_id if orders.ORDER_ID.match(order_id) else None
    view.pop("productId", None)
    view["ok"] = True
    view["version"] = events.log.version(reference)
    view["mine"] = not _is_admin(req)
    return 200, view


def _request_changes(req: Request, reference: str) -> Response:
    refusal, _ = _load_owned(req, reference)
    if refusal:
        return refusal
    return 200, {
        "ok": True,
        "version": events.log.version(reference),
        "live": bool(config.load().webhook_secret),
    }


def _reply(req: Request, reference: str) -> Response:
    refusal, _ = _load_owned(req, reference, write=True)
    if refusal:
        return refusal
    data = req.json()
    message = desk.text(data.get("message"), 5000)
    request_id = desk.text(data.get("requestId"), 100)
    if not message:
        return desk.fail(400, "invalid", "Please write a message.")
    if not _REQUEST_ID.match(request_id):
        return desk.fail(400, "invalid", "The form is out of date. Reload the page and try again.")
    who = req.user.id if req.user else req.client
    if not desk.limiter.allow("reply:" + who, 30, 3600):
        return desk.fail(429, "too-many-requests", "Please wait a little before writing again.")
    try:
        desk.tickets_client(config.load()).add_message(reference, message, idempotency_key="et-" + request_id)
    except TmsError as err:
        return desk.from_desk(err)
    return 201, {"ok": True}


def _rate(req: Request, reference: str) -> Response:
    refusal, _ = _load_owned(req, reference, write=True)
    if refusal:
        return refusal
    data = req.json()
    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    if rating < 1 or rating > 5:
        return desk.fail(400, "invalid", "Choose a rating from 1 to 5.")
    try:
        desk.tickets_client(config.load()).rate(reference, rating, desk.text(data.get("comment"), 2000) or None)
    except TmsError as err:
        return desk.from_desk(err)
    return 200, {"ok": True}


def _identity(req: Request) -> Response:
    """A signed token that tells the chat widget who is signed in, so their chat joins their requests."""
    settings = config.load()
    if req.user is None:
        return desk.fail(401, "sign-in-required", "Sign in first.")
    if not settings.chat_identity_secret:
        return 200, {"ok": True, "token": None}
    if req.user.role == "admin":
        token = sign_chat_identity(settings.chat_identity_secret, sub="admin", name=req.user.name)
    else:
        token = sign_chat_identity(
            settings.chat_identity_secret, sub=req.user.id, name=req.user.name, email=req.user.email
        )
    return 200, {"ok": True, "token": token}


# ---- Tools the support desk's AI calls ----


def _customer_email(req: Request, data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    value = (data or {}).get("customer_email") or req.query.get("customer_email")
    value = str(value or "").strip().lower()
    return value if _EMAIL.match(value) else None


def _tool_orders(req: Request) -> Response:
    email = _customer_email(req)
    if not email:
        return 400, {"message": "customer_email is required"}
    found = orders.recent_for_email(email)
    return 200, {"orders": [_tool_facts(order) for order in found], "count": len(found)}


def _tool_facts(order: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in orders.facts(order).items() if v is not None}


def _tool_order(req: Request, order_id: str) -> Response:
    email = _customer_email(req)
    if not email:
        return 400, {"message": "customer_email is required"}
    try:
        return 200, _tool_facts(orders.for_email(email, order_id))
    except orders.OrderError as err:
        return err.status, {"message": err.message}


def _tool_cancel(req: Request, order_id: str) -> Response:
    data = req.json()
    email = _customer_email(req, data)
    if not email:
        return 400, {"message": "customer_email is required"}
    try:
        orders.for_email(email, order_id)
        order = orders.cancel(orders.user_id_for_email(email), order_id, "Cancelled by support: " + desk.text(data.get("reason"), 200))
    except orders.OrderError as err:
        return err.status, {"message": err.message}
    result = {"order_id": order["id"], "status": "cancelled", "cancelled": True}
    if order["refund"]:
        result.update(refund_id=order["refund"]["id"], amount=order["refund"]["amount"], currency=order["currency"])
    return 200, result


def _tool_refund(req: Request) -> Response:
    data = req.json()
    email = _customer_email(req, data)
    order_id = desk.text(data.get("order_id"), 20)
    if not email or not order_id:
        return 400, {"message": "order_id and customer_email are required"}
    try:
        orders.for_email(email, order_id)
        return 200, orders.refund(order_id, "Refund approved by support: " + desk.text(data.get("reason"), 200))
    except orders.OrderError as err:
        return err.status, {"message": err.message}


def _tool_payments(req: Request) -> Response:
    email = _customer_email(req)
    if not email:
        return 400, {"message": "customer_email is required"}
    return 200, orders.payments_for_email(email)


def _tool_product(_: Request, product_id: str) -> Response:
    product = catalog.get(product_id)
    if product is None:
        return 404, {"message": "No product has the id %s" % product_id[:80]}
    return 200, catalog.public(product)


def _tool_search(req: Request) -> Response:
    query = desk.text(req.query.get("query"), 200)
    if not query:
        return 400, {"message": "Give a few words from the product's name"}
    return 200, {"query": query, "products": catalog.search(query)}


def _tools(req: Request, parts: list, method: str) -> Optional[Response]:
    if not desk.tool_allowed(req):
        return 401, {"message": "A valid tool token is required"}
    simple: Dict[Tuple[str, str], Callable[[], Response]] = {
        ("GET", "orders"): lambda: _tool_orders(req),
        ("GET", "payments"): lambda: _tool_payments(req),
        ("GET", "products"): lambda: _tool_search(req),
        ("GET", "shop-status"): lambda: (200, simulation.status()),
        ("POST", "refunds"): lambda: _tool_refund(req),
    }
    if len(parts) == 2 and (method, parts[1]) in simple:
        return simple[(method, parts[1])]()
    if len(parts) == 3 and parts[1] == "orders" and method == "GET":
        return _tool_order(req, parts[2])
    if len(parts) == 4 and parts[1] == "orders" and parts[3] == "cancel" and method == "POST":
        return _tool_cancel(req, parts[2])
    if len(parts) == 3 and parts[1] == "products" and method == "GET":
        return _tool_product(req, parts[2])
    return None


# ---- Dispatch ----


def handle(req: Request) -> Optional[Response]:
    """Answers a request under /api/support, or returns None when it is not one."""
    if req.path != PREFIX and not req.path.startswith(PREFIX + "/"):
        return None
    parts = [p for p in req.path[len(PREFIX) :].split("/") if p]
    method = req.method.upper()

    if parts == ["config"] and method == "GET":
        return _config(req)
    if parts == ["tickets"] and method == "POST":
        return _create_ticket(req)
    if parts == ["webhook"] and method == "POST":
        return desk.webhook(req)
    if parts == ["identity"] and method == "GET":
        return _identity(req)
    if parts == ["requests"] and method == "GET":
        return _my_requests(req)

    if parts[:1] == ["requests"] and len(parts) >= 2:
        reference = parts[1].upper()
        if len(parts) == 2 and method == "GET":
            return _read_request(req, reference)
        if parts[2:] == ["changes"] and method == "GET":
            return _request_changes(req, reference)
        if parts[2:] == ["messages"] and method == "POST":
            return _reply(req, reference)
        if parts[2:] == ["rating"] and method == "POST":
            return _rate(req, reference)

    if parts[:1] == ["tools"]:
        answer = _tools(req, parts, method)
        if answer is not None:
            return answer

    if parts == ["admin", "overview"] and method == "GET":
        if not _is_admin(req):
            return desk.fail(401, "sign-in-required", "Sign in as the admin to see this.")
        return desk.overview(req)

    return desk.fail(404, "not-found", "There is nothing at this address.")
