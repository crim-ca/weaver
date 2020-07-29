# pylint: disable=C0103,invalid-name

import contextlib
import inspect
import json
import os
import shutil
import tempfile
from typing import Type
from urllib.parse import urlparse

import mock
import pytest
from lxml import etree
from pyramid.httpexceptions import (
    HTTPConflict,
    HTTPCreated,
    HTTPError as PyramidHTTPError,
    HTTPGatewayTimeout,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPOk
)
from pywps.response.status import WPS_STATUS
from requests import Response
from requests.exceptions import HTTPError as RequestsHTTPError

from tests.utils import mocked_aws_credentials, mocked_aws_s3, mocked_aws_s3_bucket_test_file, mocked_file_response
from weaver import status, utils
from weaver.utils import (
    NullType,
    fetch_file,
    get_path_kvp,
    get_request_options,
    get_ssl_verify_option,
    make_dirs,
    null,
    request_extra
)


def test_null_operators():
    if null:
        raise AssertionError("null should not pass if clause")
    n = null.__class__
    assert null == n
    assert null == n()
    assert null.__class__ == n
    assert null.__class__ == n()
    # pylint: disable=C0121,singleton-comparison
    assert null != None     # noqa: E711
    assert null is not None
    assert bool(null) is False
    assert (null or "not-null") == "not-null"


def test_null_singleton():
    n1 = NullType()
    n2 = NullType()
    # pylint: disable=C0123,unidiomatic-typecheck
    assert type(null) is NullType
    assert null is n1
    assert null is n2
    assert n1 is n2


def test_is_url_valid():
    assert utils.is_valid_url("http://somewhere.org") is True
    assert utils.is_valid_url("https://somewhere.org/my/path") is True
    assert utils.is_valid_url("file:///my/path") is True
    assert utils.is_valid_url("/my/path") is False
    assert utils.is_valid_url(None) is False


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


def test_xml_path_elements():
    assert utils.xml_path_elements("/ows/proxy/lovely_bird") == ["ows", "proxy", "lovely_bird"]
    assert utils.xml_path_elements("/ows/proxy/lovely_bird/") == ["ows", "proxy", "lovely_bird"]
    assert utils.xml_path_elements("/ows/proxy/lovely_bird/ ") == ["ows", "proxy", "lovely_bird"]


def test_xml_strip_ns():
    wps_xml = """
<wps100:Execute
xmlns:wps100="http://www.opengis.net/wps/1.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
service="WPS"
version="1.0.0"
xsi:schemaLocation="http://www.opengis.net/wps/1.0.0 http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd"/>"""

    doc = etree.fromstring(wps_xml)
    assert doc.tag == "{http://www.opengis.net/wps/1.0.0}Execute"
    utils.xml_strip_ns(doc)
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
    queries = utils.parse_request_query(req)  # noqa
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
    for sv in status.JOB_STATUS_VALUES:
        for s in get_status_variations(sv):
            assert status.map_status(s, status.STATUS_COMPLIANT_OGC) in \
                   status.JOB_STATUS_CATEGORIES[status.STATUS_COMPLIANT_OGC]


def test_map_status_pywps_compliant():
    for sv in status.JOB_STATUS_VALUES:
        for s in get_status_variations(sv):
            assert status.map_status(s, status.STATUS_COMPLIANT_PYWPS) in \
                   status.JOB_STATUS_CATEGORIES[status.STATUS_COMPLIANT_PYWPS]


def test_map_status_owslib_compliant():
    for sv in status.JOB_STATUS_VALUES:
        for s in get_status_variations(sv):
            assert status.map_status(s, status.STATUS_COMPLIANT_OWSLIB) in \
                   status.JOB_STATUS_CATEGORIES[status.STATUS_COMPLIANT_OWSLIB]


def test_map_status_back_compatibility_and_special_cases():
    for c in [status.STATUS_COMPLIANT_OGC, status.STATUS_COMPLIANT_PYWPS, status.STATUS_COMPLIANT_OWSLIB]:
        assert status.map_status("successful", c) == status.STATUS_SUCCEEDED


def test_map_status_pywps_compliant_as_int_statuses():
    for s in range(len(WPS_STATUS)):
        if status.STATUS_PYWPS_MAP[s] != status.STATUS_UNKNOWN:
            assert status.map_status(s, status.STATUS_COMPLIANT_PYWPS) in \
                   status.JOB_STATUS_CATEGORIES[status.STATUS_COMPLIANT_PYWPS]


def test_map_status_pywps_back_and_forth():
    for s, i in status.STATUS_PYWPS_MAP.items():
        assert status.STATUS_PYWPS_IDS[i] == s


def test_get_sane_name_replace():
    kw = {"assert_invalid": False, "max_len": 25}
    assert utils.get_sane_name("Hummingbird", **kw) == "Hummingbird"
    assert utils.get_sane_name("MapMint Demo Instance", **kw) == "MapMint_Demo_Instance"
    assert utils.get_sane_name(None, **kw) is None  # noqa
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


def test_get_ssl_verify_option():
    assert get_ssl_verify_option("get", "http://test.com", {}) is True
    assert get_ssl_verify_option("get", "http://test.com", {"weaver.ssl_verify": False}) is False
    assert get_ssl_verify_option("get", "http://test.com", {"weaver.ssl_verify": True}) is True
    assert get_ssl_verify_option("get", "http://test.com", {"weaver.request_options": {
        "requests": [{"url": "http://test.com/", "method": "get"}]}
    }) is True
    assert get_ssl_verify_option("get", "http://test.com", {"weaver.request_options": {
        "requests": [{"url": "http://test.com/", "method": "get", "verify": False}]}
    }) is False
    assert get_ssl_verify_option("get", "http://test.com", {"weaver.request_options": {
        "requests": [{"url": "http://other.com/", "method": "get", "verify": False}]}
    }) is True
    assert get_ssl_verify_option("get", "http://test.com/valid-path", {"weaver.request_options": {
        "requests": [{"url": "http://test.com/*", "method": "get", "verify": False}]}
    }) is False
    assert get_ssl_verify_option("get", "http://test.com/invalid", {"weaver.request_options": {
        "requests": [{"url": "http://test.com/valid*", "method": "get", "verify": False}]}
    }) is True
    assert get_ssl_verify_option("get", "http://test.com/invalid/other", {"weaver.request_options": {
        "requests": [{"url": ["http://test.com/valid*", "http://test.com/*/other"], "method": "get", "verify": False}]}
    }) is False
    assert get_ssl_verify_option("get", "http://test.com/valid", {"weaver.request_options": {
        "requests": [{"url": ["http://test.com/valid*"], "method": "post", "verify": False}]}
    }) is True
    assert get_ssl_verify_option("get", "http://test.com/invalid", {
        "weaver.ssl_verify": False,
        "weaver.request_options": {
            "requests": [{"url": "http://test.com/valid*", "method": "get", "verify": True}]}
    }) is False
    assert get_ssl_verify_option("get", "http://test.com/invalid", {
        "weaver.ssl_verify": True,
        "weaver.request_options": {
            "requests": [{"url": "http://test.com/valid*", "method": "get", "verify": False}]}
    }) is True
    assert get_ssl_verify_option("get", "http://test.com/valid/good-path", {
        "weaver.ssl_verify": True,
        "weaver.request_options": {
            "requests": [{"url": "http://test.com/valid/*", "method": "get", "verify": False}]}
    }) is False
    any_wps_url = "http://test.com/wps"
    any_wps_conf = {
        "weaver.ssl_verify": True,
        "weaver.request_options": {
            "requests": [{"url": any_wps_url, "verify": False}]
        }
    }
    tests = [
        ("GET", "service=WPS&request=GetCapabilities&version=1.0.0"),
        ("GET", "service=WPS&request=DescribeProcess&version=1.3.0&identifier=test"),
        ("POST", "service=WPS&request=Execute&version=2.0.0&identifier=test"),
    ]
    for method, queries in tests:
        url = "{}?{}".format(any_wps_url, queries)
        assert get_ssl_verify_option(method, url, any_wps_conf)


def test_request_extra_allowed_codes():
    """Verifies that ``allowed_codes`` only are considered as valid status instead of any non-error HTTP code."""
    mocked_codes = {"codes": [HTTPCreated.code, HTTPOk.code, HTTPCreated.code]}  # note: used in reverse order

    def mocked_request(*args, **kwargs):  # noqa: E811
        mocked_resp = Response()
        mocked_resp.status_code = mocked_codes["codes"].pop()
        return mocked_resp

    with mock.patch("requests.Session.request", side_effect=mocked_request) as mocked:
        resp = request_extra("get", "http://whatever", retries=3, allowed_codes=[HTTPOk.code])
        assert resp.status_code == HTTPOk.code
        assert mocked.call_count == 2


def test_get_request_options():
    assert get_request_options("get", "http://test.com", {
        "weaver.request_options": {"requests": [
            {"url": "http://test.com/*", "verify": False}
        ]}
    }) == {"verify": False}
    assert get_request_options("get", "http://test.com", {
        "weaver.request_options": {"requests": [
            {"url": "http://other.com/*", "verify": False},
            {"url": "http://test.com/*", "verify": True, "timeout": 30}
        ]}
    }) == {"verify": True, "timeout": 30}
    assert get_request_options("get", "http://test.com/random", {
        "weaver.request_options": {"requests": [
            {"url": "http://*/random", "verify": False},  # stop at first match
            {"url": "http://test.com/*", "verify": True, "timeout": 30}
        ]}
    }) == {"verify": False}
    assert get_request_options("get", "http://test.com", {
        "weaver.request_options": {"requests": [
            {"url": "http://*.com", "method": "post", "verify": False},
            {"url": "http://test.com/*", "timeout": 30}
        ]}
    }) == {"timeout": 30}


def test_request_extra_intervals():
    """Verifies that ``intervals`` are used for calling the retry operations instead of ``backoff``/``retries``."""

    def mock_request(*args, **kwargs):  # noqa: E811
        m_resp = Response()
        m_resp.status_code = HTTPNotFound.code
        return m_resp

    sleep_counter = {"called_count": 0, "called_with": []}

    def mock_sleep(delay):  # noqa: E811
        if delay > 1e5:
            sleep_counter["called_count"] += 1
            sleep_counter["called_with"].append(delay)

    with mock.patch("requests.Session.request", side_effect=mock_request) as mocked_request:
        with mock.patch("weaver.utils.time.sleep", side_effect=mock_sleep):
            intervals = [1e6, 3e6, 5e6]  # random values that shouldn't normally be used with sleep() (too big)
            # values will not match if backoff/retries are not automatically corrected by internals parameter
            resp = request_extra("get", "http://whatever", only_server_errors=False,
                                 intervals=intervals, backoff=1000, retries=10)  # backoff/retries must be ignored here
            assert resp.status_code == HTTPGatewayTimeout.code
            assert mocked_request.call_count == 4  # first called directly, then 3 times, one for each interval
            # WARNING:
            #   cannot safely use mock counter since everything can increase it
            #   notably debugger/breakpoints that uses more calls to sleep()
            #   instead use our custom counter that employs unrealistic values
            assert sleep_counter["called_count"] == 3  # first direct call doesn't have any sleep interval
            assert all(called == expect for called, expect in zip(sleep_counter["called_with"], intervals))


def test_fetch_file_local_with_protocol():
    """
    Test function :func:`weaver.utils.fetch_file` when the reference is a pre-fetched local file.
    """
    tmp_dir = tempfile.gettempdir()
    with tempfile.NamedTemporaryFile(dir=tmp_dir, mode="w", suffix=".json") as tmp_json:
        tmp_data = {"message": "fetch-file-protocol"}
        tmp_json.write(json.dumps(tmp_data))
        tmp_json.seek(0)
        tmp_name = os.path.split(tmp_json.name)[-1]
        res_dir = os.path.join(tmp_dir, inspect.currentframe().f_code.co_name)
        res_path = os.path.join(res_dir, tmp_name)
        try:
            make_dirs(res_dir, exist_ok=True)
            for protocol in ["", "file://"]:
                tmp_path = protocol + tmp_json.name
                fetch_file(tmp_path, res_dir)
                assert os.path.isfile(res_path), "File [{}] should be accessible under [{}]".format(tmp_path, res_path)
                assert json.load(open(res_path)) == tmp_data, "File should be properly copied/referenced from original"
        except Exception:
            raise
        finally:
            shutil.rmtree(res_dir, ignore_errors=True)


def test_fetch_file_remote_with_request():
    """
    Test function :func:`weaver.utils.fetch_file` when the reference is an URL.
    Also validates retries of the failing request.
    """
    tmp_dir = tempfile.gettempdir()
    with contextlib.ExitStack() as stack:
        tmp_json = stack.enter_context(tempfile.NamedTemporaryFile(dir=tmp_dir, mode="w", suffix=".json"))
        tmp_data = {"message": "fetch-file-request"}
        tmp_json.write(json.dumps(tmp_data))
        tmp_json.seek(0)
        tmp_name = os.path.split(tmp_json.name)[-1]
        tmp_http = "http://weaver.mock" + tmp_json.name
        tmp_retry = 2

        # share in below mocked_request, 'nonlocal' back compatible with Python 2
        tmp = {"retry": tmp_retry, "json": tmp_json, "http": tmp_http}

        def mocked_request(*args, **kwargs):  # noqa: E811
            tmp["retry"] -= 1
            if not tmp["retry"]:
                return mocked_file_response(tmp["json"].name, tmp["http"])
            resp = HTTPInternalServerError()  # internal retry expect at least a 5xx code to retry
            return resp  # will be available on next call (to test retries)

        stack.enter_context(mock.patch("requests.request", side_effect=mocked_request))
        stack.enter_context(mock.patch("requests.sessions.Session.request", side_effect=mocked_request))
        m_request = stack.enter_context(mock.patch("requests.Session.request", side_effect=mocked_request))

        res_dir = os.path.join(tmp_dir, inspect.currentframe().f_code.co_name)
        res_path = os.path.join(res_dir, tmp_name)
        try:
            make_dirs(res_dir, exist_ok=True)
            fetch_file(tmp_http, res_dir, retry=tmp_retry + 1)
            assert os.path.isfile(res_path), "File [{}] should be accessible under [{}]".format(tmp_http, res_path)
            assert m_request.call_count == 2, "Request method should have been called twice because of retries"
            assert json.load(open(res_path)) == tmp_data, "File should be properly generated from HTTP reference"
        except Exception:
            raise
        finally:
            shutil.rmtree(res_dir, ignore_errors=True)


@mocked_aws_credentials
@mocked_aws_s3
def test_fetch_file_remote_s3_bucket():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file_name = "test-file.txt"
        test_file_data = "dummy file"
        test_bucket_name = "test-fake-bucket"
        test_bucket_ref = mocked_aws_s3_bucket_test_file(test_bucket_name, test_file_name, test_file_data)
        result = fetch_file(test_bucket_ref, tmpdir)
        assert result == os.path.join(tmpdir, test_file_name)
        assert os.path.isfile(result)
        with open(result, mode="r") as test_file:
            assert test_file.read() == test_file_data


def test_get_path_kvp():
    res = get_path_kvp("http://localhost", test1="value1", test2=["sub1", "sub2"])
    assert res == "http://localhost?test1=value1&test2=sub1,sub2"
