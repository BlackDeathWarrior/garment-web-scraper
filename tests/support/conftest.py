"""Fixtures for the support desk integration tests.

`desk` is a small HTTP server on this machine that records what the app
sends and answers what a test queued, so the real client code runs over
real HTTP. Nothing here talks to a real support desk: every SUPPORT_*
setting is cleared before each test, whatever the machine's .env says.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scraper.support import catalog, config, events, freshness, incidents, routes  # noqa: E402

WEB_KEY = "tms_sk_test_web"
EVENTS_KEY = "tms_sk_test_events"
WEBHOOK_SECRET = "whsec_test_secret"
TOOL_TOKEN = "tool-token-for-tests"
IDENTITY_SECRET = "chid_test_secret"


class _DeskHandler(BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        request = {
            "method": self.command,
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": json.loads(raw) if raw else None,
        }
        with self.server.lock:
            self.server.seen.append(request)
            answer = None
            for i, (match, queued) in enumerate(self.server.answers):
                if match in ("%s %s" % (self.command, self.path)):
                    answer = queued
                    del self.server.answers[i]
                    break
        status, body = answer if answer else (200, {})
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle

    def log_message(self, *args):
        pass


class Desk:
    def __init__(self, server):
        self._server = server
        self.url = "http://127.0.0.1:%d" % server.server_port

    @property
    def seen(self):
        with self._server.lock:
            return list(self._server.seen)

    def calls(self, method, path_part):
        return [r for r in self.seen if r["method"] == method and path_part in r["path"]]

    def answer(self, match, status, body):
        """The next request whose "METHOD /path" contains `match` gets this answer."""
        with self._server.lock:
            self._server.answers.append((match, (status, body)))


@pytest.fixture(autouse=True)
def clean_support_state(monkeypatch, tmp_path):
    for name in [n for n in os.environ if n.startswith("SUPPORT_")]:
        monkeypatch.delenv(name)
    # Never read the machine's own .env: it may point at a real support desk.
    monkeypatch.setattr(config, "load_dotenv", None)
    monkeypatch.setattr(events, "log", events.EventLog(tmp_path / "events.jsonl"))
    incidents.reset_for_tests()
    freshness.reset_for_tests()
    routes.limiter.reset()
    yield
    incidents.reset_for_tests()


@pytest.fixture
def desk(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DeskHandler)
    server.seen = []
    server.answers = []
    server.lock = threading.Lock()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    made = Desk(server)
    monkeypatch.setenv("SUPPORT_API_URL", made.url)
    monkeypatch.setenv("SUPPORT_API_KEY_WEB", WEB_KEY)
    monkeypatch.setenv("SUPPORT_API_KEY_EVENTS", EVENTS_KEY)
    monkeypatch.setenv("SUPPORT_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("SUPPORT_TOOL_TOKEN", TOOL_TOKEN)
    monkeypatch.setenv("SUPPORT_CHAT_IDENTITY_SECRET", IDENTITY_SECRET)
    yield made
    server.shutdown()
    server.server_close()


PRODUCTS = [
    {
        "id": "kurta-001",
        "title": "Cotton Straight Kurta",
        "brand": "Biba",
        "source": "myntra",
        "product_url": "https://www.myntra.com/kurta-001",
        "price_current": 1499.0,
        "price_original": 2999.0,
        "discount_percent": 50,
        "image_url": "https://example.com/kurta.jpg",
        "category": "Kurta",
        "target_gender": "Women",
        "in_stock": True,
        "scraped_at": "2026-04-18T18:47:49+00:00",
    },
    {
        "id": "saree-002",
        "title": "Banarasi Silk Saree with Blouse Piece",
        "brand": "Kalini",
        "source": "amazon",
        "product_url": "https://www.amazon.in/dp/saree-002",
        "price_current": 2199.0,
        "category": "Saree",
        "target_gender": "Women",
        "in_stock": False,
        "scraped_at": "2026-04-17T09:00:00+00:00",
    },
]


@pytest.fixture
def catalogue(monkeypatch, tmp_path):
    """A two-product catalogue file in place of the real products.json."""
    path = tmp_path / "products.json"

    def write(products):
        path.write_text(json.dumps(products), encoding="utf-8")
        # A new file with the same mtime would be served from the cache.
        catalog._cache.update(path=None, mtime=None, products=[])
        return path

    write(PRODUCTS)
    monkeypatch.setattr(catalog, "CANDIDATES", (path,))
    return write
