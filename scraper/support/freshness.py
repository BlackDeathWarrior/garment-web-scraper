"""Tells the support desk when the catalogue has gone stale, and when it is fresh again.

The storefront shows whatever the last scrape found. When no scrape has
succeeded for a while, prices drift from the stores' and nobody notices:
this check notices.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Optional

from scraper.support import catalog, config, incidents

FINGERPRINT = "catalog.stale"
# How often the loop looks at the catalogue file; a full check runs when the
# file changed or `freshness_minutes` have passed.
POLL_SECONDS = 30

_was_stale: Optional[bool] = None


def check(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Looks at the catalogue's age and reports a change. Returns the status."""
    global _was_stale
    settings = config.load()
    status = catalog.status(settings.stale_hours, now)
    if status["products"] == 0:
        # An empty catalogue is a first run, not a stale one.
        return status
    if status["stale"]:
        incidents.report(
            FINGERPRINT,
            "Catalogue is %s days old" % status["age_days"],
            severity="warning",
            source="worker/freshness",
            message=(
                "The newest product was scraped on %s. Prices and stock shown on the site "
                "may no longer match the stores." % status["newest_scraped_at"]
            ),
            details={
                "products": status["products"],
                "newest_scraped_at": status["newest_scraped_at"],
                "age_hours": status["age_hours"],
                "stale_after_hours": status["stale_after_hours"],
            },
            min_interval=0,
        )
    elif _was_stale is not False:
        incidents.recovered(FINGERPRINT, "A scrape has refreshed the catalogue.")
    _was_stale = bool(status["stale"])
    return status


def _mtime() -> Optional[float]:
    path = catalog.catalog_file()
    try:
        return path.stat().st_mtime if path else None
    except OSError:
        return None


def start(stop: Optional[threading.Event] = None) -> threading.Thread:
    """Checks now, then whenever the catalogue file changes or the interval passes."""
    stop = stop or threading.Event()

    def loop() -> None:
        seen = None
        waited = 0.0
        first = True
        while not stop.is_set():
            interval = config.load().freshness_minutes * 60
            current = _mtime()
            if first or current != seen or waited >= interval:
                first = False
                seen = current
                waited = 0.0
                try:
                    check()
                except Exception:
                    pass  # A bad catalogue file must not stop the worker.
            stop.wait(POLL_SECONDS)
            waited += POLL_SECONDS

    thread = threading.Thread(target=loop, name="support-freshness", daemon=True)
    thread.start()
    return thread


def reset_for_tests() -> None:
    global _was_stale
    _was_stale = None
