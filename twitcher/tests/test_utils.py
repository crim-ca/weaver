# noinspection PyPackageRequirements
import pytest
from lxml import etree
from typing import Type
from twitcher import utils
from twitcher._compat import urlparse
from twitcher.exceptions import ServiceNotFound
from twitcher.tests.common import WPS_CAPS_EMU_XML, WMS_CAPS_NCWMS2_111_XML, WMS_CAPS_NCWMS2_130_XML
from pyramid.httpexceptions import HTTPError as PyramidHTTPError, HTTPInternalServerError, HTTPNotFound, HTTPConflict
from requests.exceptions import HTTPError as RequestsHTTPError


def test_is_url_valid():
    assert utils.is_valid_url("http://somewhere.org") is True
    assert utils.is_valid_url("https://somewhere.org/my/path") is True
    assert utils.is_valid_url("file:///my/path") is True
    assert utils.is_valid_url("/my/path") is False
    assert utils.is_valid_url(None) is False


def test_parse_service_name():
    protected_path = '/ows/proxy'
    assert 'emu' == utils.parse_service_name("/ows/proxy/emu", protected_path)
    assert 'emu' == utils.parse_service_name("/ows/proxy/emu/foo/bar", protected_path)
    assert 'emu' == utils.parse_service_name("/ows/proxy/emu/", protected_path)
    with pytest.raises(ServiceNotFound):
        assert 'emu' == utils.parse_service_name("/ows/proxy/", protected_path)
    with pytest.raises(ServiceNotFound):
        assert 'emu' == utils.parse_service_name("/ows/nowhere/emu", protected_path)


def test_baseurl():
    assert utils.baseurl('http://localhost:8094/wps') == 'http://localhost:8094/wps'
    assert utils.baseurl('http://localhost:8094/wps?service=wps&request=getcapabilities') == 'http://localhost:8094/wps'
    assert utils.baseurl('https://localhost:8094/wps?service=wps&request=getcapabilities') ==\
        'https://localhost:8094/wps'
    with pytest.raises(ValueError):
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


class MockRequest(object):
    def __init__(self, url):
        self.url = url

    @property
    def query_string(self):
        return urlparse(self.url).query


def test_parse_request_query_basic():
    req = MockRequest('http://localhost:5000/ows/wps?service=wps&request=GetCapabilities&version=1.0.0')
    queries = utils.parse_request_query(req)
    assert 'service' in queries
    assert isinstance(queries['service'], dict)
    assert queries['service'][0] == 'wps'
    assert 'request' in queries
    assert isinstance(queries['request'], dict)
    assert queries['request'][0] == 'getcapabilities'
    assert 'version' in queries
    assert isinstance(queries['version'], dict)
    assert queries['version'][0] == '1.0.0'


def test_parse_request_query_many_datainputs_multicase():
    req = MockRequest('http://localhost:5000/ows/wps?service=wps&request=GetCapabilities&version=1.0.0&' +
                      'datainputs=data1=value1&dataInputs=data2=value2&DataInputs=data3=value3')
    queries = utils.parse_request_query(req)
    assert 'datainputs' in queries
    assert isinstance(queries['datainputs'], dict)
    assert 'data1' in queries['datainputs']
    assert 'data2' in queries['datainputs']
    assert 'data3' in queries['datainputs']
    assert 'value1' in queries['datainputs'].values()
    assert 'value2' in queries['datainputs'].values()
    assert 'value3' in queries['datainputs'].values()


def raise_http_error(http):
    raise http('Excepted raise HTTPError')


def make_http_error(http):
    # type: (PyramidHTTPError) -> Type[RequestsHTTPError]
    err = RequestsHTTPError
    err.status_code = http.code
    return err


@pytest.mark.xfail(raises=PyramidHTTPError)
def test_pass_http_error_doesnt_raise_single_pyramid_error():
    http_errors = [HTTPNotFound, HTTPInternalServerError]
    for err in http_errors:
        try:
            raise_http_error(err)
        except Exception as ex:
            utils.pass_http_error(ex, err)


@pytest.mark.xfail(raises=PyramidHTTPError)
def test_pass_http_error_doesnt_raise_multi_pyramid_error():
    http_errors = [HTTPNotFound, HTTPInternalServerError]
    for err in http_errors:
        try:
            raise_http_error(err)
        except Exception as ex:
            utils.pass_http_error(ex, http_errors)


@pytest.mark.xfail(raises=RequestsHTTPError)
def test_pass_http_error_doesnt_raise_requests_error():
    http_errors = [HTTPNotFound, HTTPInternalServerError]
    for err in http_errors:
        req_err = make_http_error(err)
        try:
            raise_http_error(req_err)
        except Exception as ex:
            utils.pass_http_error(ex, err)


def test_pass_http_error_raises_pyramid_error_with_single_pyramid_error():
    with pytest.raises(HTTPNotFound):
        try:
            raise_http_error(HTTPNotFound)
        except Exception as ex:
            utils.pass_http_error(ex, HTTPConflict)


def test_pass_http_error_raises_pyramid_error_with_multi_pyramid_error():
    with pytest.raises(HTTPNotFound):
        try:
            raise_http_error(HTTPNotFound)
        except Exception as ex:
            utils.pass_http_error(ex, [HTTPConflict, HTTPInternalServerError])


def test_pass_http_error_raises_requests_error_with_single_pyramid_error():
    with pytest.raises(RequestsHTTPError):
        try:
            raise_http_error(make_http_error(HTTPNotFound))
        except Exception as ex:
            utils.pass_http_error(ex, HTTPConflict)


def test_pass_http_error_raises_requests_error_with_multi_pyramid_error():
    with pytest.raises(RequestsHTTPError):
        try:
            raise_http_error(make_http_error(HTTPNotFound))
        except Exception as ex:
            utils.pass_http_error(ex, [HTTPConflict, HTTPInternalServerError])


def test_pass_http_error_raises_other_error_with_single_pyramid_error():
    with pytest.raises(ValueError):
        try:
            raise ValueError("Test Error")
        except Exception as ex:
            utils.pass_http_error(ex, HTTPConflict)


def test_pass_http_error_raises_other_error_with_multi_pyramid_error():
    with pytest.raises(ValueError):
        try:
            raise ValueError("Test Error")
        except Exception as ex:
            utils.pass_http_error(ex, [HTTPConflict, HTTPInternalServerError])
