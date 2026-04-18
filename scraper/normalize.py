import re
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from .parsers.base import RawProduct

# Categories that are definitively women's when no other signal exists
_WOMEN_ONLY_CATEGORIES = {
    r"\bsaree\b",
    r"\blehenga\b",
    r"\banarkali\b",
    r"\bkurti\b",
    r"\btunic\b",
}

# Categories that are definitively men's when no other signal exists
_MEN_ONLY_CATEGORIES = {
    r"\bsherwani\b",
    r"\bnehru\s+jacket\b",
    r"\bdhoti\b",
}


def normalize(products: list[RawProduct]) -> list[dict]:
    """Deduplicate, clean, and gender-filter a merged list of RawProduct objects."""
    seen: set[str] = set()
    result = []

    for p in products:
        if not p.is_valid():
            continue
        key = _dedup_key(p)
        if key in seen:
            continue
        seen.add(key)

        d = p.to_dict()
        d["title"] = _clean_text(d.get("title") or "")
        d["brand"] = _clean_text(d.get("brand") or "") or None
        d["category"] = _clean_text(d.get("category") or "") or _infer_category(d["title"])

        # Always recalculate discount from actual prices.
        # Scraped discount_percent values (especially Myntra) often store the
        # absolute saving amount in rupees, not a percentage; never trust them.
        cur = d.get("price_current")
        orig = d.get("price_original")
        if cur and orig and orig > cur:
            d["discount_percent"] = round((1 - cur / orig) * 100)
        else:
            d["price_original"] = None
            d["discount_percent"] = None

        gender = _normalize_gender(d.get("target_gender")) or _infer_target_gender(
            d["title"], d.get("category")
        )

        # Only keep Men and Women; drop Kids/Girls/Boys/unresolved.
        if gender not in ("Men", "Women"):
            continue

        d["target_gender"] = gender
        result.append(d)

    return result


def _dedup_key(p: RawProduct) -> str:
    source = str(p.source or "").strip().lower()
    url_norm = _normalize_product_url(p.product_url)
    if source and url_norm:
        return f"{source}::{url_norm}"

    title_norm = re.sub(r"\s+", " ", (p.title or "").lower().strip())[:120]
    return f"{source}::{title_norm}"


def _normalize_product_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    value = str(url).strip()
    if not value:
        return None

    try:
        parts = urlsplit(value)
    except ValueError:
        return value.rstrip("/").lower()

    if not parts.scheme or not parts.netloc:
        return value.rstrip("/").lower()

    clean_path = re.sub(r"/+", "/", parts.path or "/").rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            clean_path,
            "",
            "",
        )
    )


def _clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _infer_category(title: str) -> Optional[str]:
    t = (title or "").lower()
    rules = [
        # Men's categories
        (r"\bkurta\s*set\b|\bkurta\s*pyjama\b", "Kurta Set"),
        (r"\bsherwani\b", "Sherwani"),
        (r"\bnehru\s+jacket\b", "Nehru Jacket"),
        (r"\bdhoti\b", "Dhoti"),
        (r"\bethnic\s*set\b", "Ethnic Set"),
        # Women's categories
        (r"\bkurti\b", "Kurti"),
        (r"\btunic\b", "Tunic"),
        (r"\bsaree\b", "Saree"),
        (r"\blehenga\b|\blehenga\s*choli\b", "Lehenga Choli"),
        (r"\bsalwar\b|\bkameez\b|\bchuridar\b|\bsuit\b", "Salwar Suit"),
        # Shared
        (r"\bkurta\b", "Kurta"),
        (r"\bpalazzo\b|\bco-?ord\b", "Co-Ord Set"),
        (r"\bethnic\s*dress\b|\bdress\b", "Ethnic Dress"),
        (r"\bethnic\s*wear\b|\bethnic\b", "Ethnic Wear"),
        (r"\banarkali\b", "Anarkali"),
    ]
    for pattern, label in rules:
        if re.search(pattern, t):
            return label
    return None


def _normalize_gender(raw: Optional[str]) -> Optional[str]:
    """Normalize a raw gender string; returns only Men/Women or None."""
    if not raw:
        return None
    v = str(raw).lower()
    # Women must be checked before Men because "women" contains "men"
    if any(x in v for x in ("women", "woman", "ladies", "female")):
        return "Women"
    if any(x in v for x in ("men", "man", "male", "mens")):
        return "Men"
    return None


def _infer_target_gender(title: str, category: Optional[str] = None) -> Optional[str]:
    text = f"{title or ''} {category or ''}".lower()

    # Strictly exclude children's products from inference.
    if re.search(r"\b(kids?|boys?|girls?|children|child|infant|toddler)\b", text):
        return None

    # Explicit gender keywords. Women checked before Men to avoid false matches.
    if re.search(r"\b(women|woman|ladies|female)\b", text):
        return "Women"
    if re.search(r"\b(men|man|male|mens)\b", text):
        return "Men"

    # Category-based defaults for unambiguously gendered garments
    for pattern in _WOMEN_ONLY_CATEGORIES:
        if re.search(pattern, text):
            return "Women"
    for pattern in _MEN_ONLY_CATEGORIES:
        if re.search(pattern, text):
            return "Men"

    return None
