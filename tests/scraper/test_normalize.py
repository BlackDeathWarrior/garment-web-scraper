import pytest
from scraper.normalize import (
    normalize,
    _clean_text,
    _dedup_key,
    _infer_target_gender,
    _normalize_gender,
)
from scraper.parsers.base import RawProduct


def test_normalize_filters_invalid(sample_raw_products):
    result = normalize(sample_raw_products)
    assert len(result) == 2, 'Only 2 of 4 fixtures are valid'


def test_normalize_keeps_distinct_urls_from_same_source():
    products = [
        RawProduct(
            title='Men Test Kurta',
            source='flipkart',
            product_url='https://www.flipkart.com/a',
            price_current=500.0,
        ),
        RawProduct(
            title='Men Test Kurta',
            source='flipkart',
            product_url='https://www.flipkart.com/b',
            price_current=500.0,
        ),
    ]
    result = normalize(products)
    assert len(result) == 2


def test_normalize_deduplicates_same_source_when_urls_match_after_normalization():
    products = [
        RawProduct(
            title='Men Test Kurta',
            source='amazon',
            product_url='https://www.amazon.in/dp/B0TEST1234?ref_=abc',
            price_current=500.0,
        ),
        RawProduct(
            title='Men Test Kurta',
            source='amazon',
            product_url='https://www.amazon.in/dp/B0TEST1234?tag=xyz',
            price_current=500.0,
        ),
    ]
    result = normalize(products)
    assert len(result) == 1


def test_normalize_keeps_same_title_different_sources():
    products = [
        RawProduct(
            title='Women Ethnic Kurta',
            source='flipkart',
            product_url='https://www.flipkart.com/1',
            price_current=500.0,
        ),
        RawProduct(
            title='Women Ethnic Kurta',
            source='myntra',
            product_url='https://www.myntra.com/1',
            price_current=500.0,
        ),
    ]
    result = normalize(products)
    assert len(result) == 2


def test_normalize_output_has_required_keys(sample_raw_products):
    result = normalize(sample_raw_products)
    assert len(result) > 0
    for key in ('id', 'title', 'source', 'price_current', 'product_url', 'scraped_at'):
        assert key in result[0]


def test_normalize_clears_inverted_prices():
    products = [
        RawProduct(
            title='Women Test Saree',
            source='myntra',
            product_url='https://www.myntra.com/1',
            price_current=1000.0,
            price_original=500.0,
            discount_percent=50,
        )
    ]
    result = normalize(products)
    assert result[0]['price_original'] is None
    assert result[0]['discount_percent'] is None


def test_clean_text_collapses_whitespace():
    assert _clean_text('  hello   world  ') == 'hello world'


def test_clean_text_handles_empty():
    assert _clean_text('') == ''
    assert _clean_text(None) == ''


def test_normalize_infers_target_gender_and_category():
    products = [
        RawProduct(
            title='Men Printed Kurta Set',
            source='flipkart',
            product_url='https://www.flipkart.com/1',
            price_current=799.0,
            category=None,
            target_gender=None,
        )
    ]
    result = normalize(products)
    assert result[0]['target_gender'] == 'Men'
    assert result[0]['category'] == 'Kurta Set'


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('women', 'Women'),
        ('MEN', 'Men'),
        ('girls', None),
        ('boys', None),
        ('kids', None),
        ('unisex', None),
        ('', None),
    ],
)
def test_normalize_gender(raw, expected):
    assert _normalize_gender(raw) == expected


def test_infer_target_gender_drops_children_signals():
    gender = _infer_target_gender('Kids Girls Embroidered Kurta')
    assert gender is None


def test_dedup_key_prefers_normalized_product_url():
    product = RawProduct(
        title='Same Listing Name',
        source='amazon',
        product_url='https://www.amazon.in/dp/B0TEST1234?ref_=abc',
        price_current=999.0,
    )
    assert _dedup_key(product) == 'amazon::https://www.amazon.in/dp/B0TEST1234'
