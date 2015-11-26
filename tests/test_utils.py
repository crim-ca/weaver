from nose.tools import assert_equals, assert_raises

from twitcher import utils

def test_baseurl():
    assert_equals(utils.baseurl('http://localhost:8094/wps'), 'http://localhost:8094/wps')
    assert_equals(utils.baseurl('http://localhost:8094/wps?service=wps&request=getcapabilities'), 'http://localhost:8094/wps')
    assert_equals(utils.baseurl('https://localhost:8094/wps?service=wps&request=getcapabilities'), 'https://localhost:8094/wps')
    with assert_raises(ValueError) as e:
        utils.baseurl('ftp://localhost:8094/wps')


def test_path_elements():
    assert_equals(utils.path_elements('/ows/proxy/lovely_bird'), ['ows', 'proxy', 'lovely_bird'])
    assert_equals(utils.path_elements('/ows/proxy/lovely_bird/'), ['ows', 'proxy', 'lovely_bird'])
    assert_equals(utils.path_elements('/ows/proxy/lovely_bird/ '), ['ows', 'proxy', 'lovely_bird'])


def test_lxml_strip_ns():
    import lxml.etree
    wpsxml = """<wps100:Execute xmlns:wps100="http://www.opengis.net/wps/1.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" service="WPS" version="1.0.0" xsi:schemaLocation="http://www.opengis.net/wps/1.0.0 http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd"/>"""

    doc = lxml.etree.fromstring(wpsxml)
    assert_equals(doc.tag, '{http://www.opengis.net/wps/1.0.0}Execute')
    utils.lxml_strip_ns(doc)
    assert_equals(doc.tag, 'Execute')
