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

# NUCLEAR EXCLUSION: Substrings that trigger immediate deletion if found anywhere
_BANNED_SUBSTRINGS = [
    "shoe", "footwear", "sandal", "slipper", "heel", "flat", "juttis", "mojaris", "loafer", "kolhapuri", "nagras",
    "necklace", "jewel", "earring", "bangle", "ring", "pendant", "bracelet", "anklet", "jhumka", "choker", "haram",
    "watch", "wallet", "belt", "sunglasses", "handbag", "purse", "clutch", "nosepin", "nath", "maang", "tika",
    "kamarband", "mangalsutra", "gold plated", "silver plated", "oxidised", "jewelry set", "jewellery set",
    "combo set", "combo of", "pack of", "artificial", "beads", "latkan", "tassels"
]


def calculate_trust_score(rating: Optional[float], count: Optional[int]) -> Optional[int]:
    """Calculate a heuristic AI Trust Score (0-100) based on rating and volume."""
    if not rating or not count or count == 0:
        return None
        
    # Base score out of 100
    base_score = (rating / 5.0) * 100
    
    # Volume modifier (confidence increases with more reviews)
    if count < 10:
        modifier = 0.80  # Low confidence
    elif count < 50:
        modifier = 0.90
    elif count < 500:
        modifier = 0.98
    elif count < 1000:
        modifier = 1.00
    else:
        # Bonus for massive review counts maintaining high averages
        modifier = min(1.05, 1.0 + (count / 50000))
        
    final_score = base_score * modifier
    return max(1, min(99, int(round(final_score))))


def normalize(products: list[RawProduct]) -> list[dict]:
    """Deduplicate, clean, and gender-filter a merged list of RawProduct objects."""
    # Use a dictionary to merge multi-source products
    # Key: (Normalized Brand + Normalized Title snippet)
    merged: dict[str, dict] = {}

    for p in products:
        if not p.is_valid():
            continue
            
        # 1. Nuclear Noise Filter (Case-insensitive substring match)
        # Explicitly purged 'jhumka' and 'earring'
        search_text = (f"{p.title or ''} {p.category or ''}").lower()
        if any(banned in search_text for banned in _BANNED_SUBSTRINGS + ["jhumka", "earring", "jewel"]):
            continue

        # Create a merge key for cross-source detection
        brand_norm = (p.brand or "generic").lower().strip()
        title_norm = re.sub(r"[^a-z0-9]", "", (p.title or "").lower())[:40]
        merge_key = f"{brand_norm}::{title_norm}"

        d = p.to_dict()
        
        # 2. IMAGE UPSCALING: Fix Blurry Images
        if d.get("image_url"):
            url = d["image_url"]
            if "images-amazon.com" in url or "media-amazon.com" in url:
                d["image_url"] = re.sub(r"\._[A-Za-z0-9_,]+_\.(jpg|jpeg|png)", r".\1", url, flags=re.I)
            elif "rukminim" in url:
                d["image_url"] = url.replace("/200/200/", "/800/800/").replace("/128/128/", "/800/800/")
            elif "assets.myntassets.com" in url:
                d["image_url"] = url.replace("/h_240,q_90,w_180/", "/h_1000,q_95,w_800/")

        d["title"] = _clean_text(d.get("title") or "")
        
        # Fix: Normalize Brand names to Title Case to prevent duplicates like MANYAVAR and manyavar
        raw_brand = _clean_text(d.get("brand") or "")
        d["brand"] = raw_brand.title() if raw_brand else None
        
        d["category"] = _clean_text(d.get("category") or "") or _infer_category(d["title"])

        # 3. Merging Logic
        if merge_key in merged:
            existing = merged[merge_key]
            # Track multiple sources
            if "other_sources" not in existing:
                existing["other_sources"] = []
            
            new_source_info = {
                "source": d["source"],
                "url": d["product_url"],
                "price": d["price_current"]
            }
            
            # Only add if source is different
            if d["source"] != existing["source"]:
                existing["other_sources"].append(new_source_info)
                # Keep the cheapest one as primary
                if d["price_current"] and existing["price_current"] and d["price_current"] < existing["price_current"]:
                    existing["price_current"] = d["price_current"]
                    existing["product_url"] = d["product_url"]
                    existing["source"] = d["source"]
            continue

        # First time seeing this product
        cur = d.get("price_current")
        orig = d.get("price_original")
        if cur and orig and orig > cur:
            d["discount_percent"] = round((1 - cur / orig) * 100)
        else:
            d["price_original"] = None
            d["discount_percent"] = None

        d["trust_score"] = calculate_trust_score(d.get("rating"), d.get("rating_count"))

        gender = _normalize_gender(d.get("target_gender")) or _infer_target_gender(
            d["title"], d.get("category")
        )

        if not gender:
            if d.get("category") or _infer_category(d["title"]):
                gender = "Unisex"
            else:
                continue

        d["target_gender"] = gender
        merged[merge_key] = d

    return list(merged.values())


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
