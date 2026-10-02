"""The worker itself: its HTTP handler, sign-in, and what a scrape run's end reports.

The run that fails here is a real one: the worker starts the real scraper
with a source that does not exist, which exits with code 1 before it opens
a browser.
"""

import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from scraper import worker as worker_module
from scraper.support import tokens

from .conftest import WEB_KEY


def wait_for(check, seconds=20.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(0.1)
    raise AssertionError("timed out")


@pytest.fixture
def scratch(monkeypatch, tmp_path):
    """The worker writes its logs under a temporary folder, not the repo's."""
    monkeypatch.setattr(worker_module, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(worker_module, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(worker_module, "PUBLIC_LOG_FILE", tmp_path / "scraper.log")
    return tmp_path


@pytest.fixture
def site(monkeypatch, scratch):
    """The worker's HTTP server on a free port, with an admin password set."""
    monkeypatch.setenv("ADMIN_USERNAME", "scraper_admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-password")
    worker = worker_module.ScrapeWorker(sources="notasource", max_products=1)
    monkeypatch.setattr(worker_module.WorkerRequestHandler, "worker", worker, raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), worker_module.WorkerRequestHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_port

    def request(method, path, body=None, headers=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers or {})
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"{}")

    request.worker = worker
    yield request
    server.shutdown()
    server.server_close()


def test_sign_in_gives_a_session_the_support_endpoints_accept(site, desk):
    status, body = site("POST", "/api/auth/login", {"username": "scraper_admin", "password": "wrong"})
    assert status == 401
    status, body = site("POST", "/api/auth/login", {"username": "scraper_admin", "password": "test-admin-password"})
    assert status == 200 and body["ok"] is True
    token = body["token"]
    assert tokens.verify_session("test-admin-password", token)

    assert site("GET", "/api/support/admin/overview")[0] == 401
    assert site("GET", "/api/support/admin/overview", headers={"Authorization": "Bearer admin_session_active"})[0] == 401
    status, body = site("GET", "/api/support/admin/overview", headers={"Authorization": "Bearer " + token})
    assert status == 200 and body["configured"]["tickets"] is True


def test_the_storefront_reaches_the_support_routes_and_the_old_ones_still_work(site, desk):
    status, body = site("GET", "/api/support/config")
    assert (status, body["tickets"]) == (200, True)
    status, body = site("GET", "/api/scrape-status")
    assert status == 200 and body["running"] is False
    status, body = site("GET", "/api/support/nothing-here")
    assert status == 404

    desk.answer("POST /api/v1/integration/tickets", 201, {"reference": "TMS-9"})
    status, body = site(
        "POST",
        "/api/support/tickets",
        {
            "name": "Asha Verma",
            "email": "asha@shopper.example",
            "subject": "General Feedback",
            "message": "Lovely site.",
            "requestId": "form-http-0001",
        },
    )
    assert (status, body["reference"]) == (201, "TMS-9")
    assert body["token"] == tokens.tracking_token(WEB_KEY, "TMS-9")


def test_an_oversized_body_is_refused(site, desk):
    status, _ = site("POST", "/api/support/webhook", {"padding": "x" * (300 * 1024)})
    assert status == 413


def test_a_failed_run_is_reported_and_each_failure_counted(site, desk):
    worker = site.worker
    for expected in (1, 2):
        status, body = site("POST", "/api/scrape-cycle", {"reason": "manual"})
        assert status == 202, body
        reports = wait_for(
            lambda: len(desk.calls("POST", "/integration/events")) >= expected
            and desk.calls("POST", "/integration/events")
        )
        wait_for(lambda: not worker.status()["running"])
    body = reports[-1]["body"]
    assert body["fingerprint"] == "scraper.run_failed"
    assert body["status"] == "firing"
    assert body["title"] == "Scraper run failed (exit code 1)"
    assert body["details"]["exit_code"] == 1
    assert "No valid sources in 'notasource'" in body["message"]
    status = worker.status()
    assert (status["last_exit_code"], status["last_stopped_by_user"]) == (1, False)


def test_a_run_the_admin_stopped_is_not_a_failure(site, desk, scratch):
    worker = site.worker
    # A stand-in for a long scrape: a real process the worker can stop.
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], text=True)
    with worker._lock:
        worker._process = process
        worker._status.running = True
    watcher = threading.Thread(target=worker._watch_process, args=(process,), daemon=True)
    watcher.start()

    status, body = site("POST", "/api/stop-scrape")
    assert status == 200 and body["ok"] is True
    watcher.join(timeout=10)
    assert not watcher.is_alive()
    assert worker.status()["last_stopped_by_user"] is True
    time.sleep(0.3)
    assert desk.calls("POST", "/integration/events") == []


def test_a_run_that_finishes_resolves_an_earlier_failure(site, desk):
    worker = site.worker
    process = subprocess.Popen([sys.executable, "-c", "pass"], text=True)
    with worker._lock:
        worker._process = process
    worker._watch_process(process)
    resolved = [c["body"] for c in desk.calls("POST", "/integration/events")]
    assert {"fingerprint": "scraper.run_failed", "status": "resolved", "message": "A scrape finished successfully."} in resolved
    assert worker.status()["last_exit_code"] == 0
