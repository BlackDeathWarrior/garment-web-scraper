"""Tell the support desk when the scraper fails, and when it recovers.

    incidents.report("scraper.source_failed:myntra", "Myntra scrape failed", message=str(exc))
    incidents.recovered("scraper.source_failed:myntra")

Reports with one fingerprint share one ticket there, so call these wherever
the failure is detected and do not worry about repeats. Calls never raise and
never block the scraper for long: a support desk that is down must not take
the scraper down with it.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from scraper.support import config
from scraper.support.tms_support import TmsClient, TmsError

# The same fingerprint is sent at most once in this many seconds, per process.
MIN_INTERVAL_SECONDS = 60
TIMEOUT_SECONDS = 3.0

_lock = threading.Lock()
_last_sent: Dict[str, float] = {}
_client: Optional[TmsClient] = None
_client_for: Optional[tuple] = None


def _get_client() -> Optional[TmsClient]:
    global _client, _client_for
    settings = config.load()
    if not settings.incidents_enabled:
        return None
    wanted = (settings.api_url, settings.events_key)
    if _client is None or _client_for != wanted:
        _client = TmsClient(settings.api_url, settings.events_key, timeout=TIMEOUT_SECONDS)
        _client_for = wanted
    return _client


def _due(key: str, min_interval: float = MIN_INTERVAL_SECONDS) -> bool:
    now = time.monotonic()
    with _lock:
        last = _last_sent.get(key)
        if last is not None and now - last < min_interval:
            return False
        _last_sent[key] = now
        return True


def _log(message: str) -> None:
    # Imported here: log.py is used by the scraper subprocess, not by every caller.
    try:
        from scraper import log

        log.warn("support", message)
    except Exception:
        print(f"[support] {message}", flush=True)


def report(
    fingerprint: str,
    title: str,
    *,
    severity: str = "error",
    source: Optional[str] = None,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    min_interval: float = MIN_INTERVAL_SECONDS,
) -> bool:
    """Something is failing. Returns whether the report was sent.

    Pass `min_interval=0` where each call is one separate failure (a whole
    run ending), so every one is counted.
    """
    client = _get_client()
    if client is None or not _due("firing:" + fingerprint, min_interval):
        return False
    try:
        client.report_event(
            fingerprint,
            title[:300],
            severity=severity,
            source=source,
            message=(message or None) and str(message)[:5000],
            details=details,
        )
        return True
    except TmsError as err:
        _log(f"could not report {fingerprint}: {err.message}")
        return False
    except Exception as err:  # Never let reporting break the scraper.
        _log(f"could not report {fingerprint}: {err}")
        return False


def recovered(fingerprint: str, message: Optional[str] = None) -> bool:
    """It works again. Harmless when nothing was reported. Returns whether it was sent."""
    client = _get_client()
    if client is None or not _due("resolved:" + fingerprint):
        return False
    # The next failure of this kind is news again.
    with _lock:
        _last_sent.pop("firing:" + fingerprint, None)
    try:
        client.resolve_event(fingerprint, message)
        return True
    except TmsError as err:
        _log(f"could not resolve {fingerprint}: {err.message}")
        return False
    except Exception as err:
        _log(f"could not resolve {fingerprint}: {err}")
        return False


def reset_for_tests() -> None:
    global _client, _client_for
    with _lock:
        _last_sent.clear()
    _client = None
    _client_for = None
