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
    r"\bsalwar\b",
    r"\bpalazzo\b",
}

# Categories that are definitively men's when no other signal exists
_MEN_ONLY_CATEGORIES = {
    r"\bsherwani\b",
    r"\bnehru\s+jacket\b",
    r"\bdhoti\b",
    r"\bpathani\b",
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

        cur = d.get("price_current")
        orig = d.get("price_original")
        if cur and orig and orig > cur:
            d["discount_percent"] = round((1 - cur / orig) * 100)
        else:
            d["price_original"] = None
            d["discount_percent"] = None

        # Enhanced Gender Logic: Supports Unisex and Fallback
        gender = _normalize_gender(d.get("target_gender")) or _infer_target_gender(
            d["title"], d.get("category")
        )

        # Fix: If we still don't know the gender but it's a valid ethnic garment, 
        # label as Unisex so it's not deleted.
        if not gender:
            if d.get("category") or _infer_category(d["title"]):
                gender = "Unisex"
            else:
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
    """Normalize a raw gender string; returns Men, Women, or Unisex."""
    if not raw:
        return None
    v = str(raw).lower()
    
    is_women = re.search(r"\b(women|woman|ladies|female)\b", v)
    is_men = re.search(r"\b(men|man|male|mens)\b", v)
    
    if is_women and is_men:
        return "Unisex"
    if is_women:
        return "Women"
    if is_men:
        return "Men"
    
    return None


def _infer_target_gender(title: str, category: Optional[str] = None) -> Optional[str]:
    text = f"{title or ''} {category or ''}".lower()

    if re.search(r"\b(kids?|boys?|girls?|children|child|infant|toddler)\b", text):
        return None

    is_women = re.search(r"\b(women|woman|ladies|female)\b", text)
    is_men = re.search(r"\b(men|man|male|mens)\b", text)

    # Specific category checks for fallback
    has_women_cat = any(re.search(p, text) for p in _WOMEN_ONLY_CATEGORIES)
    has_men_cat = any(re.search(p, text) for p in _MEN_ONLY_CATEGORIES)

    if (is_women or has_women_cat) and (is_men or has_men_cat):
        return "Unisex"
    if is_women or has_women_cat:
        return "Women"
    if is_men or has_men_cat:
        return "Men"

    return None
