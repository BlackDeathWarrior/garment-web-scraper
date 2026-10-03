#!/usr/bin/env python3
"""Moves the shop from its SQLite file to PostgreSQL, once.

    python -m shop.to_postgres            # outputs/shop/shop.db -> SHOP_DATABASE_URL
    python -m shop.to_postgres path.db    # another file

Every table is copied as it is, in one transaction, into a database that holds
no accounts yet: accounts and their passwords, addresses, orders with their
history, the admin's switches, the session secret (so nobody is signed out)
and the carts. The file is only read. It stays where it is, as the copy to go
back to: without SHOP_DATABASE_URL the shop uses it again.

Stop the shop's server first, so nothing is written to the file while it is
being copied.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shop import db  # noqa: E402

# Parents before children, so every reference finds its row.
TABLES = ("users", "addresses", "orders", "order_items", "order_events", "settings", "payment_attempts", "cart_items")
# Tables that number their own rows: the numbering carries on after the copied ones.
NUMBERED = ("order_events", "payment_attempts")


def copy(source: Path) -> Dict[str, int]:
    """Copies the file's rows into the PostgreSQL database. Returns how many rows each table had."""
    if not db.database_url():
        raise SystemExit("Set SHOP_DATABASE_URL to the PostgreSQL database first (the shop's .env).")
    if not source.is_file():
        raise SystemExit("There is no database file at %s." % source)
    file = sqlite3.connect("file:%s?mode=ro" % source.as_posix(), uri=True)
    file.row_factory = sqlite3.Row
    copied: Dict[str, int] = {}
    try:
        with db.write() as conn:
            if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise SystemExit("That database already holds accounts. Nothing was copied.")
            for table in TABLES:
                if not file.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
                    copied[table] = 0
                    continue
                rows = file.execute("SELECT * FROM %s" % table).fetchall()
                for row in rows:
                    values = dict(row)
                    if table == "cart_items":
                        # A file from before carts kept when a line was added.
                        values.setdefault("added_at", values["updated_at"])
                    names = ", ".join('"%s"' % name for name in values)
                    marks = ", ".join("?" for _ in values)
                    # The session secret may be there already, from a server that started on the empty database.
                    clash = ' ON CONFLICT("key") DO UPDATE SET "value" = excluded."value"' if table == "settings" else ""
                    conn.execute(
                        "INSERT INTO %s(%s) VALUES(%s)%s" % (table, names, marks, clash), tuple(values.values())
                    )
                copied[table] = len(rows)
            for table in NUMBERED:
                conn.execute(
                    "SELECT setval(pg_get_serial_sequence('%s', 'id'), COALESCE((SELECT MAX(id) FROM %s), 0) + 1, false)"
                    % (table, table)
                )
    finally:
        file.close()
    return copied


def main() -> None:
    from shop.server import load_env

    load_env()
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(db.DB_FILE)
    for table, rows in copy(source).items():
        print("%-18s %d" % (table, rows))
    print("Copied from %s. The file was not changed." % source)


if __name__ == "__main__":
    main()
