import sys
from pathlib import Path

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scraper.parsers.base import RawProduct


@pytest.fixture
def sample_raw_products():
    return [
        RawProduct(
            title="W for Woman Cotton Straight Kurta",
            source="flipkart",
            product_url="https://www.flipkart.com/product/1",
            brand="W for Woman",
            price_current=899.0,
            price_original=1799.0,
            discount_percent=50,
            image_url="https://example.com/image1.jpg",
            color="Blue",
            fabric="Cotton",
            rating=4.2,
            rating_count=1547,
            category="Kurta",
            target_gender="Women",
        ),
        RawProduct(
            title="Biba Women's Printed Anarkali",
            source="myntra",
            product_url="https://www.myntra.com/product/2",
            brand="Biba",
            price_current=1299.0,
            price_original=2599.0,
            discount_percent=50,
            image_url="https://example.com/image2.jpg",
            color="Red",
            rating=4.5,
            rating_count=892,
            category="Anarkali",
            target_gender="Women",
        ),
        RawProduct(
            title="",  # invalid: empty title
            source="flipkart",
            product_url="https://www.flipkart.com/product/3",
            price_current=500.0,
        ),
        RawProduct(
            title="Libas Embroidered Kurta",
            source="myntra",
            product_url="",  # invalid: empty URL
            price_current=799.0,
        ),
    ]
