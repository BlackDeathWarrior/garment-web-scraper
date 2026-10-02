"""The warehouse and carrier clock, and what the admin's switches do.

Orders move one step every `step_seconds`. Two things can be made to go
wrong, from the admin's Operations page:

- payments_down: paying by UPI or card fails at checkout (cash on delivery
  still works). Each failed checkout is reported to the support desk.
- carrier_delay: orders that are with the carrier stop moving and are marked
  late. That is reported too.

Switching either off reports the recovery. A support desk that is not set
up, or is down, changes nothing here.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from scraper.support import incidents
from shop import db, orders, switches

PAYMENTS_FINGERPRINT = "shop.payments_failing"
DELAY_FINGERPRINT = "shop.shipping_delayed"
TICK_SECONDS = 1.0
# With the carrier: these are the steps a delay stops.
WITH_CARRIER = ("shipped", "out_for_delivery")


def _background(target, *args, **kwargs) -> None:
    threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True).start()


def payment_failed(method: str) -> None:
    """A checkout could not be paid for. Tells the support desk, off the shopper's request."""
    _background(
        incidents.report,
        PAYMENTS_FINGERPRINT,
        "Payments are failing at checkout",
        severity="critical",
        source="shop/checkout",
        message="A shopper could not pay by %s. Cash on delivery still works." % orders.PAYMENTS.get(method, method),
        details={"method": method},
        # Every failed checkout is a shopper turned away: count each one.
        min_interval=0,
    )


def tick(now: Optional[datetime] = None) -> Dict[str, int]:
    """Moves every order that is due. Returns how many advanced and how many are newly late."""
    moment = now or db.now()
    advanced = 0
    newly_late = 0
    with db.write() as conn:
        state = switches.read(conn)
        due = conn.execute(
            "SELECT * FROM orders WHERE next_step_at IS NOT NULL AND next_step_at <= ? AND held = 0 ORDER BY placed_at",
            (db.iso(moment),),
        ).fetchall()
        for row in due:
            if state["carrier_delay"] and row["status"] in WITH_CARRIER:
                later = db.iso(moment + timedelta(seconds=state["step_seconds"]))
                conn.execute("UPDATE orders SET next_step_at = ?, delayed = 1 WHERE id = ?", (later, row["id"]))
                if not row["delayed"]:
                    conn.execute("UPDATE orders SET updated_at = ? WHERE id = ?", (db.iso(moment), row["id"]))
                    orders._event(conn, row["id"], row["status"], "Delayed with the carrier", at=db.iso(moment))
                    newly_late += 1
                continue
            if orders.step(conn, row, state["step_seconds"], at=moment):
                advanced += 1
        late = conn.execute("SELECT count(*) AS n FROM orders WHERE delayed = 1").fetchone()["n"]
    if newly_late:
        _background(
            incidents.report,
            DELAY_FINGERPRINT,
            "Orders are delayed with the carrier",
            severity="error",
            source="shop/fulfilment",
            message="%d order%s with %s %s not moving. Shoppers see their order as delayed."
            % (late, "" if late == 1 else "s", orders.CARRIER, "is" if late == 1 else "are"),
            details={"carrier": orders.CARRIER, "delayed_orders": late},
            min_interval=0,
        )
    return {"advanced": advanced, "newly_late": newly_late}


def set_switches(changes: Dict[str, Any]) -> Dict[str, Any]:
    """Applies the admin's switches and reports what recovered."""
    result = switches.update(changes)
    before, after = result["before"], result["after"]
    if before["payments_down"] and not after["payments_down"]:
        _background(incidents.recovered, PAYMENTS_FINGERPRINT, "Payments are going through again.")
    if before["carrier_delay"] and not after["carrier_delay"]:
        moving = _release_delayed(after["step_seconds"])
        _background(
            incidents.recovered,
            DELAY_FINGERPRINT,
            "%s is moving again: %d order%s back on the way." % (orders.CARRIER, moving, "" if moving == 1 else "s"),
        )
    return after


def _release_delayed(step_seconds: int) -> int:
    with db.write() as conn:
        late = conn.execute("SELECT id, status FROM orders WHERE delayed = 1").fetchall()
        moment = db.now()
        for row in late:
            conn.execute(
                "UPDATE orders SET delayed = 0, next_step_at = ?, updated_at = ? WHERE id = ?",
                (db.iso(moment + timedelta(seconds=step_seconds)), db.iso(moment), row["id"]),
            )
            orders._event(conn, row["id"], row["status"], "Moving again", at=db.iso(moment))
        return len(late)


def status() -> Dict[str, Any]:
    """How the shop is doing, in plain facts (the admin page, and the AI's shop_status tool)."""
    with db.read() as conn:
        state = switches.read(conn)
        in_progress = conn.execute(
            "SELECT count(*) AS n FROM orders WHERE status IN ('placed','packed','shipped','out_for_delivery')"
        ).fetchone()["n"]
        late = conn.execute("SELECT count(*) AS n FROM orders WHERE delayed = 1").fetchone()["n"]
    return {
        "payments": "failing" if state["payments_down"] else "working",
        "cash_on_delivery": "working",
        "carrier": "delayed" if state["carrier_delay"] else "on time",
        "orders_in_progress": in_progress,
        "delayed_orders": late,
    }


def start(stop: Optional[threading.Event] = None) -> threading.Thread:
    stop = stop or threading.Event()

    def loop() -> None:
        while not stop.is_set():
            try:
                tick()
            except Exception as exc:  # The clock must keep running whatever one tick hits.
                print("[shop] tick failed: %s" % exc, flush=True)
            stop.wait(TICK_SECONDS)

    thread = threading.Thread(target=loop, name="shop-clock", daemon=True)
    thread.start()
    return thread
