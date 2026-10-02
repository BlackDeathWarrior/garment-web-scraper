"""The products on sale: the catalogue file the storefront also reads."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CATALOG_FILE = ROOT / "frontend" / "public" / "products.json"

# What support may be told about a product: what a shopper already sees.
PUBLIC_FIELDS = ("id", "title", "brand", "price_current", "price_original", "category", "target_gender", "in_stock")

_lock = threading.Lock()
_cache: Dict[str, Any] = {"path": None, "mtime": None, "by_id": {}, "all": []}


def _load() -> Dict[str, Any]:
    path = Path(CATALOG_FILE)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {"by_id": {}, "all": []}
    with _lock:
        if _cache["path"] == path and _cache["mtime"] == mtime:
            return _cache
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return {"by_id": {}, "all": []}
    items = [p for p in loaded if isinstance(p, dict) and p.get("id")] if isinstance(loaded, list) else []
    with _lock:
        _cache.update(path=path, mtime=mtime, all=items, by_id={str(p["id"]): p for p in items})
        return _cache


def get(product_id: Any) -> Optional[Dict[str, Any]]:
    return _load()["by_id"].get(str(product_id).strip())


def count() -> int:
    return len(_load()["all"])


def price(product: Dict[str, Any]) -> Optional[float]:
    try:
        value = float(product.get("price_current"))
    except (TypeError, ValueError):
        return None
    return round(value, 2) if value > 0 else None


def public(product: Dict[str, Any]) -> Dict[str, Any]:
    return {key: product.get(key) for key in PUBLIC_FIELDS if product.get(key) is not None}


def search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Products whose title or brand has every word of `query`, shortest title first."""
    words = [w for w in str(query).lower().split() if w]
    if not words:
        return []
    found = []
    for product in _load()["all"]:
        text = ("%s %s" % (product.get("title") or "", product.get("brand") or "")).lower()
        if all(word in text for word in words):
            found.append(product)
            if len(found) >= 200:
                break
    found.sort(key=lambda p: len(str(p.get("title") or "")))
    return [public(p) for p in found[: max(1, min(limit, 10))]]
