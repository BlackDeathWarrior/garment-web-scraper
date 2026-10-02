"""The worker's /api/support/* endpoints.

Three audiences, three ways in:

- Shoppers, from the storefront. The browser never holds an API key: it asks
  this worker, and the worker calls the support desk. A request is read back
  only with the tracking token handed out when it was made.
- The support desk. Its webhooks are verified by signature; its AI's tool
  calls carry SUPPORT_TOOL_TOKEN.
- The admin, with the session token from /api/auth/login.

`handle` is plain data in, plain data out, so it is tested without a server.
"""

from __future__ import annotations

import hmac
import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from scraper.support import catalog, config, events, tokens
from scraper.support.tms_support import (
    SIGNATURE_HEADER,
    TmsClient,
    TmsError,
    sign_chat_identity,
    verify_webhook_signature,
)

PREFIX = "/api/support"
MAX_BODY_BYTES = 256 * 1024
TOKEN_HEADER = "x-request-token"
VALID_SOURCES = ("amazon", "flipkart", "myntra")

# What the contact form's topics are called on the support desk. A category
# the desk does not have is left out rather than failing the request.
CONTACT_CATEGORIES = {
    "Bug Report": "Site problem",
    "Feature Suggestion": "Feedback",
    "General Feedback": "Feedback",
}
LISTING_CATEGORY = "Listings"
LISTING_ISSUES = {
    "wrong-price": "Wrong price",
    "out-of-stock": "Out of stock",
    "broken-link": "Broken link",
    "wrong-details": "Wrong details",
    "other": "Something else",
}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_REQUEST_ID = re.compile(r"^[\x21-\x7e]{8,100}$")
_REFERENCE = re.compile(r"^[A-Za-z]{2,10}-\d{1,12}$")

Response = Tuple[int, Dict[str, Any]]


@dataclass
class Request:
    method: str
    path: str
    query: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    """Header names in lower case."""
    raw_body: bytes = b""
    client: str = "unknown"
    admin: Optional[str] = None
    """The admin's username, when the request carries a valid session."""

    def json(self) -> Dict[str, Any]:
        if not self.raw_body:
            return {}
        try:
            parsed = json.loads(self.raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def bearer(self) -> Optional[str]:
        value = self.headers.get("authorization") or ""
        return value[7:].strip() if value.lower().startswith("bearer ") else None


class _Limiter:
    """A sliding window per key, in memory: enough for one worker process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = _Limiter()


def _fail(status: int, reason: str, message: str) -> Response:
    return status, {"ok": False, "reason": reason, "message": message}


def _from_desk(err: TmsError) -> Response:
    """Turns a refusal from the support desk into this API's answer."""
    if err.status == 0:
        return _fail(502, "support-unreachable", "The support desk could not be reached. Please try again.")
    if err.status == 429:
        status, body = _fail(429, "too-many-requests", "Too many requests. Please try again in a minute.")
        body["retry_after"] = err.retry_after
        return status, body
    if err.status == 404:
        return _fail(404, "not-found", "That request was not found.")
    if err.status in (400, 409, 422):
        return _fail(err.status, "refused", err.message)
    return _fail(502, "support-error", "The support desk could not take the request. Please try again.")


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _tracking_secret(settings: config.SupportConfig) -> Optional[str]:
    return settings.tracking_secret or settings.web_key


def _tickets_client(settings: config.SupportConfig) -> TmsClient:
    return TmsClient(settings.api_url or "", settings.web_key or "", timeout=8.0)


# ---- Shoppers ----


def _config(_: Request) -> Response:
    settings = config.load()
    widget = None
    origin = (settings.widget_url or settings.api_url or "").rstrip("/")
    if origin:
        widget = {
            "script": origin + "/widget/tms-chat.js",
            "server": origin,
            "integration": settings.integration,
        }
    return 200, {
        "ok": True,
        "tickets": settings.tickets_enabled,
        "widget": widget,
        "issues": [{"key": key, "label": label} for key, label in LISTING_ISSUES.items()],
    }


def _create_ticket(req: Request) -> Response:
    settings = config.load()
    if not settings.tickets_enabled:
        return _fail(503, "support-not-configured", "Support requests are not set up on this site.")
    data = req.json()
    kind = "listing" if data.get("kind") == "listing" else "contact"
    name = _text(data.get("name"), 200)
    email = _text(data.get("email"), 320)
    message = _text(data.get("message"), 5000)
    request_id = _text(data.get("requestId"), 100)
    if not name:
        return _fail(400, "invalid", "Please enter your name.")
    if not _EMAIL.match(email):
        return _fail(400, "invalid", "Please enter a valid email address.")
    if not message:
        return _fail(400, "invalid", "Please write a message.")
    if not _REQUEST_ID.match(request_id):
        return _fail(400, "invalid", "The form is out of date. Reload the page and try again.")

    metadata: Dict[str, Any]
    external_ref = None
    if kind == "listing":
        product = catalog.find(_text(data.get("productId"), 200))
        if product is None:
            return _fail(404, "unknown-product", "That listing is no longer in the catalogue.")
        issue_key = data.get("issue") if data.get("issue") in LISTING_ISSUES else "other"
        issue = LISTING_ISSUES[issue_key]
        subject = "%s: %s" % (issue, _text(product.get("title"), 200))
        category = LISTING_CATEGORY
        tags = ["listing", issue_key]
        external_ref = str(product["id"])
        # Facts about the listing come from our own catalogue, never from the browser.
        metadata = {"form": "listing_report", "issue": issue}
        metadata.update({("product_id" if k == "id" else k): v for k, v in product.items()})
    else:
        topic = _text(data.get("subject"), 100) or "General Feedback"
        subject = "%s: %s" % (topic, " ".join(message.split())[:80])
        category = CONTACT_CATEGORIES.get(topic)
        tags = ["contact-form"]
        metadata = {"form": "contact", "topic": topic}

    if not limiter.allow("ticket:" + req.client, settings.tickets_per_hour, 3600):
        return _fail(429, "too-many-requests", "You have sent several requests already. Please try again later.")

    # The admin is a known user of this app; a shopper is whoever the email says.
    customer = {"email": email, "name": name}
    if req.admin:
        customer["externalId"] = "admin"

    client = _tickets_client(settings)

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
            if not (category and err.status == 400 and "category" in err.message.lower()):
                raise
            ticket = create(None)
    except TmsError as err:
        return _from_desk(err)

    reference = str(ticket.get("reference"))
    return 201, {
        "ok": True,
        "reference": reference,
        "token": tokens.tracking_token(_tracking_secret(settings), reference),
    }


def _owned(req: Request, reference: str, write: bool = False) -> Optional[Response]:
    """None when the caller may read (or, with `write`, answer) this request; otherwise the refusal.

    The admin may read any request. Writing on it (a reply, a rating) is the
    shopper's alone: it is said in their name.
    """
    settings = config.load()
    if not settings.tickets_enabled:
        return _fail(503, "support-not-configured", "Support requests are not set up on this site.")
    if not _REFERENCE.match(reference):
        return _fail(404, "not-found", "That request was not found.")
    if req.admin and not write:
        return None
    if not tokens.verify_tracking(_tracking_secret(settings), reference, req.headers.get(TOKEN_HEADER)):
        # The same answer as for a reference that does not exist.
        return _fail(404, "not-found", "That request was not found.")
    return None


def _request_view(ticket: Dict[str, Any], messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    status = ticket.get("status") or {}
    return {
        "reference": ticket.get("reference"),
        "subject": ticket.get("subject"),
        "status": status.get("name"),
        "state": status.get("state"),
        "createdAt": ticket.get("createdAt"),
        "updatedAt": ticket.get("updatedAt"),
        "productId": ticket.get("externalRef"),
        "messages": [
            {
                "id": m.get("id"),
                "from": m.get("from"),
                "name": m.get("name"),
                "body": m.get("body"),
                "createdAt": m.get("createdAt"),
            }
            for m in messages
        ],
    }


def _read_request(req: Request, reference: str) -> Response:
    refusal = _owned(req, reference)
    if refusal:
        return refusal
    client = _tickets_client(config.load())
    try:
        ticket = client.get_ticket(reference)
        messages = client.messages(reference)
    except TmsError as err:
        return _from_desk(err)
    view = _request_view(ticket, messages)
    view["ok"] = True
    view["version"] = events.log.version(reference)
    return 200, view


def _request_changes(req: Request, reference: str) -> Response:
    """Cheap to poll: answered from what the webhooks told us, without calling the desk."""
    refusal = _owned(req, reference)
    if refusal:
        return refusal
    settings = config.load()
    return 200, {
        "ok": True,
        "version": events.log.version(reference),
        "live": bool(settings.webhook_secret),
    }


def _reply(req: Request, reference: str) -> Response:
    refusal = _owned(req, reference, write=True)
    if refusal:
        return refusal
    data = req.json()
    message = _text(data.get("message"), 5000)
    request_id = _text(data.get("requestId"), 100)
    if not message:
        return _fail(400, "invalid", "Please write a message.")
    if not _REQUEST_ID.match(request_id):
        return _fail(400, "invalid", "The form is out of date. Reload the page and try again.")
    if not limiter.allow("reply:" + req.client, 30, 3600):
        return _fail(429, "too-many-requests", "Please wait a little before writing again.")
    try:
        _tickets_client(config.load()).add_message(reference, message, idempotency_key="et-" + request_id)
    except TmsError as err:
        return _from_desk(err)
    return 201, {"ok": True}


def _rate(req: Request, reference: str) -> Response:
    refusal = _owned(req, reference, write=True)
    if refusal:
        return refusal
    data = req.json()
    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    if rating < 1 or rating > 5:
        return _fail(400, "invalid", "Choose a rating from 1 to 5.")
    comment = _text(data.get("comment"), 2000) or None
    try:
        _tickets_client(config.load()).rate(reference, rating, comment)
    except TmsError as err:
        return _from_desk(err)
    return 200, {"ok": True}


# ---- The support desk calling us ----


def _webhook(req: Request) -> Response:
    settings = config.load()
    if not settings.webhook_secret:
        return _fail(503, "webhooks-not-configured", "No webhook secret is set.")
    if not verify_webhook_signature(req.raw_body, req.headers.get(SIGNATURE_HEADER.lower()), settings.webhook_secret):
        return _fail(401, "bad-signature", "The signature does not match.")
    payload = req.json()
    if not payload.get("id"):
        return _fail(400, "invalid", "The event has no id.")
    stored = events.log.record(payload)
    return 200, {"ok": True, "duplicate": not stored}


def _tool_allowed(req: Request) -> bool:
    expected = config.load().tool_token
    given = req.bearer()
    return bool(expected and given) and hmac.compare_digest(expected.encode("utf-8"), given.encode("utf-8"))


def _tool_scrape_status(_: Request, worker: Any) -> Response:
    status = worker.status()
    return 200, {
        "running": status.get("running"),
        "last_started_at": status.get("last_started_at"),
        "last_ended_at": status.get("last_ended_at"),
        "last_exit_code": status.get("last_exit_code"),
        "last_error": status.get("last_error"),
        "stopped_by_admin": status.get("last_stopped_by_user"),
        "sources": status.get("sources"),
    }


def _tool_log_tail(req: Request, worker: Any) -> Response:
    try:
        wanted = int(req.query.get("lines") or 30)
    except ValueError:
        wanted = 30
    lines = worker.log_tail(max(1, min(wanted, 100)))
    return 200, {"lines": [line[:300] for line in lines]}


def _tool_product(_: Request, product_id: str) -> Response:
    product = catalog.find(product_id)
    if product is None:
        return 404, {"message": "No listing has the id %s" % product_id[:80]}
    return 200, product


def _tool_search(req: Request) -> Response:
    query = _text(req.query.get("query"), 200)
    if not query:
        return 400, {"message": "Give a few words from the listing's title"}
    return 200, {"query": query, "listings": catalog.search(query)}


def _tool_catalog_status(_: Request) -> Response:
    return 200, catalog.status(config.load().stale_hours)


def _tool_rescrape(req: Request, worker: Any) -> Response:
    data = req.json()
    source = _text(data.get("source"), 20).lower() or None
    if source and source not in VALID_SOURCES:
        return 400, {"message": "source must be one of: %s" % ", ".join(VALID_SOURCES)}
    reason = "support-desk"
    if data.get("reason"):
        reason += ": " + " ".join(_text(data.get("reason"), 120).split())
    status, payload = worker.trigger(reason=reason, sources=source)
    if status == 409:
        return 409, {"message": "A scrape is already running", "started_at": payload.get("last_started_at")}
    if status >= 400:
        return 502, {"message": "The scrape could not be started: %s" % (payload.get("last_error") or "unknown error")}
    return 202, {
        "started": True,
        "started_at": payload.get("last_started_at"),
        "sources": payload.get("sources"),
        "note": "The scrape runs in the background; new prices appear on the site as each store finishes.",
    }


# ---- The admin ----


def _identity(req: Request) -> Response:
    settings = config.load()
    if not settings.chat_identity_secret:
        return 200, {"ok": True, "token": None}
    token = sign_chat_identity(settings.chat_identity_secret, sub="admin", name=req.admin)
    return 200, {"ok": True, "token": token}


def _overview(_: Request) -> Response:
    settings = config.load()
    overview: Dict[str, Any] = {
        "ok": True,
        "configured": {
            "tickets": settings.tickets_enabled,
            "incidents": settings.incidents_enabled,
            "webhooks": bool(settings.webhook_secret),
        },
        "tickets": None,
        "incidents": None,
        "events": events.log.recent(30),
    }
    if settings.tickets_enabled:
        try:
            page = _tickets_client(settings).list_tickets(limit=10)
            overview["tickets"] = [
                {
                    "reference": t.get("reference"),
                    "subject": t.get("subject"),
                    "status": (t.get("status") or {}).get("name"),
                    "state": (t.get("status") or {}).get("state"),
                    "priority": t.get("priority"),
                    "handling": t.get("handling"),
                    "updatedAt": t.get("updatedAt"),
                    "token": tokens.tracking_token(_tracking_secret(settings), str(t.get("reference"))),
                }
                for t in page.get("items", [])
            ]
            overview["ticketsTotal"] = page.get("total")
        except TmsError as err:
            overview["ticketsError"] = err.message
    if settings.incidents_enabled:
        try:
            client = TmsClient(settings.api_url or "", settings.events_key or "", timeout=8.0)
            overview["incidents"] = client.incidents(status="open", limit=20)
        except TmsError as err:
            overview["incidentsError"] = err.message
    return 200, overview


# ---- Dispatch ----


def handle(req: Request, worker: Any) -> Optional[Response]:
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
        return _webhook(req)

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
        if not _tool_allowed(req):
            return 401, {"message": "A valid tool token is required"}
        tool: Dict[Tuple[str, str], Callable[[], Response]] = {
            ("GET", "scrape-status"): lambda: _tool_scrape_status(req, worker),
            ("GET", "log-tail"): lambda: _tool_log_tail(req, worker),
            ("GET", "catalog-status"): lambda: _tool_catalog_status(req),
            ("GET", "products"): lambda: _tool_search(req),
            ("POST", "rescrape"): lambda: _tool_rescrape(req, worker),
        }
        if len(parts) == 2 and (method, parts[1]) in tool:
            return tool[(method, parts[1])]()
        if len(parts) == 3 and parts[1] == "products" and method == "GET":
            return _tool_product(req, parts[2])

    if parts[:1] == ["admin"] or parts == ["identity"]:
        if not req.admin:
            return _fail(401, "sign-in-required", "Sign in as the admin to see this.")
        if parts == ["identity"] and method == "GET":
            return _identity(req)
        if parts == ["admin", "overview"] and method == "GET":
            return _overview(req)

    return _fail(404, "not-found", "There is nothing at this address.")
