"""Facts about the scraped catalogue: how many products, how old, one product by id.

Reads the same products.json the storefront shows, and caches it until the
file changes.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
CANDIDATES = (
    ROOT / "frontend" / "public" / "products.json",
    ROOT / "outputs" / "products.json",
)

# What the support desk may be told about a listing: what a shopper can already see.
PUBLIC_FIELDS = (
    "id",
    "title",
    "brand",
    "source",
    "product_url",
    "price_current",
    "price_original",
    "discount_percent",
    "category",
    "target_gender",
    "in_stock",
    "rating",
    "scraped_at",
)

_lock = threading.Lock()
_cache: Dict[str, Any] = {"path": None, "mtime": None, "products": []}


def catalog_file() -> Optional[Path]:
    for path in CANDIDATES:
        if path.is_file():
            return path
    return None


def products() -> List[Dict[str, Any]]:
    path = catalog_file()
    if path is None:
        return []
    mtime = path.stat().st_mtime
    with _lock:
        if _cache["path"] == path and _cache["mtime"] == mtime:
            return _cache["products"]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception:
        return []
    items = [p for p in loaded if isinstance(p, dict)] if isinstance(loaded, list) else []
    with _lock:
        _cache.update(path=path, mtime=mtime, products=items)
    return items


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def public_view(product: Dict[str, Any]) -> Dict[str, Any]:
    return {key: product.get(key) for key in PUBLIC_FIELDS if product.get(key) is not None}


def find(product_id: str) -> Optional[Dict[str, Any]]:
    wanted = str(product_id).strip()
    for product in products():
        if str(product.get("id")) == wanted:
            return public_view(product)
    return None


def search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Listings whose title or brand has every word of `query`, best match first."""
    words = [w for w in str(query).lower().split() if w]
    if not words:
        return []
    found = []
    for product in products():
        text = ("%s %s" % (product.get("title") or "", product.get("brand") or "")).lower()
        if all(word in text for word in words):
            found.append(product)
            if len(found) >= 200:
                break
    # Shorter titles first: the closest match to a short query.
    found.sort(key=lambda p: len(str(p.get("title") or "")))
    return [public_view(p) for p in found[: max(1, min(limit, 10))]]


def status(stale_hours: int, now: Optional[datetime] = None) -> Dict[str, Any]:
    """How big and how fresh the catalogue is. `stale` is true past `stale_hours`."""
    items = products()
    current = now or datetime.now(timezone.utc)
    times = [t for t in (_parse_time(p.get("scraped_at")) for p in items) if t is not None]
    newest = max(times) if times else None
    age_hours = round((current - newest).total_seconds() / 3600, 1) if newest else None
    by_source: Dict[str, int] = {}
    for product in items:
        name = str(product.get("source") or "unknown").lower()
        by_source[name] = by_source.get(name, 0) + 1
    return {
        "products": len(items),
        "by_source": by_source,
        "newest_scraped_at": newest.isoformat() if newest else None,
        "oldest_scraped_at": min(times).isoformat() if times else None,
        "age_hours": age_hours,
        "age_days": round(age_hours / 24, 1) if age_hours is not None else None,
        "stale_after_hours": stale_hours,
        "stale": age_hours is None or age_hours > stale_hours,
    }
