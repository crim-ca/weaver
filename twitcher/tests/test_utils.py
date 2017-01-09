import pytest
from lxml import etree
from twitcher import utils
from twitcher.exceptions import ServiceNotFound
from twitcher.tests.common import WPS_CAPS_EMU_XML, WMS_CAPS_NCWMS2_111_XML, WMS_CAPS_NCWMS2_130_XML


def test_is_url_valid():
    assert utils.is_valid_url("http://somewhere.org") is True
    assert utils.is_valid_url("https://somewhere.org/my/path") is True
    assert utils.is_valid_url("file:///my/path") is True
    assert utils.is_valid_url("/my/path") is False
    assert utils.is_valid_url(None) is False


def test_parse_service_name():
    assert 'emu' == utils.parse_service_name("/ows/proxy/emu")
    assert 'emu' == utils.parse_service_name("/ows/proxy/emu/foo/bar")
    assert 'emu' == utils.parse_service_name("/ows/proxy/emu/")
    with pytest.raises(ServiceNotFound) as e_info:
        assert 'emu' == utils.parse_service_name("/ows/proxy/")
    with pytest.raises(ServiceNotFound) as e_info:
        assert 'emu' == utils.parse_service_name("/ows/nowhere/emu")


def test_baseurl():
    assert utils.baseurl('http://localhost:8094/wps') == 'http://localhost:8094/wps'
    assert utils.baseurl('http://localhost:8094/wps?service=wps&request=getcapabilities') == 'http://localhost:8094/wps'
    assert utils.baseurl('https://localhost:8094/wps?service=wps&request=getcapabilities') ==\
        'https://localhost:8094/wps'
    with pytest.raises(ValueError) as e_info:
        utils.baseurl('ftp://localhost:8094/wps')


def test_path_elements():
    assert utils.path_elements('/ows/proxy/lovely_bird') == ['ows', 'proxy', 'lovely_bird']
    assert utils.path_elements('/ows/proxy/lovely_bird/') == ['ows', 'proxy', 'lovely_bird']
    assert utils.path_elements('/ows/proxy/lovely_bird/ ') == ['ows', 'proxy', 'lovely_bird']


def test_lxml_strip_ns():
    import lxml.etree
    wpsxml = """
<wps100:Execute
xmlns:wps100="http://www.opengis.net/wps/1.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
service="WPS"
version="1.0.0"
xsi:schemaLocation="http://www.opengis.net/wps/1.0.0 http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd"/>"""

    doc = lxml.etree.fromstring(wpsxml)
    assert doc.tag == '{http://www.opengis.net/wps/1.0.0}Execute'
    utils.lxml_strip_ns(doc)
    assert doc.tag == 'Execute'


def test_replace_caps_url_wps():
    doc = etree.parse(WPS_CAPS_EMU_XML)
    xml = etree.tostring(doc)
    assert 'http://localhost:8094/wps' in xml
    xml = utils.replace_caps_url(xml, "https://localhost/ows/proxy/emu")
    assert 'http://localhost:8094/wps' not in xml
    assert 'https://localhost/ows/proxy/emu' in xml


def test_replace_caps_url_wms_111():
    doc = etree.parse(WMS_CAPS_NCWMS2_111_XML)
    xml = etree.tostring(doc)
    assert 'http://localhost:8080/ncWMS2/wms' in xml
    xml = utils.replace_caps_url(xml, "https://localhost/ows/proxy/wms")
    # assert 'http://localhost:8080/ncWMS2/wms' not in xml
    assert 'https://localhost/ows/proxy/wms' in xml


def test_replace_caps_url_wms_130():
    doc = etree.parse(WMS_CAPS_NCWMS2_130_XML)
    xml = etree.tostring(doc)
    assert 'http://localhost:8080/ncWMS2/wms' in xml
    xml = utils.replace_caps_url(xml, "https://localhost/ows/proxy/wms")
    # assert 'http://localhost:8080/ncWMS2/wms' not in xml
    assert 'https://localhost/ows/proxy/wms' in xml
