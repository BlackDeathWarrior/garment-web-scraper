import asyncio
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Callable, Optional
import uuid


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]


@dataclass
class RawProduct:
    title: str
    source: str
    product_url: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    brand: Optional[str] = None
    price_current: Optional[float] = None
    price_original: Optional[float] = None
    discount_percent: Optional[int] = None
    image_url: Optional[str] = None
    color: Optional[str] = None
    fabric: Optional[str] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    review_summary: Optional[str] = None
    category: Optional[str] = None
    target_gender: Optional[str] = None
    in_stock: bool = True
    stock_count: Optional[int] = None
    delivery_info: Optional[str] = None
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def is_valid(self) -> bool:
        return bool(self.title and self.product_url and self.price_current is not None)

    def to_dict(self) -> dict:
        return asdict(self)


class BaseParser(ABC):
    def __init__(self, delay_range: tuple = (2.0, 5.0)):
        self.delay_range = delay_range

    def _random_ua(self) -> str:
        return random.choice(USER_AGENTS)

    async def _random_delay(self, multiplier: float = 1.0):
        delay = random.uniform(*self.delay_range) * multiplier
        await asyncio.sleep(delay)

    @abstractmethod
    async def scrape(
        self,
        max_products: int,
        on_progress: Callable[[list[RawProduct]], None] | None = None,
    ) -> list[RawProduct]:
        """Scrape products and return list of RawProduct objects."""
