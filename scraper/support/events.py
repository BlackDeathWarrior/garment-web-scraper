"""What the support desk's webhooks told us, kept in outputs/support/events.jsonl.

Each delivery is stored once (retries repeat the same id) as a short summary:
enough for the admin's activity feed and to tell a shopper's open request
page that something changed.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
EVENTS_FILE = ROOT / "outputs" / "support" / "events.jsonl"
MAX_KEPT = 500
PREVIEW_CHARS = 160


def summarise(payload: Dict[str, Any]) -> Dict[str, Any]:
    """The part of a webhook payload this app keeps."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    ticket = data.get("ticket") if isinstance(data.get("ticket"), dict) else {}
    incident = data.get("incident") if isinstance(data.get("incident"), dict) else {}
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    approval = data.get("approval") if isinstance(data.get("approval"), dict) else {}
    status = ticket.get("status") if isinstance(ticket.get("status"), dict) else {}
    record: Dict[str, Any] = {
        "id": str(payload.get("id") or ""),
        "type": str(payload.get("type") or "unknown"),
        "at": payload.get("createdAt"),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "reference": ticket.get("reference") or incident.get("ticket"),
    }
    if ticket:
        record["subject"] = ticket.get("subject")
        record["status"] = status.get("name")
        record["state"] = status.get("state")
        record["external_ref"] = ticket.get("externalRef")
    if incident:
        record["incident"] = {
            "fingerprint": incident.get("fingerprint"),
            "title": incident.get("title"),
            "status": incident.get("status"),
            "severity": incident.get("severity"),
            "occurrences": incident.get("occurrences"),
        }
    if message:
        body = " ".join(str(message.get("body") or "").split())
        record["message"] = {
            "from": message.get("from"),
            "name": message.get("name"),
            "preview": body[:PREVIEW_CHARS] + ("..." if len(body) > PREVIEW_CHARS else ""),
        }
    if approval:
        record["approval"] = {
            "action": approval.get("action"),
            "status": approval.get("status"),
        }
    if "rating" in data:
        rating = data.get("rating")
        record["rating"] = rating.get("rating") if isinstance(rating, dict) else rating
    if data.get("from") or data.get("to"):
        record["from"] = data.get("from")
        record["to"] = data.get("to")
    return record


class EventLog:
    def __init__(self, path: Path = EVENTS_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []
        self._ids: set = set()
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.is_file():
            return
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines[-MAX_KEPT:]:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("id"):
                self._events.append(event)
                self._ids.add(event["id"])

    def record(self, payload: Dict[str, Any]) -> bool:
        """Stores a delivery. False when this id was stored before (a retry)."""
        event = summarise(payload)
        if not event["id"]:
            return False
        with self._lock:
            self._load()
            if event["id"] in self._ids:
                return False
            self._events.append(event)
            self._ids.add(event["id"])
            trimmed = len(self._events) > MAX_KEPT * 2
            if trimmed:
                self._events = self._events[-MAX_KEPT:]
                self._ids = {e["id"] for e in self._events}
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                if trimmed:
                    with open(self._path, "w", encoding="utf-8") as handle:
                        handle.writelines(json.dumps(e) + "\n" for e in self._events)
                else:
                    with open(self._path, "a", encoding="utf-8") as handle:
                        handle.write(json.dumps(event) + "\n")
            except OSError:
                pass  # The feed still works from memory until the next restart.
            return True

    def recent(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Newest first."""
        with self._lock:
            self._load()
            return list(reversed(self._events[-limit:]))

    def version(self, reference: str) -> Optional[str]:
        """The id of the last event about a ticket: changes when there is news."""
        wanted = reference.upper()
        with self._lock:
            self._load()
            for event in reversed(self._events):
                if str(event.get("reference") or "").upper() == wanted:
                    return event["id"]
        return None


log = EventLog()
