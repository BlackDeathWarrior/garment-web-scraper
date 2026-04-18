from scraper.collect import (
    _balance_gender_sequence,
    _build_parsers,
    _dedup_key,
    _enforce_scope,
    _recalc_discounts,
)


def test_enforce_scope_keeps_and_normalizes_men_women_rows():
    products = [
        {'title': 'Women Printed Saree', 'source': 'myntra', 'target_gender': 'women'},
        {'title': 'Manyavar Sherwani', 'source': 'flipkart', 'target_gender': None},
    ]

    result = _enforce_scope(products)

    assert len(result) == 2
    assert result[0]['target_gender'] == 'Women'
    assert result[1]['target_gender'] == 'Men'


def test_enforce_scope_drops_children_unisex_and_unknown_rows():
    products = [
        {'title': 'Kids Girls Lehenga', 'source': 'myntra', 'target_gender': 'Girls'},
        {'title': 'Unisex Ethnic Wear', 'source': 'amazon', 'target_gender': 'Unisex'},
        {'title': 'Generic Ethnic Kurta', 'source': 'flipkart', 'target_gender': None},
    ]

    result = _enforce_scope(products)

    assert result == []


def test_recalc_discounts_drops_impossible_percentage_pairs():
    products = [
        {
            'title': 'Sample Kurta',
            'source': 'flipkart',
            'price_current': 100.0,
            'price_original': 50000.0,
            'discount_percent': 4740,
        }
    ]

    result = _recalc_discounts(products)

    assert result[0]['discount_percent'] is None
    assert result[0]['price_original'] is None


def test_collect_dedup_key_prefers_normalized_product_url():
    item = {
        'title': 'Same Listing Name',
        'source': 'amazon',
        'product_url': 'https://www.amazon.in/dp/B0TEST1234?ref_=abc',
    }

    assert _dedup_key(item) == 'amazon::https://www.amazon.in/dp/B0TEST1234'


def test_build_parsers_preserves_requested_source_order():
    parsers = _build_parsers(['amazon', 'myntra', 'flipkart'])
    names = [parser.__class__.__name__ for parser in parsers]
    assert names == ['AmazonParser', 'MyntraParser', 'FlipkartParser']


def test_balance_gender_sequence_interleaves_when_one_side_dominates():
    products = [
        {'title': 'Men 1', 'target_gender': 'Men'},
        {'title': 'Men 2', 'target_gender': 'Men'},
        {'title': 'Men 3', 'target_gender': 'Men'},
        {'title': 'Men 4', 'target_gender': 'Men'},
        {'title': 'Women 1', 'target_gender': 'Women'},
        {'title': 'Women 2', 'target_gender': 'Women'},
    ]

    result = _balance_gender_sequence(products)

    assert [item['title'] for item in result[:6]] == [
        'Men 1',
        'Women 1',
        'Men 2',
        'Women 2',
        'Men 3',
        'Men 4',
    ]
