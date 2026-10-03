"""The cart of a signed-in shopper, kept by the shop.

It is the same cart in every browser, and support can change it when the
shopper asks (shop/support.py). A guest's cart stays in their browser
(frontend/src/lib/cart.js) and is folded in when they sign in.

Only what was chosen is kept: the product, the size and how many. What an item
is called and what it costs is read from the catalogue every time, as at
checkout, so a price here can never be out of date. This module is the only
one that reads or writes cart_items.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from shop import catalog, db
from shop.orders import MAX_LINES, MAX_QUANTITY, SIZES, OrderError

# What a change did to the cart.
ADDED, UPDATED, REMOVED, UNCHANGED = "added", "updated", "removed", "unchanged"


def _title(product: Dict[str, Any]) -> str:
    return " ".join(str(product.get("title") or "This item").split())[:60]


def _quantity(raw: Any) -> Optional[int]:
    """A whole number, or None: 1.5 and True are not quantities."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, float):
        return int(raw) if raw.is_integer() else None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _size(raw: Any) -> str:
    """The size as stored: '' for a line without one."""
    return " ".join(str(raw or "").split())[:20]


def _lines(conn: sqlite3.Connection, user_id: str) -> List[sqlite3.Row]:
    # In the order things were added; changing a quantity does not move a line.
    return conn.execute(
        "SELECT product_id, size, quantity FROM cart_items WHERE user_id = ? ORDER BY added_at, product_id, size",
        (user_id,),
    ).fetchall()


def _view(conn: sqlite3.Connection, user_id: str) -> Dict[str, Any]:
    items = []
    subtotal = 0.0
    for row in _lines(conn, user_id):
        product = catalog.get(row["product_id"])
        price = catalog.price(product) if product else None
        # Still in the cart, but checkout would refuse it: gone, unpriced or sold out.
        available = bool(product) and price is not None and product.get("in_stock") is not False
        if available:
            subtotal += price * row["quantity"]
        items.append(
            {
                "productId": row["product_id"],
                "title": _title(product) if product else "An item we no longer sell",
                "brand": product.get("brand") if product else None,
                "imageUrl": product.get("image_url") if product else None,
                "size": row["size"] or None,
                "quantity": row["quantity"],
                "price": price,
                "available": available,
            }
        )
    return {"items": items, "count": sum(item["quantity"] for item in items), "subtotal": round(subtotal, 2)}


def _held(conn: sqlite3.Connection, user_id: str, product_id: str, size: str) -> int:
    row = conn.execute(
        "SELECT quantity FROM cart_items WHERE user_id = ? AND product_id = ? AND size = ?",
        (user_id, product_id, size),
    ).fetchone()
    return row["quantity"] if row else 0


def _put(conn: sqlite3.Connection, user_id: str, product_id: str, size: str, quantity: int) -> None:
    moment = db.iso()
    conn.execute(
        """INSERT INTO cart_items(user_id, product_id, size, quantity, added_at, updated_at) VALUES(?,?,?,?,?,?)
           ON CONFLICT(user_id, product_id, size) DO UPDATE SET quantity = excluded.quantity,
             updated_at = excluded.updated_at""",
        (user_id, product_id, size, quantity, moment, moment),
    )


def _full(conn: sqlite3.Connection, user_id: str) -> bool:
    return conn.execute("SELECT COUNT(*) AS n FROM cart_items WHERE user_id = ?", (user_id,)).fetchone()["n"] >= MAX_LINES


def view(user_id: str) -> Dict[str, Any]:
    with db.read() as conn:
        return _view(conn, user_id)


def set_item(
    user_id: str, product_id: Any, size: Any, quantity: Any, by_support: bool = False
) -> Tuple[str, Dict[str, Any]]:
    """Makes the cart hold exactly `quantity` of a product in a size; 0 takes it out.

    Returns what happened and the cart afterwards. Saying the same thing twice
    changes nothing, so a repeated request is harmless.

    The storefront names the line it means, with or without a size. Support
    (`by_support`) speaks for the shopper from a conversation: to add, it must
    give a size instead of leaving it out, and "take it out" without a size
    means the product in every size.
    """
    product_id = str(product_id or "").strip()[:200]
    wanted = _quantity(quantity)
    size = _size(size)
    if wanted is None or wanted < 0 or wanted > MAX_QUANTITY:
        raise OrderError(400, "invalid", "You can have 0 to %d of each item." % MAX_QUANTITY)

    with db.write() as conn:
        if wanted == 0:
            if size or not by_support:
                gone = conn.execute(
                    "DELETE FROM cart_items WHERE user_id = ? AND product_id = ? AND size = ?",
                    (user_id, product_id, size),
                ).rowcount
            else:
                gone = conn.execute(
                    "DELETE FROM cart_items WHERE user_id = ? AND product_id = ?", (user_id, product_id)
                ).rowcount
            return (REMOVED if gone else UNCHANGED), _view(conn, user_id)

        if (size or by_support) and size not in SIZES:
            raise OrderError(400, "invalid", "Choose a size: %s or %s." % (", ".join(SIZES[:-1]), SIZES[-1]))
        product = catalog.get(product_id)
        if product is None:
            raise OrderError(404, "not-found", "No product has the id %s." % (product_id[:80] or "given"))
        product_id = str(product["id"])
        if catalog.price(product) is None:
            raise OrderError(409, "unavailable", "%s has no price at the moment." % _title(product))
        held = _held(conn, user_id, product_id, size)
        if held == wanted:
            return UNCHANGED, _view(conn, user_id)
        # Having fewer of something is always allowed; more of a sold-out item is not.
        if wanted > held and product.get("in_stock") is False:
            raise OrderError(409, "sold-out", "%s is sold out." % _title(product))
        if not held and _full(conn, user_id):
            raise OrderError(409, "cart-full", "The cart is full: it can hold %d different items." % MAX_LINES)
        _put(conn, user_id, product_id, size, wanted)
        return (UPDATED if held else ADDED), _view(conn, user_id)


def merge(user_id: str, items: Any) -> Dict[str, Any]:
    """Folds a browser's cart into the account's at sign-in and returns the result.

    For a line both have, the larger quantity wins, so sending the same cart
    twice changes nothing. A line that cannot be taken (a product that is gone,
    a full cart) is left out: an old browser cart must not get in the way of
    signing in.
    """
    with db.write() as conn:
        for entry in (items if isinstance(items, list) else [])[:MAX_LINES]:
            entry = entry if isinstance(entry, dict) else {}
            product = catalog.get(entry.get("productId"))
            quantity = _quantity(entry.get("quantity"))
            if product is None or catalog.price(product) is None or quantity is None or quantity < 1:
                continue
            size = _size(entry.get("size"))
            if size not in SIZES:
                size = ""
            product_id = str(product["id"])
            held = _held(conn, user_id, product_id, size)
            wanted = max(held, min(quantity, MAX_QUANTITY))
            if wanted == held or (not held and _full(conn, user_id)):
                continue
            _put(conn, user_id, product_id, size, wanted)
        return _view(conn, user_id)


def clear(conn: sqlite3.Connection, user_id: str) -> None:
    """Empties the cart inside the caller's transaction: an order was placed from it."""
    conn.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
