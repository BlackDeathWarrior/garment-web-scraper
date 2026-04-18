import asyncio
import json
import re
from typing import Callable, Optional

from bs4 import BeautifulSoup, Tag
from playwright.async_api import async_playwright, Page

from .base import BaseParser, RawProduct
from scraper import log


BASE_URL = "https://www.flipkart.com"

# (query, gender_hint) - scoped to required Men/Women ethnic categories only
SEARCH_QUERIES: list[tuple[str, str]] = [
    # Interleave Men/Women queries so checkpointed outputs stay more balanced.
    ("men+kurta+ethnic", "Men"),
    ("ethnic+kurta+women", "Women"),
    ("men+kurta+set+ethnic", "Men"),
    ("salwar+suit+women", "Women"),
    ("men+sherwani+ethnic", "Men"),
    ("salwar+kameez+women", "Women"),
    ("men+nehru+jacket", "Men"),
    ("women+kurti+ethnic", "Women"),
    ("men+dhoti+ethnic", "Men"),
    ("women+ethnic+top+tunic", "Women"),
    ("men+ethnic+kurta+pyjama+set", "Men"),
    ("saree+women", "Women"),
    ("women+ethnic+wear", "Women"),
    ("lehenga+choli+women", "Women"),
]

# Safety rails for pagination. Unlimited mode can continue until listings dry up.
DEFAULT_QUERY_PAGE_LIMIT = 3
UNLIMITED_QUERY_PAGE_LIMIT = 12
LOW_YIELD_THRESHOLD = 4
MAX_CONSECUTIVE_LOW_YIELD_PAGES = 2

# Ordered by likelihood of matching - Flipkart rotates class names often
_CARD_SEL = ["div[data-id]", "._1AtVbE > div", "._4ddWXP", ".cPHDOP", ".col"]
_TITLE_SEL = ["._4rR01T", ".KzDlHZ", ".WKTcLC", ".atJtCj", "a._2Kn22P", "a[title]"]
_PRICE_SEL = ["._30jeq3", "._1_WHN1", ".Nx9bqj", "._4b5DiR", ".hZ3P6w"]
_ORIG_PRICE_SEL = ["._3I9_wc", "._2p6lqe", ".yRaY8j", "._25b18", ".kRYCnD"]
_RATING_SEL = ["._3LWZlK", ".XQDdHH", "._1lRcqv"]
_RATING_COUNT_SEL = ["._2_R_DZ", ".Wphh3N", "._13vcmD", ".Wphh3N span", "._2MZnfa"]
_IMG_SEL = ["img._396cs4", "img._2r_T1I", "img.q6DClP", "img"]
_BRAND_SEL = ["._2WkVRV", ".syl9yP", "._3wU53n", ".Fo1I0b"]


class FlipkartParser(BaseParser):
    def __init__(self):
        super().__init__(delay_range=(3.0, 7.0))

    async def scrape(
        self,
        max_products: int = 100,
        on_progress: Callable[[list[RawProduct]], None] | None = None,
    ) -> list[RawProduct]:
        products: list[RawProduct] = []
        seen_urls: set[str] = set()
        limit_enabled = max_products > 0
        page_limit = DEFAULT_QUERY_PAGE_LIMIT if limit_enabled else UNLIMITED_QUERY_PAGE_LIMIT

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            context = await browser.new_context(
                user_agent=self._random_ua(),
                viewport={"width": 1920, "height": 1080},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            page = await context.new_page()

            query_states = {
                query: {"gender_hint": gender_hint, "active": True, "low_yield_streak": 0}
                for query, gender_hint in SEARCH_QUERIES
            }

            for pg in range(1, page_limit + 1):
                if limit_enabled and len(products) >= max_products:
                    break

                active_queries = [
                    query for query, state in query_states.items() if state["active"]
                ]
                if not active_queries:
                    break

                for query in active_queries:
                    if limit_enabled and len(products) >= max_products:
                        break

                    state = query_states[query]
                    gender_hint = state["gender_hint"]
                    try:
                        batch = await self._scrape_query(page, query, pg, seen_urls, gender_hint)
                        products.extend(batch)
                        log.scrape_batch("Flipkart", query, pg, len(batch), len(products))
                        if on_progress and batch:
                            try:
                                on_progress(products)
                            except Exception:
                                pass
                        if not batch:
                            state["active"] = False
                            continue
                        if len(batch) < LOW_YIELD_THRESHOLD:
                            state["low_yield_streak"] += 1
                            if state["low_yield_streak"] >= MAX_CONSECUTIVE_LOW_YIELD_PAGES:
                                log.warn(
                                    "Flipkart",
                                    f"'{query}' low yield for {state['low_yield_streak']} pages - moving on",
                                )
                                state["active"] = False
                        else:
                            state["low_yield_streak"] = 0
                    except Exception as exc:
                        log.error("Flipkart", f"'{query}' p{pg} failed: {exc}")
                        state["active"] = False

                    if state["active"]:
                        await self._random_delay()

            await browser.close()

        return products[:max_products] if limit_enabled else products

    async def _scrape_query(
        self, page: Page, query: str, page_num: int, seen_urls: set,
        gender_hint: Optional[str] = None,
    ) -> list[RawProduct]:
        url = f"{BASE_URL}/search?q={query}&sort=popularity&page={page_num}"
        captured: list[dict] = []

        async def _intercept(route, _request):
            try:
                response = await route.fetch()
                if response.status == 200 and "json" in response.headers.get("content-type", ""):
                    try:
                        captured.append(await response.json())
                    except Exception:
                        pass
                await route.fulfill(response=response)
            except Exception:
                try:
                    await route.continue_()
                except Exception:
                    pass

        # Capture XHR/fetch calls Flipkart uses to load product listings
        await page.route("**/api/**", _intercept)

        try:
            await page.goto(url, wait_until="networkidle", timeout=45_000)
        except Exception:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                await page.goto(url, wait_until="commit", timeout=30_000)

        # Wait until at least one product card selector resolves
        for sel in _CARD_SEL[:4]:
            try:
                await page.wait_for_selector(sel, timeout=8_000)
                break
            except Exception:
                continue

        await self._random_delay()

        # Dismiss location/login dialogs
        for sel in [
            "button._2KpZ6l._2doB4z",
            "button[class*='_2KpZ6l']",
            "._2AkmmA button",
            "button[aria-label='close']",
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1500):
                    await btn.click()
            except Exception:
                pass

        # Scroll to trigger lazy-loaded images and dynamic batches
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await asyncio.sleep(1.5)

        await _safe_unroute(page, "**/api/**")

        # Try captured API JSON first - most reliable
        for data in captured:
            batch = self._try_extract_from_json(data, seen_urls)
            if batch:
                return _apply_gender_hint(batch, gender_hint)

        html = await page.content()
        return _apply_gender_hint(self._parse_html(html, seen_urls), gender_hint)

    # ------------------------------------------------------------------ #
    # Parsing                                                              #
    # ------------------------------------------------------------------ #

    def _try_extract_from_json(self, data: dict, seen_urls: set) -> list[RawProduct]:
        """Extract products from any captured XHR JSON response."""
        raw_list = (
            self._deep_find(data, "products")
            or self._deep_find(data, "SEARCH_RESULT")
            or self._deep_find(data, "searchResult")
            or self._deep_find(data, "items")
            or []
        )
        if not raw_list:
            return []
        results = []
        for item in raw_list[:60]:
            try:
                p = self._map_next_item(item)
                if p and p.is_valid() and p.product_url not in seen_urls:
                    seen_urls.add(p.product_url)
                    results.append(p)
            except Exception:
                continue
        return results

    def _parse_html(self, html: str, seen_urls: set) -> list[RawProduct]:
        soup = BeautifulSoup(html, "html.parser")

        # Strategy 1: __NEXT_DATA__ JSON embed (SSR data)
        script = soup.find("script", id="__NEXT_DATA__")
        if script and script.string:
            try:
                products = self._parse_next_data(script.string, seen_urls)
                if products:
                    return products
            except Exception:
                pass

        # Strategy 2: JSON-LD structured data
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
                products = self._parse_json_ld(data, seen_urls)
                if products:
                    return products
            except Exception:
                continue

        # Strategy 3: HTML card parsing with selector fallbacks
        return self._parse_cards(soup, seen_urls)

    def _parse_next_data(self, json_str: str, seen_urls: set) -> list[RawProduct]:
        data = json.loads(json_str)
        raw_list = (
            self._deep_find(data, "products")
            or self._deep_find(data, "SEARCH")
            or []
        )
        results = []
        for item in raw_list[:60]:
            try:
                p = self._map_next_item(item)
                if p and p.is_valid() and p.product_url not in seen_urls:
                    seen_urls.add(p.product_url)
                    results.append(p)
            except Exception:
                continue
        return results

    def _deep_find(self, obj, key: str, depth: int = 0):
        if depth > 8:
            return None
        if isinstance(obj, dict):
            if key in obj:
                val = obj[key]
                if isinstance(val, list) and val:
                    return val
            for v in obj.values():
                r = self._deep_find(v, key, depth + 1)
                if r:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = self._deep_find(item, key, depth + 1)
                if r:
                    return r
        return None

    def _map_next_item(self, item: dict) -> Optional[RawProduct]:
        value = item.get("value") or item
        if isinstance(value, list):
            value = value[0] if value else {}

        title = (
            value.get("title")
            or value.get("name")
            or value.get("productName")
            or _deep_pick_scalar(value, {"title", "name", "productName", "displayName"})
        )
        url_path = (
            value.get("url")
            or value.get("productUrl")
            or value.get("href")
            or _deep_pick_scalar(value, {"url", "productUrl", "href", "landingPageUrl", "actionUrl"})
        )
        price_raw = (
            value.get("finalPrice")
            or value.get("price")
            or value.get("sellingPrice")
            or _deep_pick_scalar(value, {"finalPrice", "price", "sellingPrice", "discountedPrice", "offerPrice"})
        )
        if not title or not url_path:
            return None

        product_url = (
            url_path if str(url_path).startswith("http") else f"{BASE_URL}{url_path}"
        )
        current = _parse_price(str(price_raw)) if price_raw else None
        original = _parse_price(
            str(
                value.get("mrp")
                or value.get("originalPrice")
                or _deep_pick_scalar(value, {"mrp", "originalPrice", "strikePrice", "maxPrice"})
                or ""
            )
        )
        disc = None
        if current and original and original > current:
            disc = round((1 - current / original) * 100)

        rating_raw = (
            value.get("rating")
            or value.get("overallRating")
            or value.get("averageRating")
            or _deep_pick_scalar(value, {"rating", "overallRating", "averageRating", "avgRating", "ratingValue"})
        )
        rating_count_raw = (
            value.get("ratingCount")
            or value.get("totalRatings")
            or _deep_pick_scalar(value, {"ratingCount", "ratingsCount", "totalRatings", "reviewCount", "ratingTotalCount"})
        )
        image_url = (
            value.get("image")
            or value.get("imageUrl")
            or _deep_pick_scalar(value, {"image", "imageUrl", "imageURL", "thumbnail", "thumbUrl"})
        )
        brand = (
            value.get("brand")
            or value.get("brandName")
            or _deep_pick_scalar(value, {"brand", "brandName", "sellerBrand", "manufacturer"})
        )
        category = (
            value.get("category")
            or value.get("productType")
            or _deep_pick_scalar(value, {"category", "productType", "vertical", "superCategory"})
        )

        return RawProduct(
            title=str(title).strip(),
            source="flipkart",
            product_url=product_url,
            brand=str(brand).strip() if brand else None,
            price_current=current,
            price_original=original,
            discount_percent=disc,
            image_url=str(image_url).strip() if image_url else None,
            rating=_parse_rating(str(rating_raw or "")),
            rating_count=_parse_count(str(rating_count_raw or "")),
            category=str(category).strip() if category else None,
        )

    def _parse_json_ld(self, data, seen_urls: set) -> list[RawProduct]:
        items = data if isinstance(data, list) else [data]
        results = []
        for item in items:
            if item.get("@type") not in ("Product", "ItemList"):
                continue
            offer = item.get("offers") or {}
            if isinstance(offer, list):
                offer = offer[0] if offer else {}
            url = item.get("url") or offer.get("url") or ""
            if not url:
                continue
            product_url = url if url.startswith("http") else f"{BASE_URL}{url}"
            current = _parse_price(str(offer.get("price") or ""))
            if not current:
                continue
            p = RawProduct(
                title=str(item.get("name") or "").strip(),
                source="flipkart",
                product_url=product_url,
                brand=str(item.get("brand", {}).get("name") or ""),
                price_current=current,
                image_url=(
                    item["image"] if isinstance(item.get("image"), str) else None
                ),
                rating=_parse_rating(
                    str(
                        (item.get("aggregateRating") or {}).get("ratingValue") or ""
                    )
                ),
                rating_count=_parse_int(
                    str(
                        (item.get("aggregateRating") or {}).get("reviewCount") or ""
                    )
                ),
            )
            if p.is_valid() and p.product_url not in seen_urls:
                seen_urls.add(p.product_url)
                results.append(p)
        return results

    def _parse_cards(self, soup: BeautifulSoup, seen_urls: set) -> list[RawProduct]:
        cards = []
        for sel in _CARD_SEL:
            cards = soup.select(sel)
            if len(cards) >= 5:
                break

        results = []
        for card in cards:
            try:
                p = self._extract_from_card(card)
                if p and p.is_valid() and p.product_url not in seen_urls:
                    seen_urls.add(p.product_url)
                    results.append(p)
            except Exception:
                continue
        return results

    def _extract_from_card(self, card: Tag) -> Optional[RawProduct]:
        title = _first_text(card, _TITLE_SEL)
        if not title:
            return None

        link = card.find("a", href=True)
        if not link:
            return None
        href = str(link["href"])
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        price_text = _first_text(card, _PRICE_SEL)
        orig_text = _first_text(card, _ORIG_PRICE_SEL)
        rating_text = _first_text(card, _RATING_SEL)
        rating_count_text = _first_text(card, _RATING_COUNT_SEL)

        img_url = None
        for sel in _IMG_SEL:
            tag = card.select_one(sel)
            if tag:
                src = tag.get("src") or tag.get("data-src") or ""
                if str(src).startswith("http"):
                    img_url = str(src)
                    break

        brand = _first_text(card, _BRAND_SEL)
        current = _parse_price(price_text or "")
        original = _parse_price(orig_text or "")
        disc = None
        if current and original and original > current:
            disc = round((1 - current / original) * 100)

        # Stock availability
        in_stock = True
        stock_count = None
        delivery_info = None
        card_text = card.get_text(" ", strip=True)
        if re.search(r"sold\s*out|out\s*of\s*stock|currently\s*unavailable", card_text, re.I):
            in_stock = False
        m = re.search(r"only\s+(\d+)\s+left", card_text, re.I)
        if m:
            stock_count = int(m.group(1))
        d = re.search(r"((?:free\s+)?delivery\s+by\s+[A-Za-z,\s\d]+)", card_text, re.I)
        if d:
            delivery_info = d.group(1).strip()

        return RawProduct(
            title=title.strip(),
            source="flipkart",
            product_url=product_url,
            brand=brand,
            price_current=current,
            price_original=original,
            discount_percent=disc,
            image_url=img_url,
            rating=_parse_rating(rating_text or ""),
            rating_count=_parse_count(rating_count_text or ""),
            in_stock=in_stock,
            stock_count=stock_count,
            delivery_info=delivery_info,
        )


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _first_text(card: Tag, selectors: list[str]) -> Optional[str]:
    for sel in selectors:
        el = card.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    return None


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    # Extract the first numeric token to avoid cases like "Rs. 899" -> ".899".
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    cleaned = match.group(0)
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def _parse_rating(text: str) -> Optional[float]:
    if not text:
        return None
    match = re.search(r"(\d+\.?\d*)", text)
    if match:
        val = float(match.group(1))
        return val if 0 < val <= 5 else None
    return None


def _parse_int(text: str) -> Optional[int]:
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text)
    try:
        return int(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_count(text: str) -> Optional[int]:
    if not text:
        return None
    t = str(text).replace(",", "").strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([km]?)", t)
    if not match:
        return None
    num = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        num *= 1_000
    elif suffix == "m":
        num *= 1_000_000
    try:
        count = int(round(num))
        return count if count > 0 else None
    except ValueError:
        return None


def _deep_pick_scalar(obj, keys: set[str], depth: int = 0):
    if depth > 8:
        return None
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in keys:
                if isinstance(val, (str, int, float)):
                    return val
                if isinstance(val, dict):
                    nested = _deep_pick_scalar(
                        val,
                        {
                            "value",
                            "name",
                            "rating",
                            "ratingValue",
                            "average",
                            "averageRating",
                            "count",
                            "ratingCount",
                            "totalRatings",
                            "reviewCount",
                            "url",
                            "src",
                            "imageUrl",
                        },
                        depth + 1,
                    )
                    if nested is not None:
                        return nested
            nested = _deep_pick_scalar(val, keys, depth + 1)
            if nested is not None:
                return nested
    elif isinstance(obj, list):
        for item in obj:
            nested = _deep_pick_scalar(item, keys, depth + 1)
            if nested is not None:
                return nested
    return None


def _apply_gender_hint(products: list[RawProduct], hint: Optional[str]) -> list[RawProduct]:
    """Set target_gender from query hint on products that have no gender yet."""
    if not hint:
        return products
    for p in products:
        if not p.target_gender:
            p.target_gender = hint
    return products


async def _safe_unroute(page: Page, pattern: str):
    try:
        await page.unroute(pattern)
    except Exception:
        pass

