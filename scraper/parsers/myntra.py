import asyncio
import re
from typing import Callable, Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page

from .base import BaseParser, RawProduct
from scraper import log


BASE_URL = "https://www.myntra.com"

# (path, gender_hint) - scoped to required Men/Women ethnic categories only
SEARCH_PATHS: list[tuple[str, str]] = [
    # Interleave Men/Women paths so partial outputs are not overwhelmingly men-first.
    ("men-kurtas", "Men"),
    ("kurtas", "Women"),
    ("men-kurta-sets", "Men"),
    ("salwar-suits", "Women"),
    ("men-sherwanis", "Men"),
    ("kurtis", "Women"),
    ("men-nehru-jackets", "Men"),
    ("tunics", "Women"),
    ("men-dhotis", "Men"),
    ("sarees", "Women"),
    ("men-ethnic-wear", "Men"),
    ("ethnic-wear", "Women"),
    ("lehenga-cholis", "Women"),
]

DEFAULT_PATH_PAGE_LIMIT = 1
UNLIMITED_PATH_PAGE_LIMIT = 8
LOW_YIELD_THRESHOLD = 4
MAX_CONSECUTIVE_LOW_YIELD_PAGES = 2


class MyntraParser(BaseParser):
    def __init__(self):
        super().__init__(delay_range=(3.0, 6.0))

    async def scrape(
        self,
        max_products: int = 100,
        on_progress: Callable[[list[RawProduct]], None] | None = None,
    ) -> list[RawProduct]:
        products: list[RawProduct] = []
        seen_urls: set[str] = set()
        limit_enabled = max_products > 0
        page_limit = DEFAULT_PATH_PAGE_LIMIT if limit_enabled else UNLIMITED_PATH_PAGE_LIMIT

        async with async_playwright() as pw:
            # Myntra frequently fails with HTTP2 protocol errors on Chromium in
            # headless automation; Firefox is more reliable for navigation.
            browser = await pw.firefox.launch(headless=True)
            context = await browser.new_context(
                user_agent=self._random_ua(),
                viewport={"width": 1920, "height": 1080},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            page = await context.new_page()

            path_states = {
                path: {"gender_hint": gender_hint, "active": True, "low_yield_streak": 0}
                for path, gender_hint in SEARCH_PATHS
            }

            for page_num in range(1, page_limit + 1):
                if limit_enabled and len(products) >= max_products:
                    break

                active_paths = [path for path, state in path_states.items() if state["active"]]
                if not active_paths:
                    break

                for path in active_paths:
                    if limit_enabled and len(products) >= max_products:
                        break

                    state = path_states[path]
                    gender_hint = state["gender_hint"]
                    try:
                        batch = await asyncio.wait_for(
                            self._scrape_path(page, path, page_num, seen_urls, gender_hint),
                            timeout=150,
                        )
                        products.extend(batch)
                        log.scrape_batch("Myntra", path, page_num, len(batch), len(products))
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
                                    "Myntra",
                                    f"'{path}' low yield for {state['low_yield_streak']} pages - moving on",
                                )
                                state["active"] = False
                        else:
                            state["low_yield_streak"] = 0
                    except asyncio.TimeoutError:
                        log.error("Myntra", f"'{path}' p{page_num} timed out after 150s - skipping")
                        state["active"] = False
                    except Exception as exc:
                        log.error("Myntra", f"'{path}' p{page_num} failed: {exc}")
                        state["active"] = False

                    if state["active"]:
                        await self._random_delay(1.5)

            await browser.close()

        return products[:max_products] if limit_enabled else products

    async def _scrape_path(
        self,
        page: Page,
        path: str,
        page_num: int,
        seen_urls: set,
        gender_hint: Optional[str] = None,
    ) -> list[RawProduct]:
        captured: list[dict] = []

        async def _on_route(route, _request):
            try:
                response = await route.fetch()
                if response.status == 200:
                    try:
                        data = await response.json()
                        captured.append(data)
                    except Exception:
                        pass
                await route.fulfill(response=response)
            except Exception:
                try:
                    await route.continue_()
                except Exception:
                    pass

        # Intercept Myntra's internal search API
        await page.route("**gateway**search**", _on_route)
        await page.route("**search**results**", _on_route)

        page_url = f"{BASE_URL}/{path}" if page_num <= 1 else f"{BASE_URL}/{path}?p={page_num}"

        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:
            log.error("Myntra", f"Navigation failed for '{path}' p{page_num}: {exc}")
            await _safe_unroute(page, "**gateway**search**")
            await _safe_unroute(page, "**search**results**")
            return []

        await asyncio.sleep(4)

        # Scroll repeatedly to trigger lazy-load API batches (Myntra loads 30/page)
        for _ in range(6):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 3)")
            await asyncio.sleep(2)

        await _safe_unroute(page, "**gateway**search**")
        await _safe_unroute(page, "**search**results**")

        # Use API-intercepted data first
        if captured:
            products = []
            for data in captured:
                products.extend(self._parse_api_response(data, seen_urls))
            if products:
                return _apply_gender_hint(products, gender_hint)

        # Fallback: parse rendered HTML
        html = await page.content()
        return _apply_gender_hint(self._parse_html(html, seen_urls), gender_hint)

    # ------------------------------------------------------------------ #
    # API response parsing (most reliable path)                            #
    # ------------------------------------------------------------------ #

    def _parse_api_response(self, data: dict, seen_urls: set) -> list[RawProduct]:
        product_list = (
            data.get("searchData", {}).get("results", {}).get("products")
            or data.get("results", {}).get("products")
            or data.get("products")
            or []
        )
        results = []
        for item in product_list:
            try:
                p = self._map_api_item(item)
                if p and p.is_valid() and p.product_url not in seen_urls:
                    seen_urls.add(p.product_url)
                    results.append(p)
            except Exception:
                continue
        return results

    def _map_api_item(self, item: dict) -> Optional[RawProduct]:
        product_id = (
            item.get("productId")
            or item.get("id")
            or _deep_pick_scalar(item, {"productId", "id"})
        )
        name = (
            item.get("productName")
            or item.get("name")
            or _deep_pick_scalar(item, {"productName", "name", "title", "displayName"})
        )
        if not name or not product_id:
            return None

        landing = (
            item.get("landingPageUrl")
            or _deep_pick_scalar(item, {"landingPageUrl", "pdpUrl", "url", "href"})
            or str(product_id)
        )
        product_url = (
            landing if landing.startswith("http") else f"{BASE_URL}/{landing.lstrip('/')}"
        )

        price_info = item.get("price") or {}
        if isinstance(price_info, dict):
            selling_price = price_info.get("discounted") or price_info.get("current")
            mrp = price_info.get("mrp")
        else:
            selling_price = price_info
            mrp = item.get("mrp")

        image_url = _extract_image_url(item)

        rating_info = item.get("rating") or item.get("ratings") or {}
        if isinstance(rating_info, dict):
            rating_val = (
                rating_info.get("averageRating")
                or rating_info.get("rating")
                or rating_info.get("value")
                or rating_info.get("score")
            )
            rating_count = (
                rating_info.get("ratingCount")
                or rating_info.get("count")
                or rating_info.get("totalRatings")
                or rating_info.get("reviewCount")
            )
        else:
            rating_val = rating_info
            rating_count = item.get("ratingCount") or item.get("reviewCount")

        rating_val = rating_val or _deep_pick_scalar(
            item,
            {"averageRating", "rating", "avgRating", "ratingValue", "score"},
        )
        rating_count = rating_count or _deep_pick_scalar(
            item,
            {"ratingCount", "ratingsCount", "totalRatings", "reviewCount", "count"},
        )

        brand_info = item.get("brand") or {}
        brand = (
            brand_info.get("name") if isinstance(brand_info, dict) else brand_info
        )
        if not brand:
            brand = _deep_pick_scalar(item, {"brand", "brandName", "sellerBrand"})

        colours = item.get("colours") or []
        color = colours[0] if colours else None

        current = _parse_price(str(selling_price)) if selling_price else None
        original = _parse_price(str(mrp)) if mrp else None
        disc = None
        if current and original and original > current:
            disc = round((1 - current / original) * 100)

        # Stock availability
        in_stock, stock_count = _parse_availability(item)

        return RawProduct(
            title=str(name).strip(),
            source="myntra",
            product_url=product_url,
            brand=str(brand).strip() if brand else None,
            price_current=current,
            price_original=original,
            discount_percent=disc,
            image_url=str(image_url) if image_url else None,
            color=str(color).strip() if color else None,
            rating=_parse_rating(str(rating_val or "")),
            rating_count=_parse_count(str(rating_count or "")),
            category=item.get("primaryType") or item.get("category"),
            in_stock=in_stock,
            stock_count=stock_count,
        )

    # ------------------------------------------------------------------ #
    # HTML fallback parsing                                                #
    # ------------------------------------------------------------------ #

    def _parse_html(self, html: str, seen_urls: set) -> list[RawProduct]:
        soup = BeautifulSoup(html, "html.parser")
        cards = (
            soup.select(".product-base")
            or soup.select("li.product-base")
            or soup.select("[class*='product-base']")
        )
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

    def _extract_from_card(self, card) -> Optional[RawProduct]:
        link = card.find("a", href=True)
        if not link:
            return None
        href = str(link["href"])
        product_url = (
            href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"
        )

        title_tag = card.select_one(".product-product") or card.select_one(
            "[class*='product-product']"
        )
        brand_tag = card.select_one(".product-brand") or card.select_one(
            "[class*='product-brand']"
        )
        price_tag = card.select_one(
            ".product-discountedPrice"
        ) or card.select_one("[class*='discountedPrice']")
        orig_tag = card.select_one(".product-strike") or card.select_one(
            "[class*='product-strike']"
        )
        disc_tag = card.select_one(
            ".product-discountPercentage"
        ) or card.select_one("[class*='discountPercentage']")
        rating_tag = (
            card.select_one(".product-ratingsContainer span")
            or card.select_one("[class*='ratingsContainer'] span")
        )
        rating_count_tag = (
            card.select_one(".product-ratingsCount")
            or card.select_one("[class*='ratingsCount']")
        )

        img = card.find("img")
        image_url = None
        if img:
            image_url = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
                or _extract_first_src_from_srcset(img.get("srcset") or img.get("data-srcset"))
            )

        title = title_tag.get_text(strip=True) if title_tag else None
        if not title:
            return None

        price_current = _parse_price(price_tag.get_text() if price_tag else "")
        price_original = _parse_price(orig_tag.get_text() if orig_tag else "")
        disc = _parse_int(disc_tag.get_text() if disc_tag else "")

        return RawProduct(
            title=title,
            source="myntra",
            product_url=product_url,
            brand=brand_tag.get_text(strip=True) if brand_tag else None,
            price_current=price_current,
            price_original=price_original,
            discount_percent=disc,
            image_url=_normalize_image_url(image_url),
            rating=_parse_rating(rating_tag.get_text() if rating_tag else ""),
            rating_count=_parse_count(rating_count_tag.get_text() if rating_count_tag else ""),
        )


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    # Use search instead of sub to avoid "Rs.86" -> ".86" -> 0.86
    match = re.search(r"\d+(?:\.\d+)?", str(text).replace(",", ""))
    if not match:
        return None
    try:
        val = float(match.group(0))
        return val if val > 0 else None
    except ValueError:
        return None


def _parse_rating(text: str) -> Optional[float]:
    if not text:
        return None
    match = re.search(r"(\d+\.?\d*)", str(text))
    if not match:
        return None
    val = float(match.group(1))
    return val if 0 < val <= 5 else None


def _parse_int(text: str) -> Optional[int]:
    if not text:
        return None
    match = re.search(r"(\d+)", str(text).replace(",", ""))
    return int(match.group(1)) if match else None


def _parse_count(text: str) -> Optional[int]:
    if not text:
        return None
    t = str(text).replace(",", "").replace("(", "").replace(")", "").strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([km]?)", t)
    if not match:
        return _parse_int(t)
    num = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        num *= 1_000
    elif suffix == "m":
        num *= 1_000_000
    return int(round(num)) if num > 0 else None


def _extract_first_src_from_srcset(srcset: Optional[str]) -> Optional[str]:
    if not srcset:
        return None
    first = str(srcset).split(",")[0].strip()
    if not first:
        return None
    return first.split(" ")[0].strip()


def _normalize_image_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    val = str(url).strip()
    if not val:
        return None
    if val.startswith("//"):
        return f"https:{val}"
    if val.startswith("/"):
        return f"{BASE_URL}{val}"
    return val


def _extract_image_url(item: dict) -> Optional[str]:
    candidate = _find_first_image_value(
        item,
        {
            "searchImage",
            "searchImageUrl",
            "defaultImage",
            "defaultImageURL",
            "image",
            "imageURL",
            "imageUrl",
            "imageSrc",
            "thumbnail",
            "secureSrc",
            "src",
            "url",
            "webpSrc",
        },
    )
    return _normalize_image_url(candidate)


async def _safe_unroute(page: Page, pattern: str):
    try:
        await page.unroute(pattern)
    except Exception:
        # Firefox intermittently aborts pending interceptions during unroute.
        pass


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


def _find_first_image_value(obj, keys: set[str], depth: int = 0):
    if depth > 8:
        return None

    if isinstance(obj, str):
        return obj if obj.startswith(("http://", "https://", "//", "/")) else None

    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in keys:
                nested = _find_first_image_value(val, keys, depth + 1)
                if nested:
                    return nested
            nested = _find_first_image_value(val, keys, depth + 1)
            if nested:
                return nested
    elif isinstance(obj, list):
        for item in obj:
            nested = _find_first_image_value(item, keys, depth + 1)
            if nested:
                return nested

    return None


def _parse_availability(item: dict) -> tuple[bool, Optional[int]]:
    """Return (in_stock, stock_count) from a Myntra API product item."""
    # Direct sold-out flags
    if item.get("isSoldOut") or item.get("soldOut"):
        return False, 0

    availability = item.get("availability") or item.get("availabilityStatus") or ""
    if str(availability).lower() in ("soldout", "sold_out", "out_of_stock", "unavailable"):
        return False, 0

    # Inventory count
    inventory = item.get("inventoryInfo") or item.get("inventory") or {}
    stock_count: Optional[int] = None
    if isinstance(inventory, dict):
        raw = inventory.get("totalCount") or inventory.get("qty") or inventory.get("count")
        if raw is not None:
            try:
                stock_count = int(raw)
                if stock_count == 0:
                    return False, 0
            except (ValueError, TypeError):
                pass
    elif isinstance(inventory, int):
        stock_count = inventory
        if stock_count == 0:
            return False, 0

    return True, stock_count


def _apply_gender_hint(products: list[RawProduct], hint: Optional[str]) -> list[RawProduct]:
    """Set target_gender from path hint on products that have no gender yet."""
    if not hint:
        return products
    for p in products:
        if not p.target_gender:
            p.target_gender = hint
    return products

