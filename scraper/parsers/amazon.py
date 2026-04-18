import asyncio
import re
from typing import Callable, Optional

from bs4 import BeautifulSoup, Tag
from playwright.async_api import async_playwright, Page

from .base import BaseParser, RawProduct
from scraper import log


BASE_URL = "https://www.amazon.in"

# Interleave men and women searches so women's inventory is not starved when
# long-running sessions hit Amazon throttling or browser crashes.
SEARCH_QUERIES: list[tuple[str, str]] = [
    ("men kurta ethnic indian", "Men"),
    ("women kurta ethnic suit indian", "Women"),
    ("men kurta set ethnic pyjama", "Men"),
    ("salwar suit women ethnic", "Women"),
    ("men sherwani wedding ethnic", "Men"),
    ("women kurti tunic ethnic top", "Women"),
    ("men nehru jacket ethnic", "Men"),
    ("saree women indian traditional", "Women"),
    ("men dhoti ethnic traditional", "Men"),
    ("women ethnic wear indian", "Women"),
    ("men ethnic set kurta pyjama", "Men"),
    ("lehenga choli women ethnic", "Women"),
]

DEFAULT_QUERY_PAGE_LIMIT = 2
UNLIMITED_QUERY_PAGE_LIMIT = 10
LOW_YIELD_THRESHOLD = 4
MAX_CONSECUTIVE_LOW_YIELD_PAGES = 2


class AmazonParser(BaseParser):
    def __init__(self):
        super().__init__(delay_range=(5.0, 12.0))

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
            for query, gender_hint in SEARCH_QUERIES:
                if limit_enabled and len(products) >= max_products:
                    break
                batch, should_continue = await self._scrape_query_range(
                    pw,
                    query,
                    gender_hint,
                    start_page=1,
                    end_page=1,
                    seen_urls=seen_urls,
                    products=products,
                    on_progress=on_progress,
                )
                if not should_continue:
                    continue
                await self._random_delay()

            if page_limit <= 1:
                return products[:max_products] if limit_enabled else products

            for query, gender_hint in SEARCH_QUERIES:
                if limit_enabled and len(products) >= max_products:
                    break
                await self._scrape_query_range(
                    pw,
                    query,
                    gender_hint,
                    start_page=2,
                    end_page=page_limit,
                    seen_urls=seen_urls,
                    products=products,
                    on_progress=on_progress,
                )
                await self._random_delay()

        return products[:max_products] if limit_enabled else products

    async def _scrape_query_range(
        self,
        pw,
        query: str,
        gender_hint: Optional[str],
        start_page: int,
        end_page: int,
        seen_urls: set,
        products: list[RawProduct],
        on_progress: Callable[[list[RawProduct]], None] | None = None,
    ) -> tuple[list[RawProduct], bool]:
        low_yield_streak = 0
        collected: list[RawProduct] = []
        browser = None
        context = None

        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                ],
            )
            context = await browser.new_context(
                user_agent=self._random_ua(),
                viewport={"width": 1366, "height": 768},
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                extra_http_headers={
                    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                },
            )
            await context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en', 'hi'] });
                window.chrome = { runtime: {} };
                """
            )
            page = await context.new_page()

            try:
                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(3)
            except Exception:
                pass

            for pg in range(start_page, end_page + 1):
                try:
                    batch = await self._scrape_query(page, query, pg, seen_urls, gender_hint)
                    collected.extend(batch)
                    products.extend(batch)
                    log.scrape_batch("Amazon", query, pg, len(batch), len(products))
                    if on_progress and batch:
                        try:
                            on_progress(products)
                        except Exception:
                            pass
                    if not batch:
                        return collected, False
                    if len(batch) < LOW_YIELD_THRESHOLD:
                        low_yield_streak += 1
                        if low_yield_streak >= MAX_CONSECUTIVE_LOW_YIELD_PAGES:
                            log.warn(
                                "Amazon",
                                f"'{query}' low yield for {low_yield_streak} pages - moving on",
                            )
                            return collected, False
                    else:
                        low_yield_streak = 0
                except Exception as exc:
                    log.error("Amazon", f"'{query}' p{pg} failed: {exc}")
                    return collected, False

                if pg < end_page:
                    await self._random_delay()
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

        return collected, True

    async def _scrape_query(
        self,
        page: Page,
        query: str,
        page_num: int,
        seen_urls: set,
        gender_hint: Optional[str] = None,
    ) -> list[RawProduct]:
        encoded = query.replace(" ", "+")
        url = f"{BASE_URL}/s?k={encoded}&page={page_num}"

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception:
            try:
                await page.goto(url, wait_until="commit", timeout=30_000)
            except Exception as exc:
                raise exc

        await asyncio.sleep(3)

        # Bail out early if CAPTCHA is served.
        body_text = await page.evaluate("document.body.innerText")
        if "captcha" in body_text.lower() or "Enter the characters" in body_text:
            log.warn("Amazon", f"CAPTCHA detected for '{query}' - skipping, waiting 15s")
            await asyncio.sleep(15)
            return []

        # Scroll to trigger lazy-loaded images.
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            await asyncio.sleep(1.5)

        html = await page.content()
        return self._parse_html(html, seen_urls, gender_hint)

    def _parse_html(
        self, html: str, seen_urls: set, gender_hint: Optional[str] = None
    ) -> list[RawProduct]:
        soup = BeautifulSoup(html, "html.parser")

        cards = soup.select('[data-component-type="s-search-result"]')
        if not cards:
            cards = soup.select(".s-result-item[data-asin]")

        results = []
        for card in cards:
            try:
                p = self._extract_from_card(card, gender_hint)
                if (
                    p
                    and p.is_valid()
                    and _matches_gender_hint(p.title, gender_hint)
                    and p.product_url not in seen_urls
                ):
                    seen_urls.add(p.product_url)
                    results.append(p)
            except Exception:
                continue
        return results

    def _extract_from_card(
        self, card: Tag, gender_hint: Optional[str] = None
    ) -> Optional[RawProduct]:
        asin = str(card.get("data-asin", "")).strip()
        if not asin:
            return None

        title_tag = (
            card.select_one("h2 a span") 
            or card.select_one(".a-text-normal")
            or card.select_one("span.a-size-base-plus.a-color-base.a-text-normal")
        )
        title = title_tag.get_text(strip=True) if title_tag else None
        if not title:
            return None

        link = card.select_one("h2 a") or card.select_one("a.a-link-normal[href]")
        if not link:
            return None
        href = str(link.get("href", ""))
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        # Normalize to clean /dp/ URL to deduplicate tracking variants.
        dp_match = re.search(r"(/dp/[A-Z0-9]+)", product_url)
        if dp_match:
            product_url = f"{BASE_URL}{dp_match.group(1)}"

        current = None
        price_whole = card.select_one(".a-price-whole")
        if price_whole:
            price_str = price_whole.get_text(strip=True).replace(",", "").rstrip(".")
            frac = card.select_one(".a-price-fraction")
            if frac:
                price_str += "." + frac.get_text(strip=True)
            current = _parse_price(price_str)
        if not current:
            off = card.select_one(".a-price .a-offscreen")
            current = _parse_price(off.get_text() if off else "")

        orig_tag = (
            card.select_one(".a-text-price .a-offscreen")
            or card.select_one(".basisPrice .a-offscreen")
        )
        original = _parse_price(orig_tag.get_text() if orig_tag else "")

        disc = None
        if current and original and original > current:
            disc = round((1 - current / original) * 100)

        img = (
            card.select_one("img.s-image") 
            or card.select_one("img[src*='media-amazon']")
            or card.select_one(".s-image-fixed-height img")
            or card.select_one("img")
        )
        image_url = img.get("src") or img.get("data-src") if img else None

        rating_tag = (
            card.select_one("i.a-icon-star-small span.a-icon-alt")
            or card.select_one(".a-icon-star span.a-icon-alt")
            or card.select_one(".a-icon-alt")
        )
        rating_text = rating_tag.get_text(strip=True) if rating_tag else ""

        count_tag = (
            card.select_one("span.a-size-base.s-underline-text")
            or card.select_one("a.a-link-normal span.a-size-base")
            or card.select_one("span[aria-label*='ratings']")
            or card.select_one(".a-size-base.s-light-weight-text")
            or card.select_one(".a-link-normal .a-size-base")
        )
        rating_count_text = count_tag.get_text(strip=True) if count_tag else ""

        brand_tag = (
            card.select_one(".a-size-base-plus")
            or card.select_one(".s-line-clamp-1 .a-size-base-plus")
            or card.select_one("h5.s-line-clamp-1 span")
        )
        brand = brand_tag.get_text(strip=True) if brand_tag else None
        if brand and (len(brand) > 60 or re.match(r"^(rs\.?|inr|\$)", brand, re.I)):
            brand = None

        return RawProduct(
            title=title,
            source="amazon",
            product_url=product_url,
            brand=brand,
            price_current=current,
            price_original=original,
            discount_percent=disc,
            image_url=str(image_url) if image_url else None,
            rating=_parse_rating(rating_text),
            rating_count=_parse_count(rating_count_text),
            target_gender=gender_hint,
        )


# ------------------------------------------------------------------ #
# Helpers                                                            #
# ------------------------------------------------------------------ #


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
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


def _parse_count(text: str) -> Optional[int]:
    if not text:
        return None
    t = str(text).replace(",", "").replace("(", "").replace(")", "").strip().lower()
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


def _matches_gender_hint(title: str, gender_hint: Optional[str]) -> bool:
    if not gender_hint:
        return True

    text = str(title or "").lower()
    men_terms = (
        r"\bmen\b",
        r"\bmen's\b",
        r"\bmens\b",
        r"\bmale\b",
        r"\bsherwani\b",
        r"\bnehru\s+jacket\b",
        r"\bdhoti\b",
    )
    women_terms = (
        r"\bwomen\b",
        r"\bwomen's\b",
        r"\bladies\b",
        r"\bfemale\b",
        r"\bsaree\b",
        r"\blehenga\b",
        r"\bkurti\b",
        r"\bsalwar\b",
        r"\banarkali\b",
    )

    if gender_hint == "Women":
        return not any(re.search(pattern, text) for pattern in men_terms)
    if gender_hint == "Men":
        return not any(re.search(pattern, text) for pattern in women_terms)
    return True
