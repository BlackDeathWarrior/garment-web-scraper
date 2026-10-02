"""Scraper failures become reports to the support desk, and recoveries resolve them."""

from datetime import datetime, timezone

from scraper.support import catalog, freshness, incidents

from .conftest import EVENTS_KEY


def test_a_failure_is_reported_with_the_events_key(desk):
    sent = incidents.report(
        "scraper.source_failed:myntra",
        "Myntra scrape failed",
        source="scraper/myntra",
        message="Timeout 45000ms exceeded",
        details={"cycle": 3},
    )
    assert sent is True
    (call,) = desk.calls("POST", "/api/v1/integration/events")
    assert call["headers"]["authorization"] == "Bearer " + EVENTS_KEY
    assert call["body"] == {
        "fingerprint": "scraper.source_failed:myntra",
        "status": "firing",
        "title": "Myntra scrape failed",
        "severity": "error",
        "source": "scraper/myntra",
        "message": "Timeout 45000ms exceeded",
        "details": {"cycle": 3},
    }


def test_a_failure_in_a_tight_loop_is_sent_once_a_minute(desk):
    assert incidents.report("scraper.s3_sync_failed", "Upload failed") is True
    assert incidents.report("scraper.s3_sync_failed", "Upload failed") is False
    # Another problem is not held back by the first.
    assert incidents.report("scraper.disk_critical", "Disk almost full") is True
    assert len(desk.calls("POST", "/integration/events")) == 2


def test_separate_runs_are_each_counted(desk):
    for _ in range(3):
        assert incidents.report("scraper.run_failed", "Run failed", min_interval=0) is True
    assert len(desk.calls("POST", "/integration/events")) == 3


def test_a_recovery_resolves_and_lets_the_next_failure_through(desk):
    incidents.report("scraper.cycle_failed", "Cycle failed")
    assert incidents.recovered("scraper.cycle_failed", "Cycle #4 scraped 120 products.") is True
    assert incidents.report("scraper.cycle_failed", "Cycle failed") is True
    bodies = [c["body"] for c in desk.calls("POST", "/integration/events")]
    assert [b["status"] for b in bodies] == ["firing", "resolved", "firing"]
    assert bodies[1] == {
        "fingerprint": "scraper.cycle_failed",
        "status": "resolved",
        "message": "Cycle #4 scraped 120 products.",
    }


def test_nothing_is_sent_when_the_desk_is_not_configured():
    assert incidents.report("scraper.run_failed", "Run failed") is False
    assert incidents.recovered("scraper.run_failed") is False


def test_a_desk_that_is_down_or_refuses_never_breaks_the_scraper(desk, monkeypatch):
    desk.answer("POST /api/v1/integration/events", 403, {"message": "Missing scope"})
    assert incidents.report("scraper.run_failed", "Run failed") is False

    monkeypatch.setenv("SUPPORT_API_URL", "http://127.0.0.1:1")
    incidents.reset_for_tests()
    assert incidents.report("scraper.run_failed", "Run failed") is False


def test_long_titles_and_messages_are_cut_to_what_the_desk_accepts(desk):
    incidents.report("scraper.source_failed:amazon", "x" * 500, message="y" * 9000)
    (call,) = desk.calls("POST", "/integration/events")
    assert len(call["body"]["title"]) == 300
    assert len(call["body"]["message"]) == 5000


# ---- Catalogue freshness ----


def test_an_old_catalogue_is_reported_as_stale(desk, catalogue):
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    status = freshness.check(now)
    assert status["stale"] is True
    assert status["newest_scraped_at"] == "2026-04-18T18:47:49+00:00"
    (call,) = desk.calls("POST", "/integration/events")
    body = call["body"]
    assert body["fingerprint"] == "catalog.stale"
    assert body["status"] == "firing"
    assert body["severity"] == "warning"
    assert body["title"] == "Catalogue is %s days old" % status["age_days"]
    assert body["details"]["products"] == 2


def test_a_refreshed_catalogue_resolves_the_report(desk, catalogue):
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    freshness.check(now)
    fresh = dict(catalog.products()[0], scraped_at="2026-10-02T11:30:00+00:00")
    catalogue([fresh])
    status = freshness.check(now)
    assert status["stale"] is False
    statuses = [c["body"]["status"] for c in desk.calls("POST", "/integration/events")]
    assert statuses == ["firing", "resolved"]
    # Still fresh an hour later: nothing more to say.
    freshness.check(now)
    assert len(desk.calls("POST", "/integration/events")) == 2


def test_an_empty_catalogue_is_a_first_run_not_a_stale_one(desk, catalogue):
    catalogue([])
    status = freshness.check()
    assert status["products"] == 0
    assert desk.calls("POST", "/integration/events") == []


def test_catalogue_status_and_search(catalogue):
    now = datetime(2026, 4, 19, 18, 47, 49, tzinfo=timezone.utc)
    status = catalog.status(48, now)
    assert status["products"] == 2
    assert status["by_source"] == {"myntra": 1, "amazon": 1}
    assert status["age_hours"] == 24.0
    assert status["stale"] is False

    assert [p["id"] for p in catalog.search("silk saree")] == ["saree-002"]
    assert catalog.search("lehenga") == []
    found = catalog.find("kurta-001")
    assert found["price_current"] == 1499.0
    # Only what a shopper can already see is handed on.
    assert "image_url" not in found
    assert catalog.find("nope") is None
