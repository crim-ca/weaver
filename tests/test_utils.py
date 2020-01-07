from weaver import utils
from weaver import status
from weaver.utils import null, _NullType   # noqa: W0212
from weaver.exceptions import ServiceNotFound
from tests.resources import WPS_CAPS_EMU_XML, WMS_CAPS_NCWMS2_111_XML, WMS_CAPS_NCWMS2_130_XML
from pyramid.httpexceptions import HTTPError as PyramidHTTPError, HTTPInternalServerError, HTTPNotFound, HTTPConflict
from pywps.response.status import WPS_STATUS
from requests.exceptions import HTTPError as RequestsHTTPError
from six.moves.urllib.parse import urlparse
from lxml import etree
from typing import Type
import pytest


def test_null_operators():
    if null:
        raise AssertionError("null should not pass if clause")
    n = null.__class__
    assert null == n
    assert null == n()
    assert null.__class__ == n
    assert null.__class__ == n()
    assert null != None  # noqa: E711
    assert null is not None
    assert bool(null) is False
    assert null or "not-null" == "not-null"


def test_null_singleton():
    nn = _NullType()
    assert null is nn
    assert null is _NullType


def test_is_url_valid():
    assert utils.is_valid_url("http://somewhere.org") is True
    assert utils.is_valid_url("https://somewhere.org/my/path") is True
    assert utils.is_valid_url("file:///my/path") is True
    assert utils.is_valid_url("/my/path") is False
    assert utils.is_valid_url(None) is False


def test_parse_service_name():
    protected_path = "/ows/proxy"
    assert "emu" == utils.parse_service_name("/ows/proxy/emu", protected_path)
    assert "emu" == utils.parse_service_name("/ows/proxy/emu/foo/bar", protected_path)
    assert "emu" == utils.parse_service_name("/ows/proxy/emu/", protected_path)
    with pytest.raises(ServiceNotFound):
        assert "emu" == utils.parse_service_name("/ows/proxy/", protected_path)
    with pytest.raises(ServiceNotFound):
        assert "emu" == utils.parse_service_name("/ows/nowhere/emu", protected_path)


def test_get_url_without_query():
    url_h = "http://some-host.com/wps"
    url_q = "{}?service=WPS".format(url_h)
    url_p = urlparse(url_q)
    assert utils.get_url_without_query(url_q) == url_h
    assert utils.get_url_without_query(url_p) == url_h
    assert utils.get_url_without_query(url_h) == url_h


def test_get_base_url():
    assert utils.get_base_url("http://localhost:8094/wps") == "http://localhost:8094/wps"
    assert utils.get_base_url("http://localhost:8094/wps?service=wps&request=getcapabilities") == \
        "http://localhost:8094/wps"
    assert utils.get_base_url("https://localhost:8094/wps?service=wps&request=getcapabilities") == \
        "https://localhost:8094/wps"
    with pytest.raises(ValueError):
        utils.get_base_url("ftp://localhost:8094/wps")


def test_path_elements():
    assert utils.path_elements("/ows/proxy/lovely_bird") == ["ows", "proxy", "lovely_bird"]
    assert utils.path_elements("/ows/proxy/lovely_bird/") == ["ows", "proxy", "lovely_bird"]
    assert utils.path_elements("/ows/proxy/lovely_bird/ ") == ["ows", "proxy", "lovely_bird"]


def test_lxml_strip_ns():
    wps_xml = """
<wps100:Execute
xmlns:wps100="http://www.opengis.net/wps/1.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
service="WPS"
version="1.0.0"
xsi:schemaLocation="http://www.opengis.net/wps/1.0.0 http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd"/>"""

    doc = etree.fromstring(wps_xml)
    assert doc.tag == "{http://www.opengis.net/wps/1.0.0}Execute"
    utils.lxml_strip_ns(doc)
    assert doc.tag == "Execute"


class MockRequest(object):
    def __init__(self, url):
        self.url = url

    @property
    def query_string(self):
        return urlparse(self.url).query


def test_parse_request_query_basic():
    req = MockRequest("http://localhost:5000/ows/wps?service=wps&request=GetCapabilities&version=1.0.0")
    queries = utils.parse_request_query(req)    # noqa
    assert "service" in queries
    assert isinstance(queries["service"], dict)
    assert queries["service"][0] == "wps"
    assert "request" in queries
    assert isinstance(queries["request"], dict)
    assert queries["request"][0] == "getcapabilities"
    assert "version" in queries
    assert isinstance(queries["version"], dict)
    assert queries["version"][0] == "1.0.0"


def test_parse_request_query_many_datainputs_multi_case():
    req = MockRequest("http://localhost:5000/ows/wps?service=wps&request=GetCapabilities&version=1.0.0&" +
                      "datainputs=data1=value1&dataInputs=data2=value2&DataInputs=data3=value3")
    # noinspection PyTypeChecker
    queries = utils.parse_request_query(req)
    assert "datainputs" in queries
    assert isinstance(queries["datainputs"], dict)
    assert "data1" in queries["datainputs"]
    assert "data2" in queries["datainputs"]
    assert "data3" in queries["datainputs"]
    assert "value1" in queries["datainputs"].values()
    assert "value2" in queries["datainputs"].values()
    assert "value3" in queries["datainputs"].values()


def raise_http_error(http):
    raise http("Excepted raise HTTPError")


def make_http_error(http):
    # type: (PyramidHTTPError) -> Type[RequestsHTTPError]
    err = RequestsHTTPError
    err.status_code = http.code
    return err


def test_pass_http_error_doesnt_raise_single_pyramid_error():
    http_errors = [HTTPNotFound, HTTPInternalServerError]
    for err in http_errors:
        # test try/except
        try:
            # normal usage try/except
            try:
                raise_http_error(err)
            except Exception as ex:
                utils.pass_http_error(ex, err)
        except PyramidHTTPError:
            pytest.fail("PyramidHTTPError should be ignored but was raised.")


def test_pass_http_error_doesnt_raise_multi_pyramid_error():
    http_errors = [HTTPNotFound, HTTPInternalServerError]
    for err in http_errors:
        # test try/except
        try:
            # normal usage try/except
            try:
                raise_http_error(err)
            except Exception as ex:
                utils.pass_http_error(ex, http_errors)
        except PyramidHTTPError:
            pytest.fail("PyramidHTTPError should be ignored but was raised.")


def test_pass_http_error_doesnt_raise_requests_error():
    http_errors = [HTTPNotFound, HTTPInternalServerError]
    for err in http_errors:
        req_err = make_http_error(err)
        # test try/except
        try:
            # normal usage try/except
            try:
                raise_http_error(req_err)
            except Exception as ex:
                utils.pass_http_error(ex, err)
        except RequestsHTTPError:
            pytest.fail("RequestsHTTPError should be ignored but was raised.")


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


def get_status_variations(status_value):
    return [status_value.lower(),
            status_value.upper(),
            status_value.capitalize(),
            "Process" + status_value.capitalize()]


def test_map_status_ogc_compliant():
    for sv in status.job_status_values:
        for s in get_status_variations(sv):
            assert status.map_status(s, status.STATUS_COMPLIANT_OGC) in \
                   status.job_status_categories[status.STATUS_COMPLIANT_OGC]


def test_map_status_pywps_compliant():
    for sv in status.job_status_values:
        for s in get_status_variations(sv):
            assert status.map_status(s, status.STATUS_COMPLIANT_PYWPS) in \
                   status.job_status_categories[status.STATUS_COMPLIANT_PYWPS]


def test_map_status_owslib_compliant():
    for sv in status.job_status_values:
        for s in get_status_variations(sv):
            assert status.map_status(s, status.STATUS_COMPLIANT_OWSLIB) in \
                   status.job_status_categories[status.STATUS_COMPLIANT_OWSLIB]


def test_map_status_back_compatibility_and_special_cases():
    for c in [status.STATUS_COMPLIANT_OGC, status.STATUS_COMPLIANT_PYWPS, status.STATUS_COMPLIANT_OWSLIB]:
        assert status.map_status("successful", c) == status.STATUS_SUCCEEDED


def test_map_status_pywps_compliant_as_int_statuses():
    for s in range(len(WPS_STATUS)):
        if status.STATUS_PYWPS_MAP[s] != status.STATUS_UNKNOWN:
            assert status.map_status(s, status.STATUS_COMPLIANT_PYWPS) in \
                   status.job_status_categories[status.STATUS_COMPLIANT_PYWPS]


def test_map_status_pywps_back_and_forth():
    for s, i in status.STATUS_PYWPS_MAP.items():
        assert status.STATUS_PYWPS_IDS[i] == s


# noinspection PyTypeChecker
def test_get_sane_name_replace():
    kw = {"assert_invalid": False, "max_len": 25}
    assert utils.get_sane_name("Hummingbird", **kw) == "Hummingbird"
    assert utils.get_sane_name("MapMint Demo Instance", **kw) == "MapMint_Demo_Instance"
    assert utils.get_sane_name(None, **kw) is None
    assert utils.get_sane_name("12", **kw) is None
    assert utils.get_sane_name(" ab c ", **kw) == "ab_c"
    assert utils.get_sane_name("a_much_to_long_name_for_this_test", **kw) == "a_much_to_long_name_for_t"


def test_assert_sane_name():
    test_cases_invalid = [
        None,
        "12",   # too short
        " ab c ",
        "MapMint Demo Instance",
        "double--dashes_not_ok",
        "-start_dash_not_ok",
        "end_dash_not_ok-",
        "no_exclamation!point",
        "no_interrogation?point",
        "no_slashes/allowed",
        "no_slashes\\allowed",
    ]
    for test in test_cases_invalid:
        with pytest.raises(ValueError):
            utils.assert_sane_name(test)

    test_cases_valid = [
        "Hummingbird",
        "short",
        "a_very_long_name_for_this_test_is_ok_if_max_len_is_none",
        "AlTeRnAtInG_cApS"
        "middle-dashes-are-ok",
        "underscores_also_ok",
    ]
    for test in test_cases_valid:
        utils.assert_sane_name(test)


def test_str2bytes():
    assert utils.str2bytes(b"test-bytes") == b"test-bytes"
    assert utils.str2bytes(u"test-unicode") == b"test-unicode"


def test_bytes2str():
    assert utils.bytes2str(b"test-bytes") == u"test-bytes"
    assert utils.bytes2str(u"test-unicode") == u"test-unicode"
