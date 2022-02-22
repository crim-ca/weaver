# pylint: disable=C0103,invalid-name

import contextlib
import inspect
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from typing import Type
from urllib.parse import quote, urlparse

import mock
import pytest
import pytz
import responses
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
from weaver import xml_util
from weaver.formats import ContentType
from weaver.status import JOB_STATUS_CATEGORIES, STATUS_PYWPS_IDS, STATUS_PYWPS_MAP, Status, StatusCompliant, map_status
from weaver.utils import (
    NullType,
    assert_sane_name,
    bytes2str,
    fetch_file,
    get_any_value,
    get_base_url,
    get_path_kvp,
    get_request_options,
    get_sane_name,
    get_ssl_verify_option,
    get_url_without_query,
    is_valid_url,
    localize_datetime,
    make_dirs,
    null,
    pass_http_error,
    request_extra,
    str2bytes,
    xml_path_elements,
    xml_strip_ns
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
    assert is_valid_url("http://somewhere.org") is True
    assert is_valid_url("https://somewhere.org/my/path") is True
    assert is_valid_url("file:///my/path") is True
    assert is_valid_url("/my/path") is False
    assert is_valid_url(None) is False


def test_get_url_without_query():
    url_h = "http://some-host.com/wps"
    url_q = "{}?service=WPS".format(url_h)
    url_p = urlparse(url_q)
    assert get_url_without_query(url_q) == url_h
    assert get_url_without_query(url_p) == url_h
    assert get_url_without_query(url_h) == url_h


def test_get_base_url():
    assert get_base_url("http://localhost:8094/wps") == "http://localhost:8094/wps"
    assert get_base_url("http://localhost:8094/wps?service=wps&request=getcapabilities") == \
        "http://localhost:8094/wps"
    assert get_base_url("https://localhost:8094/wps?service=wps&request=getcapabilities") == \
        "https://localhost:8094/wps"
    with pytest.raises(ValueError):
        get_base_url("ftp://localhost:8094/wps")


def test_xml_path_elements():
    assert xml_path_elements("/ows/proxy/lovely_bird") == ["ows", "proxy", "lovely_bird"]
    assert xml_path_elements("/ows/proxy/lovely_bird/") == ["ows", "proxy", "lovely_bird"]
    assert xml_path_elements("/ows/proxy/lovely_bird/ ") == ["ows", "proxy", "lovely_bird"]


def test_xml_strip_ns():
    wps_xml = """
<wps100:Execute
xmlns:wps100="http://www.opengis.net/wps/1.0.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
service="WPS"
version="1.0.0"
xsi:schemaLocation="http://www.opengis.net/wps/1.0.0 http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd"/>"""

    doc = xml_util.fromstring(wps_xml)
    assert doc.tag == "{http://www.opengis.net/wps/1.0.0}Execute"
    xml_strip_ns(doc)
    assert doc.tag == "Execute"


class MockRequest(object):
    def __init__(self, url):
        self.url = url

    @property
    def query_string(self):
        return urlparse(self.url).query


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
                pass_http_error(ex, err)
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
                pass_http_error(ex, http_errors)
        except PyramidHTTPError:
            pytest.fail("PyramidHTTPError should be ignored but was raised.")


def test_pass_http_error_doesnt_raise_requests_error():
    http_errors = [HTTPNotFound, HTTPInternalServerError]
    for err in http_errors:
        req_err = make_http_error(err)  # noqa
        # test try/except
        try:
            # normal usage try/except
            try:
                raise_http_error(req_err)
            except Exception as ex:
                pass_http_error(ex, err)
        except RequestsHTTPError:
            pytest.fail("RequestsHTTPError should be ignored but was raised.")


def test_pass_http_error_raises_pyramid_error_with_single_pyramid_error():
    with pytest.raises(HTTPNotFound):
        try:
            raise_http_error(HTTPNotFound)
        except Exception as ex:
            pass_http_error(ex, HTTPConflict)


def test_pass_http_error_raises_pyramid_error_with_multi_pyramid_error():
    with pytest.raises(HTTPNotFound):
        try:
            raise_http_error(HTTPNotFound)
        except Exception as ex:
            pass_http_error(ex, [HTTPConflict, HTTPInternalServerError])


def test_pass_http_error_raises_requests_error_with_single_pyramid_error():
    with pytest.raises(RequestsHTTPError):
        try:
            raise_http_error(make_http_error(HTTPNotFound))  # noqa
        except Exception as ex:
            pass_http_error(ex, HTTPConflict)


def test_pass_http_error_raises_requests_error_with_multi_pyramid_error():
    with pytest.raises(RequestsHTTPError):
        try:
            raise_http_error(make_http_error(HTTPNotFound))  # noqa
        except Exception as ex:
            pass_http_error(ex, [HTTPConflict, HTTPInternalServerError])


def test_pass_http_error_raises_other_error_with_single_pyramid_error():
    with pytest.raises(ValueError):
        try:
            raise ValueError("Test Error")
        except Exception as ex:
            pass_http_error(ex, HTTPConflict)


def test_pass_http_error_raises_other_error_with_multi_pyramid_error():
    with pytest.raises(ValueError):
        try:
            raise ValueError("Test Error")
        except Exception as ex:
            pass_http_error(ex, [HTTPConflict, HTTPInternalServerError])


def get_status_variations(status_value):
    return [status_value.lower(),
            status_value.upper(),
            status_value.capitalize(),
            "Process" + status_value.capitalize()]


def test_map_status_ogc_compliant():
    known_statuses = set(Status.values()) - {Status.UNKNOWN}
    for sv in known_statuses:
        for s in get_status_variations(sv):
            assert map_status(s, StatusCompliant.OGC) in JOB_STATUS_CATEGORIES[StatusCompliant.OGC]


def test_map_status_pywps_compliant():
    known_statuses = set(Status.values()) - {Status.UNKNOWN}
    for sv in known_statuses:
        for s in get_status_variations(sv):
            assert map_status(s, StatusCompliant.PYWPS) in JOB_STATUS_CATEGORIES[StatusCompliant.PYWPS]


def test_map_status_owslib_compliant():
    known_statuses = set(Status.values()) - {Status.UNKNOWN}
    for sv in known_statuses:
        for s in get_status_variations(sv):
            assert map_status(s, StatusCompliant.OWSLIB) in JOB_STATUS_CATEGORIES[StatusCompliant.OWSLIB]


def test_map_status_back_compatibility_and_special_cases():
    for c in StatusCompliant:
        assert map_status("successful", c) == Status.SUCCEEDED


def test_map_status_pywps_compliant_as_int_statuses():
    for s in range(len(WPS_STATUS)):
        if STATUS_PYWPS_MAP[s] != Status.UNKNOWN:
            assert map_status(s, StatusCompliant.PYWPS) in JOB_STATUS_CATEGORIES[StatusCompliant.PYWPS]


def test_map_status_pywps_back_and_forth():
    for s, i in STATUS_PYWPS_MAP.items():
        assert STATUS_PYWPS_IDS[i] == s


def test_get_sane_name_replace():
    kw = {"assert_invalid": False, "max_len": 25}
    assert get_sane_name("Hummingbird", **kw) == "Hummingbird"
    assert get_sane_name("MapMint Demo Instance", **kw) == "MapMint_Demo_Instance"
    assert get_sane_name(None, **kw) is None  # noqa
    assert get_sane_name("12", **kw) is None
    assert get_sane_name(" ab c ", **kw) == "ab_c"
    assert get_sane_name("a_much_to_long_name_for_this_test", **kw) == "a_much_to_long_name_for_t"


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
            assert_sane_name(test)

    test_cases_valid = [
        "Hummingbird",
        "short",
        "a_very_long_name_for_this_test_is_ok_if_max_len_is_none",
        "AlTeRnAtInG_cApS"
        "middle-dashes-are-ok",
        "underscores_also_ok",
    ]
    for test in test_cases_valid:
        assert_sane_name(test)


def test_str2bytes():
    assert str2bytes(b"test-bytes") == b"test-bytes"
    assert str2bytes(u"test-unicode") == b"test-unicode"


def test_bytes2str():
    assert bytes2str(b"test-bytes") == u"test-bytes"
    assert bytes2str(u"test-unicode") == u"test-unicode"


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


def test_request_extra_allowed_codes():
    """
    Verifies that ``allowed_codes`` only are considered as valid status instead of any non-error HTTP code.
    """
    mocked_codes = {"codes": [HTTPCreated.code, HTTPOk.code, HTTPCreated.code]}  # note: used in reverse order

    def mocked_request(*_, **__):
        mocked_resp = Response()
        mocked_resp.status_code = mocked_codes["codes"].pop()
        return mocked_resp

    with mock.patch("requests.Session.request", side_effect=mocked_request) as mocked:
        resp = request_extra("get", "http://whatever", retries=3, allowed_codes=[HTTPOk.code])
        assert resp.status_code == HTTPOk.code
        assert mocked.call_count == 2


def test_request_extra_intervals():
    """
    Verifies that ``intervals`` are used for calling the retry operations instead of ``backoff``/``retries``.
    """

    def mock_request(*_, **__):
        m_resp = Response()
        m_resp.status_code = HTTPNotFound.code
        return m_resp

    sleep_counter = {"called_count": 0, "called_with": []}

    def mock_sleep(delay):
        if delay > 1e5:
            sleep_counter["called_count"] += 1
            sleep_counter["called_with"].append(delay)

    with mock.patch("weaver.utils.get_settings", return_value={"cache.requests.enable": "false"}):
        with mock.patch("requests.Session.request", side_effect=mock_request) as mocked_request:
            with mock.patch("weaver.utils.time.sleep", side_effect=mock_sleep):
                intervals = [1e6, 3e6, 5e6]  # random values that shouldn't normally be used with sleep() (too big)
                # values will not match if backoff/retries are not automatically corrected by internals parameter
                resp = request_extra("get", "http://whatever",
                                     only_server_errors=False, intervals=intervals,
                                     backoff=1000, retries=10)  # backoff/retries must be ignored here
                assert resp.status_code == HTTPGatewayTimeout.code
                assert mocked_request.call_count == 4  # first called directly, then 3 times, one for each interval
                # WARNING:
                #   cannot safely use mock counter since everything can increase it
                #   notably debugger/breakpoints that uses more calls to sleep()
                #   instead use our custom counter that employs unrealistic values
                assert sleep_counter["called_count"] == 3  # first direct call doesn't have any sleep interval
                assert all(called == expect for called, expect in zip(sleep_counter["called_with"], intervals))


def test_request_extra_zero_values():
    """
    Test that zero-value ``retries`` and ``backoff`` are not ignored.
    """
    def mock_request(*_, **__):
        mocked_resp = Response()
        mocked_resp.status_code = HTTPNotFound.code
        return mocked_resp

    with mock.patch("requests.Session.request", side_effect=mock_request) as mocked_request:
        resp = request_extra("get", "http://whatever", retries=0, allowed_codes=[HTTPOk.code])
        assert resp.status_code == HTTPGatewayTimeout.code, "failing request with no retry should produce timeout"
        assert mocked_request.call_count == 1

    sleep_counter = {"called_count": 0, "called_with": []}

    def mock_sleep(delay):
        sleep_counter["called_count"] += 1
        sleep_counter["called_with"].append(delay)

    with mock.patch("weaver.utils.get_settings", return_value={"cache.requests.enable": "false"}):
        with mock.patch("requests.Session.request", side_effect=mock_request) as mocked_request:
            with mock.patch("weaver.utils.time.sleep", side_effect=mock_sleep):
                # if backoff is not correctly handled as explicit zero, the default backoff value would be used
                # to calculate the delay between requests which should increase with backoff formula and retry count
                resp = request_extra("get", "http://whatever", backoff=0, retries=3, allowed_codes=[HTTPOk.code])
                assert resp.status_code == HTTPGatewayTimeout.code
                assert mocked_request.call_count == 4  # first called directly, then 3 times for each retry

    # since backoff factor multiplies all incrementally increasing delays between requests,
    # proper detection of input backoff=0 makes all sleep calls equal to zero
    assert all(backoff == 0 for backoff in sleep_counter["called_with"])
    assert sleep_counter["called_count"] == 3  # first direct call doesn't have any sleep from retry


def test_fetch_file_local_links():
    """
    Test handling of symbolic links by function :func:`weaver.utils.fetch_file` for local files.
    """
    tmp_dir = tempfile.gettempdir()
    src_dir = os.path.join(tmp_dir, str(uuid.uuid4()))
    dst_dir = os.path.join(tmp_dir, str(uuid.uuid4()))
    try:
        make_dirs(src_dir, exist_ok=True)
        make_dirs(dst_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=src_dir, mode="w", suffix=".json") as tmp_json:
            tmp_data = {"message": "fetch-file-link"}
            tmp_json.write(json.dumps(tmp_data))
            tmp_json.seek(0)
            tmp_file = tmp_json.name
            tmp_path, tmp_name = os.path.split(tmp_file)
            tmp_link = os.path.join(tmp_path, "link.json")
            os.symlink(tmp_file, tmp_link)
            dst_path = os.path.join(dst_dir, tmp_name)
            for src_path, as_link, result_link in [
                (tmp_file, True, True),
                (tmp_file, False, False),
                (tmp_file, None, False),
                (tmp_link, True, True),
                (tmp_link, False, False),
                (tmp_link, None, True),
            ]:
                if os.path.exists(dst_path):
                    os.remove(dst_path)
                fetch_file(src_path, dst_dir, link=as_link)
                assert os.path.isfile(dst_path), "File [{}] should be accessible under [{}]. Failed with: {}".format(
                    tmp_file, dst_path, (src_path, as_link, result_link)
                )
                if result_link:
                    assert os.path.islink(dst_path), "Result is not a link when it is expected to be one."
                else:
                    assert not os.path.islink(dst_path), "Result is a link when it is expected not to be one."
                assert json.load(open(dst_path)) == tmp_data, "File should be properly copied/referenced from original"
    except OSError as exc:
        pytest.fail("Unexpected error raised during test: [{}]".format(exc))
    finally:
        shutil.rmtree(src_dir, ignore_errors=True)
        shutil.rmtree(dst_dir, ignore_errors=True)


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
        tmp_json = stack.enter_context(tempfile.NamedTemporaryFile(dir=tmp_dir, mode="w", suffix=".json"))  # noqa
        tmp_data = {"message": "fetch-file-request"}
        tmp_json.write(json.dumps(tmp_data))
        tmp_json.seek(0)
        tmp_name = os.path.split(tmp_json.name)[-1]
        tmp_http = "http://weaver.mock" + tmp_json.name
        tmp_retry = 2

        # share in below mocked_request, 'nonlocal' back compatible with Python 2
        tmp = {"retry": tmp_retry, "json": tmp_json, "http": tmp_http}

        def mocked_request(*_, **__):  # noqa: E811
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


def test_fetch_file_http_content_disposition_filename():
    tmp_dir = tempfile.gettempdir()
    with contextlib.ExitStack() as stack:
        tmp_json = stack.enter_context(tempfile.NamedTemporaryFile(dir=tmp_dir, mode="w", suffix=".json"))  # noqa
        tmp_data = {"message": "fetch-file-request"}
        tmp_text = json.dumps(tmp_data)
        tmp_json.write(tmp_text)
        tmp_json.seek(0)

        tmp_random = "123456"
        tmp_normal = "spécial.json"
        tmp_escape = quote(tmp_normal)  # % characters
        tmp_name = os.path.split(tmp_json.name)[-1]
        tmp_http = "http://weaver.mock/{}".format(tmp_random)  # pseudo endpoint where file name is not directly visible

        def mock_response(__request, test_headers):
            test_headers.update({
                "Content-Type": ContentType.APP_JSON,
                "Content-Length": str(len(tmp_text))
            })
            return 200, headers, tmp_text

        res_dir = os.path.join(tmp_dir, str(uuid.uuid4()))
        req_mock = stack.enter_context(responses.RequestsMock())
        try:
            make_dirs(res_dir, exist_ok=True)
            for target, headers in [
                (tmp_name, {
                    "Content-Disposition": f"attachment; filename=\"{tmp_name}\";filename*=UTF-8''{tmp_name}"
                }),
                (tmp_name, {  # unusual spacing/order does not matter
                    "Content-Disposition": f" filename*=UTF-8''{tmp_name};   filename=\"{tmp_name}\";attachment;"
                }),
                (tmp_name, {
                    "Content-Disposition": f"attachment; filename=\"{tmp_name}\""
                }),
                (tmp_name, {
                    "Content-Disposition": f"attachment; filename={tmp_name}"
                }),
                (tmp_normal, {
                    "Content-Disposition": f"attachment; filename=\"{tmp_normal}\";filename*=UTF-8''{tmp_escape}"
                }),
                (tmp_normal, {  # disallowed escape character in 'filename', but 'filename*' is valid and used first
                    "Content-Disposition": f"attachment; filename=\"{tmp_escape}\";filename*=UTF-8''{tmp_normal}"
                }),
                (tmp_random, {  # disallowed escape character in 'filename', reject since no alternative
                    "Content-Disposition": f"attachment; filename=\"{tmp_escape}\""
                }),
                (tmp_random, {  # empty header
                    "Content-Disposition": ""
                }),
                (tmp_random, {  # missing header
                }),
                (tmp_random, {  # missing filename
                    "Content-Disposition": "attachment"
                }),
                (tmp_random, {  # invalid filename
                    "Content-Disposition": "attachment; filename*=UTF-8''exec%20'echo%20test'"
                }),
                (tmp_random, {  # invalid encoding
                    "Content-Disposition": "attachment; filename*=random''%47%4F%4F%44.json"
                }),
                ("GOOD.json", {  # valid encoding and allowed characters after escape
                    "Content-Disposition": "attachment; filename*=UTF-8''%47%4F%4F%44.json"
                })
            ]:
                req_mock.remove("GET", tmp_http)  # reset previous iter
                req_mock.add_callback("GET", tmp_http, callback=lambda req: mock_response(req, headers))
                try:
                    res_path = fetch_file(tmp_http, res_dir)
                except Exception as exc:
                    raise AssertionError(f"Unexpected exception when testing with: [{headers}]. Exception: [{exc}]")
                assert res_path == os.path.join(res_dir, target), f"Not expected name when testing with: [{headers}]"
                assert os.path.isfile(res_path), f"File [{tmp_http}] should be accessible under [{res_path}]"
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


def test_get_any_value():
    assert get_any_value({}) is None
    assert get_any_value({}, default=null) is null
    assert get_any_value({}, default=1) == 1
    assert get_any_value({"data": 2}) == 2
    assert get_any_value({"data": 2}, default=1) == 2
    assert get_any_value({"data": 2}, data=False) is None
    assert get_any_value({"data": 2}, default=1, data=False) == 1
    assert get_any_value({"value": 2}) == 2
    assert get_any_value({"value": 2}, default=1) == 2
    assert get_any_value({"value": 2}, data=False) is None
    assert get_any_value({"value": 2}, default=1, data=False) == 1
    assert get_any_value({"href": "http://localhost/test.txt"}) == "http://localhost/test.txt"
    assert get_any_value({"href": "http://localhost/test.txt"}, default=1) == "http://localhost/test.txt"
    assert get_any_value({"href": "http://localhost/test.txt"}, file=False) is None
    assert get_any_value({"href": "http://localhost/test.txt"}, file=False, default=1) == 1
    assert get_any_value({"reference": "http://localhost/test.txt"}) == "http://localhost/test.txt"
    assert get_any_value({"reference": "http://localhost/test.txt"}, default=1) == "http://localhost/test.txt"
    assert get_any_value({"reference": "http://localhost/test.txt"}, file=False) is None
    assert get_any_value({"reference": "http://localhost/test.txt"}, file=False, default=1) == 1
    assert get_any_value({"file": "http://localhost/test.txt"}) is None
    assert get_any_value({"data": 1, "value": 2, "href": "http://localhost/test.txt"}, file=False, data=False) is None


def test_localize_datetime():
    dt_utc = datetime(2000, 10, 10, 6, 12, 50, tzinfo=pytz.timezone("UTC"))
    dt_utc_tz = localize_datetime(dt_utc)
    dt_gmt_tz = localize_datetime(dt_utc, "GMT")  # UTC-0
    dt_est_tz = localize_datetime(dt_utc, "EST")  # UTC-5
    assert dt_utc_tz.timetuple()[:6] == (2000, 10, 10, 6, 12, 50)
    assert dt_gmt_tz.timetuple()[:6] == (2000, 10, 10, 6, 12, 50)
    assert dt_est_tz.timetuple()[:6] == (2000, 10, 10, 1, 12, 50)
