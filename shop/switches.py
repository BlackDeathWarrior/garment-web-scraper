"""The admin's simulation switches: what is going wrong in the shop right now.

Nothing real fails. These make the shop behave as if its payment provider or
its carrier had a problem, so the consequences (failed checkouts, late
orders, the incidents reported to the support desk) can be shown.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict

from shop import db

DEFAULT_STEP_SECONDS = 30
MIN_STEP_SECONDS = 2
MAX_STEP_SECONDS = 3600

_FLAGS = ("payments_down", "carrier_delay")


def _default_step() -> int:
    try:
        return int(os.environ.get("SHOP_STEP_SECONDS") or DEFAULT_STEP_SECONDS)
    except ValueError:
        return DEFAULT_STEP_SECONDS


def read(conn: sqlite3.Connection) -> Dict[str, Any]:
    step = db.get_setting(conn, "step_seconds")
    try:
        step_seconds = int(step) if step else _default_step()
    except ValueError:
        step_seconds = _default_step()
    return {
        "payments_down": db.get_setting(conn, "payments_down") == "1",
        "carrier_delay": db.get_setting(conn, "carrier_delay") == "1",
        "step_seconds": max(MIN_STEP_SECONDS, min(step_seconds, MAX_STEP_SECONDS)),
    }


def current() -> Dict[str, Any]:
    with db.read() as conn:
        return read(conn)


def update(changes: Dict[str, Any]) -> Dict[str, Any]:
    """Applies the given switches; returns {"before": ..., "after": ...}."""
    with db.write() as conn:
        before = read(conn)
        for flag in _FLAGS:
            if flag in changes:
                db.set_setting(conn, flag, "1" if changes[flag] else "0")
        if "step_seconds" in changes:
            try:
                step = int(changes["step_seconds"])
            except (TypeError, ValueError):
                step = before["step_seconds"]
            db.set_setting(conn, "step_seconds", str(max(MIN_STEP_SECONDS, min(step, MAX_STEP_SECONDS))))
        after = read(conn)
    return {"before": before, "after": after}
