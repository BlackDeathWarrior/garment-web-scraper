"""Support desk settings, read from the environment (see .env.example).

Nothing is required. Each feature switches on when its own settings are
present, so a deployment can use tickets without incidents, or the reverse.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional, as in worker.py
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class SupportConfig:
    api_url: Optional[str]
    """Where the support desk is served, e.g. http://localhost:3000."""
    web_key: Optional[str]
    """API key for shopper requests (scope integration:ticket)."""
    events_key: Optional[str]
    """API key for scraper incidents (scope integration:event)."""
    webhook_secret: Optional[str]
    chat_identity_secret: Optional[str]
    tool_token: Optional[str]
    """What the support desk's AI sends to call /api/support/tools/*."""
    widget_url: Optional[str]
    """Where the chat widget script is served from; defaults to api_url."""
    tracking_secret: Optional[str]
    """Signs the tokens shoppers read their own requests with; defaults to one derived from web_key."""
    integration: str
    stale_hours: int
    """The catalogue counts as stale once its newest record is older than this."""
    freshness_minutes: int
    """How often the worker checks the catalogue's age."""
    tickets_per_hour: int
    """Requests one visitor (by address) may raise in an hour."""

    @property
    def tickets_enabled(self) -> bool:
        return bool(self.api_url and self.web_key)

    @property
    def incidents_enabled(self) -> bool:
        return bool(self.api_url and self.events_key)

    @property
    def widget_enabled(self) -> bool:
        return bool(self.widget_url or self.api_url)


def _clean(name: str) -> Optional[str]:
    value = (os.environ.get(name) or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value or None


def _number(name: str, default: int) -> int:
    try:
        return max(1, int(_clean(name) or default))
    except ValueError:
        return default


def load() -> SupportConfig:
    """Reads the settings now. The scraper subprocess calls this too, so .env is loaded here."""
    if load_dotenv is not None:
        for env_file in (ROOT / ".env", ROOT / "frontend" / ".env"):
            if env_file.is_file():
                load_dotenv(env_file, override=False)
    return SupportConfig(
        api_url=_clean("SUPPORT_API_URL"),
        web_key=_clean("SUPPORT_API_KEY_WEB"),
        events_key=_clean("SUPPORT_API_KEY_EVENTS"),
        webhook_secret=_clean("SUPPORT_WEBHOOK_SECRET"),
        chat_identity_secret=_clean("SUPPORT_CHAT_IDENTITY_SECRET"),
        tool_token=_clean("SUPPORT_TOOL_TOKEN"),
        widget_url=_clean("SUPPORT_WIDGET_URL"),
        tracking_secret=_clean("SUPPORT_TRACKING_SECRET"),
        integration=_clean("SUPPORT_INTEGRATION") or "ethnic-threads",
        stale_hours=_number("SUPPORT_STALE_HOURS", 48),
        freshness_minutes=_number("SUPPORT_FRESHNESS_MINUTES", 60),
        tickets_per_hour=_number("SUPPORT_TICKETS_PER_HOUR", 20),
    )
