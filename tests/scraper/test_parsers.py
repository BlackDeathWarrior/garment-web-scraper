import pytest
from scraper.parsers.flipkart import _parse_price, _parse_rating, _parse_int
from scraper.parsers.myntra import _extract_image_url, _parse_price as myntra_parse_price
from scraper.parsers.base import RawProduct


@pytest.mark.parametrize(
    'text,expected',
    [
        ('₹1,299', 1299.0),
        ('Rs. 899', 899.0),
        ('Rs.86', 86.0),
        ('2,499.00', 2499.0),
        ('999', 999.0),
        ('', None),
        ('N/A', None),
        ('0', None),
    ],
)
def test_flipkart_parse_price(text, expected):
    assert _parse_price(text) == expected


@pytest.mark.parametrize(
    'text,expected',
    [
        ('4.2', 4.2),
        ('3.8 out of 5', 3.8),
        ('5', 5.0),
        ('6.0', None),
        ('', None),
        ('Not rated', None),
    ],
)
def test_flipkart_parse_rating(text, expected):
    result = _parse_rating(text)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected, 0.01)


@pytest.mark.parametrize(
    'text,expected',
    [
        ('1,547 ratings', 1547),
        ('892', 892),
        ('', None),
    ],
)
def test_flipkart_parse_int(text, expected):
    assert _parse_int(text) == expected


@pytest.mark.parametrize(
    'text,expected',
    [
        ('₹1,299', 1299.0),
        ('999', 999.0),
        ('', None),
    ],
)
def test_myntra_parse_price(text, expected):
    assert myntra_parse_price(text) == expected


def test_myntra_extract_image_url_from_nested_style_images():
    item = {
        'styleImages': {
            'default': {
                'imageURL': 'https://assets.myntassets.com/default.jpg',
            }
        }
    }
    assert _extract_image_url(item) == 'https://assets.myntassets.com/default.jpg'


def test_myntra_extract_image_url_from_nested_media_list():
    item = {
        'media': [
            {
                'imageInfo': {
                    'secureSrc': '//assets.myntassets.com/media-one.jpg',
                }
            }
        ]
    }
    assert _extract_image_url(item) == 'https://assets.myntassets.com/media-one.jpg'


def test_raw_product_is_valid():
    p = RawProduct(
        title='Kurta',
        source='flipkart',
        product_url='https://flipkart.com/p/1',
        price_current=499.0,
    )
    assert p.is_valid()


def test_raw_product_invalid_no_title():
    p = RawProduct(title='', source='flipkart', product_url='https://x.com', price_current=499.0)
    assert not p.is_valid()


def test_raw_product_invalid_no_url():
    p = RawProduct(title='Kurta', source='flipkart', product_url='', price_current=499.0)
    assert not p.is_valid()


def test_raw_product_invalid_no_price():
    p = RawProduct(title='Kurta', source='flipkart', product_url='https://x.com', price_current=None)
    assert not p.is_valid()
