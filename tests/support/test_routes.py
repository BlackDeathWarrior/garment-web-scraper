"""The worker's /api/support/* endpoints: shoppers, the support desk's calls, the admin."""

import json
import time

from scraper.support import events, routes, tokens
from scraper.support.tms_support import sign_webhook

from .conftest import TOOL_TOKEN, WEB_KEY, WEBHOOK_SECRET


class StubWorker:
    """What routes.py needs of the scrape worker."""

    def __init__(self):
        self.triggered = []
        self.next_trigger = (202, {"last_started_at": "2026-10-02T10:00:00+00:00", "sources": "myntra"})

    def status(self):
        return {
            "running": False,
            "pid": None,
            "last_started_at": "2026-10-02T09:00:00+00:00",
            "last_ended_at": "2026-10-02T09:00:02+00:00",
            "last_exit_code": 1,
            "last_error": "Scraper exited with code 1",
            "last_stopped_by_user": False,
            "last_log_file": "C:/somewhere/private/manual-scrape.log",
            "sources": "amazon,myntra,flipkart",
        }

    def log_tail(self, lines):
        return ["[10:00:00] [worker    ] ERR  Scraper cycle failed with exit code 1"][:lines]

    def trigger(self, reason="manual", sources=None, **_):
        self.triggered.append({"reason": reason, "sources": sources})
        return self.next_trigger


def call(method, path, body=None, headers=None, query=None, admin=None, client="203.0.113.9", raw=None):
    request = routes.Request(
        method=method,
        path=path,
        query=query or {},
        headers={k.lower(): v for k, v in (headers or {}).items()},
        raw_body=raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else b""),
        client=client,
        admin=admin,
    )
    return routes.handle(request, StubWorker())


CONTACT = {
    "name": "Asha Verma",
    "email": "asha@shopper.example",
    "subject": "Bug Report",
    "message": "The filter for sarees shows kurtas.",
    "requestId": "form-0001-abcd",
}


def test_paths_outside_api_support_are_not_handled():
    assert call("GET", "/api/scrape-status") is None
    assert call("GET", "/api/supportive") is None


def test_config_tells_the_storefront_what_is_switched_on(desk):
    status, body = call("GET", "/api/support/config")
    assert status == 200
    assert body["tickets"] is True
    assert body["widget"] == {
        "script": desk.url + "/widget/tms-chat.js",
        "server": desk.url,
        "integration": "ethnic-threads",
    }
    # Nothing secret goes to a browser.
    assert "tms_sk_" not in json.dumps(body) and "whsec_" not in json.dumps(body)


def test_with_no_settings_everything_is_off():
    status, body = call("GET", "/api/support/config")
    assert (status, body["tickets"], body["widget"]) == (200, False, None)
    status, body = call("POST", "/api/support/tickets", CONTACT)
    assert (status, body["reason"]) == (503, "support-not-configured")


def test_the_contact_form_raises_a_ticket_and_returns_a_tracking_token(desk):
    desk.answer("POST /api/v1/integration/tickets", 201, {"reference": "TMS-41"})
    status, body = call("POST", "/api/support/tickets", CONTACT)
    assert status == 201
    assert body["reference"] == "TMS-41"
    assert body["token"] == tokens.tracking_token(WEB_KEY, "TMS-41")

    (sent,) = desk.calls("POST", "/integration/tickets")
    assert sent["headers"]["authorization"] == "Bearer " + WEB_KEY
    assert sent["headers"]["idempotency-key"] == "et-form-0001-abcd"
    assert sent["body"] == {
        "customer": {"email": "asha@shopper.example", "name": "Asha Verma"},
        "subject": "Bug Report: The filter for sarees shows kurtas.",
        "body": "The filter for sarees shows kurtas.",
        "category": "Site problem",
        "tags": ["contact-form"],
        "metadata": {"form": "contact", "topic": "Bug Report"},
    }


def test_a_listing_report_carries_the_listing_from_our_catalogue_not_the_browser(desk, catalogue):
    desk.answer("POST /api/v1/integration/tickets", 201, {"reference": "TMS-42"})
    status, body = call(
        "POST",
        "/api/support/tickets",
        {
            **CONTACT,
            "kind": "listing",
            "productId": "kurta-001",
            "issue": "wrong-price",
            "message": "Myntra charges 1,799 for this.",
            # A browser could send anything; none of this may reach the ticket.
            "price_current": 1,
            "metadata": {"price_current": 1},
        },
    )
    assert (status, body["reference"]) == (201, "TMS-42")
    (sent,) = desk.calls("POST", "/integration/tickets")
    assert sent["body"]["subject"] == "Wrong price: Cotton Straight Kurta"
    assert sent["body"]["externalRef"] == "kurta-001"
    assert sent["body"]["category"] == "Listings"
    assert sent["body"]["tags"] == ["listing", "wrong-price"]
    metadata = sent["body"]["metadata"]
    assert metadata["form"] == "listing_report"
    assert metadata["issue"] == "Wrong price"
    assert metadata["product_id"] == "kurta-001"
    assert metadata["price_current"] == 1499.0
    assert metadata["scraped_at"] == "2026-04-18T18:47:49+00:00"


def test_a_report_about_a_listing_we_do_not_have_is_refused(desk, catalogue):
    status, body = call("POST", "/api/support/tickets", {**CONTACT, "kind": "listing", "productId": "gone"})
    assert (status, body["reason"]) == (404, "unknown-product")
    assert desk.calls("POST", "/integration/tickets") == []


def test_bad_input_is_refused_before_the_desk_is_called(desk):
    for change in ({"name": " "}, {"email": "not-an-email"}, {"message": ""}, {"requestId": "short"}):
        status, body = call("POST", "/api/support/tickets", {**CONTACT, **change})
        assert (status, body["reason"]) == (400, "invalid"), change
    assert desk.calls("POST", "/integration/tickets") == []


def test_a_category_the_desk_does_not_have_is_left_out(desk):
    desk.answer("POST /api/v1/integration/tickets", 400, {"message": 'Unknown category "Site problem"'})
    desk.answer("POST /api/v1/integration/tickets", 201, {"reference": "TMS-43"})
    status, body = call("POST", "/api/support/tickets", CONTACT)
    assert (status, body["reference"]) == (201, "TMS-43")
    first, second = desk.calls("POST", "/integration/tickets")
    assert first["body"]["category"] == "Site problem"
    assert "category" not in second["body"]
    # Both attempts are one request: the same idempotency key.
    assert first["headers"]["idempotency-key"] == second["headers"]["idempotency-key"]


def test_the_desk_being_down_or_busy_is_said_plainly(desk, monkeypatch):
    desk.answer("POST /api/v1/integration/tickets", 429, {"message": "Too many requests."})
    status, body = call("POST", "/api/support/tickets", CONTACT)
    assert (status, body["reason"]) == (429, "too-many-requests")

    monkeypatch.setenv("SUPPORT_API_URL", "http://127.0.0.1:1")
    status, body = call("POST", "/api/support/tickets", {**CONTACT, "requestId": "form-0002-abcd"})
    assert (status, body["reason"]) == (502, "support-unreachable")


def test_one_visitor_cannot_flood_the_desk(desk, monkeypatch):
    monkeypatch.setenv("SUPPORT_TICKETS_PER_HOUR", "2")
    for i in range(2):
        status, _ = call("POST", "/api/support/tickets", {**CONTACT, "requestId": "form-000%d-abcd" % i})
        assert status == 201
    status, body = call("POST", "/api/support/tickets", {**CONTACT, "requestId": "form-0009-abcd"})
    assert (status, body["reason"]) == (429, "too-many-requests")
    # Someone else is not affected.
    status, _ = call("POST", "/api/support/tickets", {**CONTACT, "requestId": "form-0010-abcd"}, client="198.51.100.7")
    assert status == 201


# ---- Reading a request back ----

TICKET = {
    "reference": "TMS-41",
    "subject": "Bug Report: The filter for sarees shows kurtas.",
    "status": {"key": "pending_customer", "name": "Waiting for you", "state": "pending"},
    "externalRef": None,
    "customer": {"name": "Asha Verma", "email": "asha@shopper.example"},
    "metadata": {"form": "contact"},
    "createdAt": "2026-10-02T10:00:00.000Z",
    "updatedAt": "2026-10-02T10:05:00.000Z",
}
MESSAGES = [
    {"id": "m1", "from": "customer", "name": None, "body": "The filter is wrong.", "createdAt": "2026-10-02T10:00:00.000Z"},
    {"id": "m2", "from": "support", "name": "Maya", "body": "Fixed, thank you.", "createdAt": "2026-10-02T10:05:00.000Z"},
]


def test_a_request_is_read_only_with_its_tracking_token(desk):
    token = tokens.tracking_token(WEB_KEY, "TMS-41")
    for headers in ({}, {"X-Request-Token": "0" * 32}, {"X-Request-Token": tokens.tracking_token(WEB_KEY, "TMS-40")}):
        status, body = call("GET", "/api/support/requests/TMS-41", headers=headers)
        assert (status, body["reason"]) == (404, "not-found")
    assert desk.seen == []

    desk.answer("GET /api/v1/integration/tickets/TMS-41/messages", 200, MESSAGES)
    desk.answer("GET /api/v1/integration/tickets/TMS-41", 200, TICKET)
    status, body = call("GET", "/api/support/requests/tms-41", headers={"X-Request-Token": token})
    assert status == 200
    assert body["status"] == "Waiting for you"
    assert body["state"] == "pending"
    assert [m["from"] for m in body["messages"]] == ["customer", "support"]
    assert body["messages"][1]["name"] == "Maya"
    # The page gets what it shows, and no more of the ticket.
    assert "customer" not in body and "metadata" not in body


def test_a_follow_up_and_a_rating_go_to_the_ticket(desk):
    headers = {"X-Request-Token": tokens.tracking_token(WEB_KEY, "TMS-41")}
    status, _ = call(
        "POST",
        "/api/support/requests/TMS-41/messages",
        {"message": "Still wrong on mobile.", "requestId": "reply-0001-abcd"},
        headers=headers,
    )
    assert status == 201
    (reply,) = desk.calls("POST", "/tickets/TMS-41/messages")
    assert reply["body"] == {"body": "Still wrong on mobile."}
    assert reply["headers"]["idempotency-key"] == "et-reply-0001-abcd"

    status, _ = call("POST", "/api/support/requests/TMS-41/rating", {"rating": 5, "comment": "Quick"}, headers=headers)
    assert status == 200
    (rating,) = desk.calls("POST", "/tickets/TMS-41/rating")
    assert rating["body"] == {"rating": 5, "comment": "Quick"}

    status, body = call("POST", "/api/support/requests/TMS-41/rating", {"rating": 9}, headers=headers)
    assert (status, body["reason"]) == (400, "invalid")
    status, _ = call("POST", "/api/support/requests/TMS-41/messages", {"message": "x", "requestId": "reply-0002-abcd"})
    assert status == 404


def test_a_refusal_from_the_desk_reaches_the_shopper(desk):
    headers = {"X-Request-Token": tokens.tracking_token(WEB_KEY, "TMS-41")}
    desk.answer("POST /api/v1/integration/tickets/TMS-41/rating", 409, {"message": "This ticket is not solved yet"})
    status, body = call("POST", "/api/support/requests/TMS-41/rating", {"rating": 4}, headers=headers)
    assert (status, body["message"]) == (409, "This ticket is not solved yet")


# ---- Webhooks from the support desk ----


def delivery(event_id="d-1", event_type="message.created", secret=WEBHOOK_SECRET, at=None):
    payload = {
        "id": event_id,
        "type": event_type,
        "createdAt": "2026-10-02T10:05:00.000Z",
        "integration": "ethnic-threads",
        "data": {
            "ticket": TICKET,
            "message": {"id": "m2", "from": "support", "name": "Maya", "body": "Fixed, thank you."},
        },
    }
    raw = json.dumps(payload)
    header = sign_webhook(raw, secret, int(time.time()) if at is None else at)
    return raw.encode("utf-8"), {"X-TMS-Signature": header, "X-TMS-Delivery": event_id}


def test_a_signed_webhook_is_stored_once(desk):
    raw, headers = delivery()
    assert call("POST", "/api/support/webhook", raw=raw, headers=headers) == (200, {"ok": True, "duplicate": False})
    # The desk retries a delivery it thinks failed: same id, nothing new stored.
    assert call("POST", "/api/support/webhook", raw=raw, headers=headers) == (200, {"ok": True, "duplicate": True})

    (event,) = events.log.recent()
    assert event["type"] == "message.created"
    assert event["reference"] == "TMS-41"
    assert event["status"] == "Waiting for you"
    assert event["message"] == {"from": "support", "name": "Maya", "preview": "Fixed, thank you."}
    assert events.log.version("tms-41") == "d-1"


def test_a_webhook_that_does_not_verify_is_refused(desk):
    raw, headers = delivery(secret="whsec_someone_else")
    status, body = call("POST", "/api/support/webhook", raw=raw, headers=headers)
    assert (status, body["reason"]) == (401, "bad-signature")

    raw, headers = delivery()
    status, _ = call("POST", "/api/support/webhook", raw=raw + b" ", headers=headers)
    assert status == 401
    status, _ = call("POST", "/api/support/webhook", raw=raw, headers={})
    assert status == 401
    # A real delivery, replayed an hour later.
    raw, headers = delivery(at=int(time.time()) - 3600)
    status, _ = call("POST", "/api/support/webhook", raw=raw, headers=headers)
    assert status == 401
    assert events.log.recent() == []


def test_the_event_log_survives_a_restart(desk, tmp_path):
    raw, headers = delivery("d-7", "ticket.status_changed")
    call("POST", "/api/support/webhook", raw=raw, headers=headers)
    reopened = events.EventLog(tmp_path / "events.jsonl")
    assert [e["id"] for e in reopened.recent()] == ["d-7"]
    assert reopened.record(json.loads(raw)) is False


def test_an_open_request_page_hears_about_news_without_calling_the_desk(desk):
    headers = {"X-Request-Token": tokens.tracking_token(WEB_KEY, "TMS-41")}
    assert call("GET", "/api/support/requests/TMS-41/changes", headers=headers) == (
        200,
        {"ok": True, "version": None, "live": True},
    )
    raw, signed = delivery("d-2")
    call("POST", "/api/support/webhook", raw=raw, headers=signed)
    status, body = call("GET", "/api/support/requests/TMS-41/changes", headers=headers)
    assert body["version"] == "d-2"
    assert desk.seen == []
    assert call("GET", "/api/support/requests/TMS-41/changes")[0] == 404


# ---- Tools the support desk's AI calls ----

TOOL = {"Authorization": "Bearer " + TOOL_TOKEN}


def test_tools_need_the_tool_token(desk, catalogue):
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Bearer " + WEB_KEY}):
        status, _ = call("GET", "/api/support/tools/scrape-status", headers=headers)
        assert status == 401
    status, _ = call("POST", "/api/support/tools/rescrape", {}, headers={})
    assert status == 401


def test_tools_are_off_when_no_token_is_set(catalogue):
    assert call("GET", "/api/support/tools/catalog-status", headers={"Authorization": "Bearer "})[0] == 401


def test_read_tools_answer_with_facts(desk, catalogue):
    status, body = call("GET", "/api/support/tools/scrape-status", headers=TOOL)
    assert status == 200
    assert body["last_exit_code"] == 1
    assert body["last_error"] == "Scraper exited with code 1"
    # Paths on this machine are nobody else's business.
    assert "last_log_file" not in body

    status, body = call("GET", "/api/support/tools/log-tail", headers=TOOL, query={"lines": "5"})
    assert status == 200 and "exit code 1" in body["lines"][0]

    status, body = call("GET", "/api/support/tools/catalog-status", headers=TOOL)
    assert (status, body["products"], body["stale"]) == (200, 2, True)

    status, body = call("GET", "/api/support/tools/products/saree-002", headers=TOOL)
    assert (status, body["in_stock"], body["price_current"]) == (200, False, 2199.0)
    status, body = call("GET", "/api/support/tools/products/nope", headers=TOOL)
    assert status == 404

    status, body = call("GET", "/api/support/tools/products", headers=TOOL, query={"query": "cotton kurta"})
    assert (status, [p["id"] for p in body["listings"]]) == (200, ["kurta-001"])
    assert call("GET", "/api/support/tools/products", headers=TOOL)[0] == 400


def test_the_rescrape_tool_starts_a_scrape(desk):
    worker = StubWorker()
    request = routes.Request(
        method="POST",
        path="/api/support/tools/rescrape",
        headers={"authorization": "Bearer " + TOOL_TOKEN},
        raw_body=json.dumps({"source": "Myntra", "reason": "customer says prices are old"}).encode("utf-8"),
    )
    status, body = routes.handle(request, worker)
    assert (status, body["started"]) == (202, True)
    assert worker.triggered == [{"reason": "support-desk: customer says prices are old", "sources": "myntra"}]

    worker.next_trigger = (409, {"last_started_at": "2026-10-02T10:00:00+00:00"})
    status, body = routes.handle(request, worker)
    assert (status, body["message"]) == (409, "A scrape is already running")

    request.raw_body = json.dumps({"source": "ebay"}).encode("utf-8")
    assert routes.handle(request, worker)[0] == 400
    assert len(worker.triggered) == 2


# ---- The admin ----


def test_the_admin_views_need_a_session(desk):
    assert call("GET", "/api/support/admin/overview")[0] == 401
    assert call("GET", "/api/support/identity")[0] == 401


def test_the_admin_overview_shows_tickets_incidents_and_activity(desk):
    desk.answer("GET /api/v1/integration/tickets", 200, {"items": [TICKET], "total": 1})
    desk.answer(
        "GET /api/v1/integration/incidents",
        200,
        [{"fingerprint": "scraper.run_failed", "title": "Scraper run failed", "status": "open", "occurrences": 3}],
    )
    raw, signed = delivery("d-3", "ticket.created")
    call("POST", "/api/support/webhook", raw=raw, headers=signed)

    status, body = call("GET", "/api/support/admin/overview", admin="scraper_admin")
    assert status == 200
    assert body["configured"] == {"tickets": True, "incidents": True, "webhooks": True}
    assert body["tickets"][0]["reference"] == "TMS-41"
    # The admin reads requests with the session; a shopper's tracking token is never handed out.
    assert "token" not in body["tickets"][0]
    assert tokens.tracking_token(WEB_KEY, "TMS-41") not in json.dumps(body)
    assert body["incidents"][0]["occurrences"] == 3
    assert [e["id"] for e in body["events"]] == ["d-3"]
    assert "?status=open" in desk.calls("GET", "/integration/incidents")[0]["path"]


def test_the_admin_is_a_known_customer_and_gets_a_chat_identity(desk):
    status, body = call("GET", "/api/support/identity", admin="scraper_admin")
    assert status == 200
    header, claims, _ = body["token"].split(".")
    import base64

    decoded = json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))
    assert (decoded["sub"], decoded["name"]) == ("admin", "scraper_admin")

    desk.answer("POST /api/v1/integration/tickets", 201, {"reference": "TMS-50"})
    call("POST", "/api/support/tickets", CONTACT, admin="scraper_admin")
    (sent,) = desk.calls("POST", "/integration/tickets")
    assert sent["body"]["customer"]["externalId"] == "admin"

    # The admin may open any of the site's requests without a tracking token.
    desk.answer("GET /api/v1/integration/tickets/TMS-41/messages", 200, MESSAGES)
    desk.answer("GET /api/v1/integration/tickets/TMS-41", 200, TICKET)
    assert call("GET", "/api/support/requests/TMS-41", admin="scraper_admin")[0] == 200
    # Reading only: a reply or a rating is said in the shopper's name, so it needs their token.
    reply = {"message": "Speaking for the shopper", "requestId": "reply-0009-abcd"}
    assert call("POST", "/api/support/requests/TMS-41/messages", reply, admin="scraper_admin")[0] == 404
    assert call("POST", "/api/support/requests/TMS-41/rating", {"rating": 5}, admin="scraper_admin")[0] == 404
    assert desk.calls("POST", "/tickets/TMS-41/") == []


def test_session_tokens_expire_and_cannot_be_forged():
    token = tokens.sign_session("admin-password", now=1_000_000)
    assert tokens.verify_session("admin-password", token, now=1_000_100) is True
    assert tokens.verify_session("admin-password", token, now=1_000_000 + tokens.SESSION_TTL_SECONDS + 1) is False
    assert tokens.verify_session("another-password", token, now=1_000_100) is False
    far = "v1.9999999999." + token.split(".")[2]
    assert tokens.verify_session("admin-password", far, now=1_000_100) is False
    for bad in (None, "", "admin_session_active", "v1.x.y"):
        assert tokens.verify_session("admin-password", bad) is False
    assert tokens.verify_session(None, token) is False
