"""The shop's database.

With SHOP_DATABASE_URL set it is a PostgreSQL server, which is how the shop
runs for real: several processes, real column types, connections kept open.
Without it, it is a SQLite file (SHOP_DB), which a fresh clone and the tests
use because it needs nothing installed.

The rest of the shop does not know which one it has. It writes one SQL, with
`?` for each value, reads rows by column name, and gets every date and time
back as the ISO text it stored. What differs between the two is in this file.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

try:  # Only needed with SHOP_DATABASE_URL: pip install "psycopg[binary]"
    import psycopg
    from psycopg.adapt import Loader
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - the SQLite file needs nothing
    psycopg = None

ROOT = Path(__file__).resolve().parent.parent
# Tests point this at a temporary file.
DB_FILE = Path(os.environ.get("SHOP_DB") or ROOT / "outputs" / "shop" / "shop.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS addresses (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  phone TEXT NOT NULL,
  line1 TEXT NOT NULL,
  line2 TEXT NOT NULL DEFAULT '',
  city TEXT NOT NULL,
  state TEXT NOT NULL,
  pincode TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  status TEXT NOT NULL,
  placed_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  address TEXT NOT NULL,
  delivery_option TEXT NOT NULL,
  payment_method TEXT NOT NULL,
  payment_status TEXT NOT NULL,
  subtotal REAL NOT NULL,
  shipping_fee REAL NOT NULL,
  total REAL NOT NULL,
  carrier TEXT,
  tracking_number TEXT,
  expected_delivery TEXT NOT NULL,
  next_step_at TEXT,
  held INTEGER NOT NULL DEFAULT 0,
  delayed INTEGER NOT NULL DEFAULT 0,
  cancel_reason TEXT,
  return_reason TEXT,
  refund_id TEXT,
  refund_amount REAL,
  refunded_at TEXT
);
CREATE INDEX IF NOT EXISTS orders_user_idx ON orders(user_id, placed_at);
CREATE INDEX IF NOT EXISTS orders_step_idx ON orders(next_step_at);
CREATE TABLE IF NOT EXISTS order_items (
  order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  line INTEGER NOT NULL,
  product_id TEXT NOT NULL,
  title TEXT NOT NULL,
  brand TEXT,
  image_url TEXT,
  size TEXT,
  price REAL NOT NULL,
  quantity INTEGER NOT NULL,
  PRIMARY KEY (order_id, line)
);
CREATE TABLE IF NOT EXISTS order_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS order_events_order_idx ON order_events(order_id, id);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- A checkout whose payment did not go through: no order exists, so support
-- would otherwise have nothing to look at. Nothing is charged, and no payment
-- detail is kept: only the method and the amount that was due.
CREATE TABLE IF NOT EXISTS payment_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id),
  method TEXT NOT NULL,
  amount REAL NOT NULL,
  failed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS payment_attempts_user_idx ON payment_attempts(user_id, failed_at);

-- A signed-in shopper's cart (shop/cart.py). Only what was chosen: names and
-- prices come from the catalogue when the cart is read. size is '' for none.
CREATE TABLE IF NOT EXISTS cart_items (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL,
  size TEXT NOT NULL DEFAULT '',
  quantity INTEGER NOT NULL,
  added_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, product_id, size)
);
"""

# The same tables on PostgreSQL, with the types a server gives: real times
# and dates, checked quantities, and an index for every way a table is read.
# Money is double precision, as in the file: no money moves in this shop.
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS addresses (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  phone TEXT NOT NULL,
  line1 TEXT NOT NULL,
  line2 TEXT NOT NULL DEFAULT '',
  city TEXT NOT NULL,
  state TEXT NOT NULL,
  pincode TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS addresses_user_idx ON addresses(user_id, created_at);
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  status TEXT NOT NULL,
  placed_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  address TEXT NOT NULL,
  delivery_option TEXT NOT NULL,
  payment_method TEXT NOT NULL,
  payment_status TEXT NOT NULL,
  subtotal DOUBLE PRECISION NOT NULL CHECK (subtotal >= 0),
  shipping_fee DOUBLE PRECISION NOT NULL CHECK (shipping_fee >= 0),
  total DOUBLE PRECISION NOT NULL CHECK (total >= 0),
  carrier TEXT,
  tracking_number TEXT,
  expected_delivery DATE NOT NULL,
  next_step_at TIMESTAMPTZ,
  held INTEGER NOT NULL DEFAULT 0 CHECK (held IN (0, 1)),
  delayed INTEGER NOT NULL DEFAULT 0 CHECK (delayed IN (0, 1)),
  cancel_reason TEXT,
  return_reason TEXT,
  refund_id TEXT,
  refund_amount DOUBLE PRECISION,
  refunded_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS orders_user_idx ON orders(user_id, placed_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS orders_placed_idx ON orders(placed_at DESC, id DESC);
-- The clock asks every second for what is due: only orders still moving are in here.
CREATE INDEX IF NOT EXISTS orders_step_idx ON orders(next_step_at) WHERE next_step_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS orders_delayed_idx ON orders(id) WHERE delayed = 1;
CREATE TABLE IF NOT EXISTS order_items (
  order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  line INTEGER NOT NULL,
  product_id TEXT NOT NULL,
  title TEXT NOT NULL,
  brand TEXT,
  image_url TEXT,
  size TEXT,
  price DOUBLE PRECISION NOT NULL CHECK (price >= 0),
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  PRIMARY KEY (order_id, line)
);
CREATE TABLE IF NOT EXISTS order_events (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS order_events_order_idx ON order_events(order_id, id);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_attempts (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  method TEXT NOT NULL,
  amount DOUBLE PRECISION NOT NULL CHECK (amount >= 0),
  failed_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS payment_attempts_user_idx ON payment_attempts(user_id, failed_at DESC);
CREATE TABLE IF NOT EXISTS cart_items (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL,
  size TEXT NOT NULL DEFAULT '',
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  added_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (user_id, product_id, size)
);
"""

# What a second account with the same email raises, on either database.
IntegrityError: Tuple[type, ...] = (sqlite3.IntegrityError,) + ((psycopg.IntegrityError,) if psycopg else ())

# One lock for every writer, taken for the length of a transaction. The shop's
# code was written for a database with one writer at a time (it reads a counter
# and then writes it); this keeps that true on a server.
_WRITE_LOCK = 0x45544853  # "ETHS"
# A connection that sat idle longer than this is checked before it is used again.
_IDLE_CHECK_SECONDS = 30
_MAX_IDLE = 8

_init_lock = threading.Lock()
_initialised: Optional[object] = None
_idle_lock = threading.Lock()
_idle: List[Tuple[Any, float]] = []


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: Optional[datetime] = None) -> str:
    return (moment or now()).isoformat(timespec="seconds")


def database_url() -> str:
    """The PostgreSQL address, or '' for the SQLite file. Read each time: .env is loaded after this module."""
    return (os.environ.get("SHOP_DATABASE_URL") or "").strip().strip("'\"")


if psycopg:

    class _IsoTime(Loader):
        """A time as the shop writes it: `2026-10-03T09:15:00+00:00`."""

        def load(self, data: Any) -> str:
            moment = datetime.fromisoformat(bytes(data).decode("ascii"))
            return moment.astimezone(timezone.utc).isoformat(timespec="seconds")

    class _IsoDate(Loader):
        def load(self, data: Any) -> str:
            return bytes(data).decode("ascii")


class _Postgres:
    """A PostgreSQL connection that takes the shop's SQL. Closing it hands it back for the next piece of work."""

    def __init__(self, raw: Any):
        self.raw = raw

    def execute(self, sql: str, params: Any = ()) -> Any:
        return self.raw.execute(sql.replace("?", "%s"), params or None)

    def close(self) -> None:
        raw, self.raw = self.raw, None
        if raw is None or raw.closed:
            return
        try:
            if raw.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                raw.execute("ROLLBACK")
        except psycopg.Error:
            raw.close()
            return
        with _idle_lock:
            if len(_idle) < _MAX_IDLE:
                _idle.append((raw, time.monotonic()))
                return
        raw.close()


def _postgres(url: str) -> _Postgres:
    global _initialised
    if psycopg is None:
        raise RuntimeError('SHOP_DATABASE_URL is set but psycopg is not installed: pip install "psycopg[binary]"')
    raw = None
    while raw is None:
        with _idle_lock:
            kept = _idle.pop() if _idle else None
        if kept is None:
            break
        candidate, since = kept
        try:
            if time.monotonic() - since > _IDLE_CHECK_SECONDS:
                candidate.execute("SELECT 1")
            raw = candidate
        except psycopg.Error:  # The server went away while it waited: open a new one.
            candidate.close()
    if raw is None:
        # Each statement is its own transaction until write() opens one, as with the file.
        raw = psycopg.connect(url, autocommit=True, row_factory=dict_row, options="-c timezone=UTC")
        raw.adapters.register_loader("timestamptz", _IsoTime)
        raw.adapters.register_loader("date", _IsoDate)
    if _initialised != url:
        with _init_lock:
            if _initialised != url:
                # Two processes starting together must not both create the tables.
                raw.execute("BEGIN")
                raw.execute("SELECT pg_advisory_xact_lock(%s)", (_WRITE_LOCK,))
                raw.execute(POSTGRES_SCHEMA)
                raw.execute("COMMIT")
                _initialised = url
    return _Postgres(raw)


def connect() -> Any:
    global _initialised
    url = database_url()
    if url:
        return _postgres(url)
    path = Path(DB_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if _initialised != path:
        with _init_lock:
            if _initialised != path:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript(SCHEMA)
                _initialised = path
    return conn


@contextmanager
def read() -> Iterator[Any]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def write() -> Iterator[Any]:
    """One transaction that takes the write lock at once, so two requests cannot interleave."""
    conn = connect()
    try:
        if isinstance(conn, _Postgres):
            conn.execute("BEGIN")
            conn.execute("SELECT pg_advisory_xact_lock(?)", (_WRITE_LOCK,))
        else:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except (sqlite3.Error,) + ((psycopg.Error,) if psycopg else ()):
            pass
        raise
    finally:
        conn.close()


def get_setting(conn: Any, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: Any, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def reset_for_tests() -> None:
    global _initialised
    _initialised = None
    with _idle_lock:
        while _idle:
            _idle.pop()[0].close()
