from decimal import Decimal

import mock
import pytest

from weaver.quotation.estimation import CURRENCY_CONVERTERS


class MockResponse(object):
    status_code = 200

    def __init__(self, text):
        self.text = text


@pytest.mark.parametrize(
    ["converter", "expect_host"],
    [
        ("openexchangerates", "openexchangerates.org"),
        ("currencylayer", "api.currencylayer.com"),
        ("exchangeratesapi", "api.exchangeratesapi.io"),
        ("fixer", "data.fixer.io"),
        ("allratestoday", "allratestoday.com"),
    ]
)
def test_currency_converter_url_and_parse(converter, expect_host):
    cvt = CURRENCY_CONVERTERS[converter]
    body = '{"success": true, "result": 8.9341553, "response": 8.9341553}'
    with mock.patch("weaver.quotation.estimation.request_extra", return_value=MockResponse(body)) as mock_req:
        result = cvt.convert(Decimal("10"), "usd", "eur")
    url = mock_req.call_args[0][1]
    assert expect_host in url
    assert "USD" in url and "EUR" in url and "10" in url
    assert "{" not in url
    assert result == Decimal("8.9341553")
