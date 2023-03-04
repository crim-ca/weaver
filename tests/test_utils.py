# pylint: disable=C0103,invalid-name

import contextlib
import inspect
import itertools
import json
import os
import random
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import quote, urlparse

import mock
import pytest
import pytz
import responses
from beaker.cache import cache_region
from mypy_boto3_s3.literals import RegionName
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

from tests.utils import (
    MOCK_AWS_REGION,
    mocked_aws_config,
    mocked_aws_s3,
    mocked_aws_s3_bucket_test_file,
    mocked_file_response,
    mocked_file_server,
    setup_test_file_hierarchy
)
from weaver import xml_util
from weaver.execute import ExecuteControlOption, ExecuteMode
from weaver.formats import ContentType, repr_json
from weaver.status import JOB_STATUS_CATEGORIES, STATUS_PYWPS_IDS, STATUS_PYWPS_MAP, Status, StatusCompliant, map_status
from weaver.utils import (
    AWS_S3_BUCKET_REFERENCE_PATTERN,
    AWS_S3_REGIONS,
    NullType,
    OutputMethod,
    PathMatchingMethod,
    VersionLevel,
    apply_number_with_unit,
    assert_sane_name,
    bytes2str,
    fetch_directory,
    fetch_file,
    get_any_value,
    get_base_url,
    get_path_kvp,
    get_request_options,
    get_sane_name,
    get_secure_directory_name,
    get_ssl_verify_option,
    get_url_without_query,
    is_update_version,
    is_valid_url,
    localize_datetime,
    make_dirs,
    null,
    parse_kvp,
    parse_number_with_unit,
    parse_prefer_header_execute_mode,
    pass_http_error,
    request_extra,
    resolve_s3_from_http,
    resolve_s3_http_options,
    resolve_s3_reference,
    retry_on_condition,
    setup_cache,  # WARNING: make sure to reset after use since state is applied globally, could break other tests
    str2bytes,
    validate_s3,
    xml_path_elements,
    xml_strip_ns
)

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple, Type

    from responses import _Body as BodyType  # noqa: W0212

    from tests.utils import S3Scheme
    from weaver.typedefs import AnyRequestType, HeadersType

AWS_S3_REGION_SUBSET = set(random.choices(AWS_S3_REGIONS, k=4))
AWS_S3_REGION_SUBSET_WITH_MOCK = {MOCK_AWS_REGION} | AWS_S3_REGION_SUBSET
AWS_S3_REGION_NON_DEFAULT = list(AWS_S3_REGION_SUBSET_WITH_MOCK - {MOCK_AWS_REGION})[0]

# pylint: disable=R1732,W1514  # not using with open + encoding


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


def test_is_update_version():
    versions = [
        "0.1.2",
        "1.0.3",
        "1.2.0",
        "1.2.3",
        "1.2.4",
        "1.3.1",
    ]
    random.shuffle(versions)  # function must not depend on input order

    assert not is_update_version("0.1.0", versions, VersionLevel.PATCH)
    assert not is_update_version("1.0.1", versions, VersionLevel.PATCH)
    assert not is_update_version("1.2.1", versions, VersionLevel.PATCH)
    assert not is_update_version("1.2.3", versions, VersionLevel.PATCH)
    assert not is_update_version("1.3.0", versions, VersionLevel.PATCH)
    assert not is_update_version("1.3.1", versions, VersionLevel.PATCH)
    assert not is_update_version("1.4.5", versions, VersionLevel.PATCH)  # no 1.4.x to update from

    assert not is_update_version("0.1.0", versions, VersionLevel.MINOR)
    assert not is_update_version("0.1.4", versions, VersionLevel.MINOR)
    assert not is_update_version("1.2.5", versions, VersionLevel.MINOR)
    assert not is_update_version("1.3.2", versions, VersionLevel.MINOR)
    assert not is_update_version("2.0.0", versions, VersionLevel.MINOR)  # no 2.x to update from
    assert not is_update_version("2.1.3", versions, VersionLevel.MINOR)

    assert not is_update_version("0.1.0", versions, VersionLevel.MAJOR)
    assert not is_update_version("0.1.4", versions, VersionLevel.MAJOR)
    assert not is_update_version("0.2.0", versions, VersionLevel.MAJOR)
    assert not is_update_version("0.2.9", versions, VersionLevel.MAJOR)
    assert not is_update_version("1.2.5", versions, VersionLevel.MAJOR)
    assert not is_update_version("1.3.2", versions, VersionLevel.MAJOR)
    assert not is_update_version("1.4.0", versions, VersionLevel.MAJOR)

    assert is_update_version("0.1.3", versions, VersionLevel.PATCH)
    assert is_update_version("1.2.5", versions, VersionLevel.PATCH)
    assert is_update_version("1.3.2", versions, VersionLevel.PATCH)

    assert is_update_version("0.2.0", versions, VersionLevel.MINOR)
    assert is_update_version("0.2.1", versions, VersionLevel.MINOR)
    assert is_update_version("0.3.0", versions, VersionLevel.MINOR)
    assert is_update_version("1.4.0", versions, VersionLevel.MINOR)
    assert is_update_version("1.5.0", versions, VersionLevel.MINOR)

    assert is_update_version("2.0.0", versions, VersionLevel.MAJOR)
    assert is_update_version("2.1.3", versions, VersionLevel.MAJOR)


def test_get_url_without_query():
    url_h = "http://some-host.com/wps"
    url_q = f"{url_h}?service=WPS"
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
            f"Process{status_value.capitalize()}"]


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
    # pylint: disable=W1406,redundant-u-string-prefix  # left for readability
    assert str2bytes(b"test-bytes") == b"test-bytes"
    assert str2bytes(u"test-unicode") == b"test-unicode"


def test_bytes2str():
    # pylint: disable=W1406,redundant-u-string-prefix  # left for readability
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
        url = f"{any_wps_url}?{queries}"
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

    with mock.patch("weaver.utils.get_settings", return_value={"cache.request.enabled": "false"}):
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

    with mock.patch("weaver.utils.get_settings", return_value={"cache.request.enabled": "false"}):
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


@pytest.mark.parametrize("cache_enabled", [False, True])
def test_request_extra_cache_requests_applied(cache_enabled):
    def mock_request(*_, **__):
        mocked_resp = Response()
        mocked_resp.status_code = HTTPOk.code
        return mocked_resp

    try:
        cache_settings = {"cache.request.enabled": str(cache_enabled)}
        with mock.patch("weaver.utils.get_settings", return_value=cache_settings):
            setup_cache(cache_settings)
            with mock.patch("requests.Session.request", side_effect=mock_request) as mocked_request:
                resp = request_extra("GET", "https://valid.com")
                assert resp.status_code == HTTPOk.code
                assert mocked_request.called
                resp = request_extra("GET", "https://valid.com")
                assert resp.status_code == HTTPOk.code
                assert mocked_request.call_count == 1 if cache_enabled else 2
    finally:
        setup_cache({})  # ensure reset since globally applied


@pytest.mark.parametrize("cache_enabled", [False, True])
def test_request_extra_cache_non_default_func(cache_enabled):
    test_region = "result"
    test_called = [0]

    @cache_region(test_region)
    def mock_request(*args):
        test_called[0] += 1
        mocked_resp = Response()
        mocked_resp.status_code = HTTPOk.code
        return mocked_resp

    try:
        cache_settings = {f"cache.{test_region}.enabled": str(cache_enabled)}
        with mock.patch("weaver.utils.get_settings", return_value=cache_settings):
            setup_cache(cache_settings)
            with mock.patch("requests.Session.request", side_effect=mock_request) as mocked_request:
                resp = request_extra("GET", "https://valid.com", cache_request=mock_request)
                assert resp.status_code == HTTPOk.code
                assert test_called[0]
                assert not mocked_request.called
                resp = request_extra("GET", "https://valid.com", cache_request=mock_request)
                assert resp.status_code == HTTPOk.code
                assert test_called[0] == 1 if cache_enabled else 2
                assert not mocked_request.called
    finally:
        setup_cache({})  # ensure reset since globally applied


@pytest.mark.parametrize(
    "location,expected",
    [
        ("https://mocked-file-server.com/dir/", "dir"),
        ("https://mocked-file-server.com/dir/sub/", "sub"),
        ("https://mocked-file-server.com/dir/../", "dir"),
        ("https://mocked-file-server.com/dir/../../", "dir"),
        ("https://mocked-file-server.com/../", "mocked-file-server.com",)
    ]
)
def test_get_secure_directory_name(location, expected):
    result = get_secure_directory_name(location)
    assert result == expected


def test_get_secure_directory_name_uuid():
    invalid_location = "/../../"
    fake_uuid = "fe9c497e-811f-4bf8-b1a8-63005cea8e99"

    def mock_uuid():
        return fake_uuid

    with mock.patch("uuid.uuid4", side_effect=mock_uuid):
        result = get_secure_directory_name(invalid_location)
        assert result == fake_uuid


@pytest.mark.parametrize(
    "include_dir_heading,include_separators,include_code_format,include_table_format,include_modified_date",
    itertools.product((True, False), repeat=5)
)
def test_fetch_directory_html(include_dir_heading,       # type: bool
                              include_separators,        # type: bool
                              include_code_format,       # type: bool
                              include_table_format,      # type: bool
                              include_modified_date,     # type: bool
                              ):                         # type: (...) -> None
    with contextlib.ExitStack() as stack:
        tmp_host = "https://mocked-file-server.com"  # must match in 'Execute_WorkflowSelectCopyNestedOutDir.json'
        tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
        stack.enter_context(mocked_file_server(
            tmp_dir, tmp_host,
            settings={},
            mock_browse_index=True,
            include_dir_heading=include_dir_heading,
            include_separators=include_separators,
            include_code_format=include_code_format,
            include_table_format=include_table_format,
            include_modified_date=include_modified_date,
        ))
        test_http_dir_files = [
            "main.txt",
            "dir/file.txt",
            "dir/sub/file.tmp",
            "dir/sub/nested/file.cfg",
            "dir/other/meta.txt",
            "another/info.txt",
            "another/nested/data.txt",
        ]
        test_dir_files = setup_test_file_hierarchy(test_http_dir_files, tmp_dir)

        out_dir = stack.enter_context(tempfile.TemporaryDirectory())
        out_files = fetch_directory(f"{tmp_host}/dir/", out_dir)
        expect_files = filter(lambda _f: _f.startswith("dir/"), test_http_dir_files)
        expect_files = [os.path.join(out_dir, file) for file in expect_files]
        assert list(out_files) == sorted(expect_files), (
            f"Out dir: [{out_dir}], Test dir:\n{repr_json(test_dir_files, indent=2)}"
        )


def test_fetch_directory_host_html():
    with contextlib.ExitStack() as stack:
        tmp_host = "https://mocked-file-server.com"  # must match in 'Execute_WorkflowSelectCopyNestedOutDir.json'
        tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
        stack.enter_context(mocked_file_server(tmp_dir, tmp_host, settings={}, mock_browse_index=True))
        test_http_dir_files = [
            "main.txt",
            "dir/file.txt",
            "dir/sub/file.tmp",
            "dir/sub/nested/file.cfg",
            "dir/other/meta.txt",
            "another/info.txt",
            "another/nested/data.txt",
        ]
        test_dir_files = setup_test_file_hierarchy(test_http_dir_files, tmp_dir)
        out_dir = stack.enter_context(tempfile.TemporaryDirectory())
        out_files = fetch_directory(f"{tmp_host}/", out_dir)
        expect_files = [os.path.join(out_dir, f"mocked-file-server.com/{file}") for file in test_http_dir_files]
        assert list(out_files) == sorted(expect_files), (
            f"Out dir: [{out_dir}], Test dir:\n{repr_json(test_dir_files, indent=2)}"
        )


def test_fetch_directory_json():
    with contextlib.ExitStack() as stack:
        tmp_host = "https://mocked-file-server.com"
        tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
        test_http_dir_files = [
            "main.txt",
            "dir/file.txt",
            "dir/sub/file.tmp",
            "dir/sub/nested/file.cfg",
            "dir/other/meta.txt",
            "another/info.txt",
            "another/nested/data.txt",
        ]
        test_dir_files = setup_test_file_hierarchy(test_http_dir_files, tmp_dir)

        def mock_json_dir(request):
            # type: (AnyRequestType) -> Tuple[int, HeadersType, BodyType]
            _dir = request.path_url.split("?")[0].lstrip("/")
            _files = [
                os.path.join(tmp_host, _file)
                for _file in test_http_dir_files
                if _file.startswith(_dir)
            ]
            return 200, {"Content-Type": ContentType.APP_JSON}, json.dumps(_files)

        req_mock = responses.RequestsMock(assert_all_requests_are_fired=False)
        req_mock.add_callback(responses.GET, f"{tmp_host}/dir/?f=json", callback=mock_json_dir)
        stack.enter_context(mocked_file_server(
            tmp_dir, tmp_host,
            settings={},
            mock_browse_index=True,
            requests_mock=req_mock,
        ))

        out_dir = stack.enter_context(tempfile.TemporaryDirectory())
        out_files = fetch_directory(f"{tmp_host}/dir/?f=json", out_dir)
        expect_files = filter(lambda _f: _f.startswith("dir/"), test_http_dir_files)
        expect_files = [os.path.join(out_dir, file) for file in expect_files]
        assert list(out_files) == sorted(expect_files), (
            f"Out dir: [{out_dir}], Test dir:\n{repr_json(test_dir_files, indent=2)}"
        )


@pytest.mark.parametrize("invalid_json_listing", [
    {},
    [],
    {"file": "https://somewhere.com/test.txt"},
    [{"file": "https://somewhere.com/test.txt"}],
])
def test_fetch_directory_json_invalid_listing(invalid_json_listing):
    with contextlib.ExitStack() as stack:
        tmp_host = "https://mocked-file-server.com"
        tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())

        def mock_json_dir(__request):
            # type: (AnyRequestType) -> Tuple[int, HeadersType, BodyType]
            return 200, {"Content-Type": ContentType.APP_JSON}, json.dumps(invalid_json_listing)

        req_mock = responses.RequestsMock(assert_all_requests_are_fired=False)
        req_mock.add_callback(responses.GET, f"{tmp_host}/dir/?f=json", callback=mock_json_dir)
        stack.enter_context(mocked_file_server(
            tmp_dir, tmp_host,
            settings={},
            mock_browse_index=True,
            requests_mock=req_mock,
        ))
        out_dir = stack.enter_context(tempfile.TemporaryDirectory())

        with pytest.raises(ValueError):  # error expected since JSON response is not a list of files
            fetch_directory(f"{tmp_host}/dir/?f=json", out_dir)


class TemporaryLinkableDirectory(tempfile.TemporaryDirectory):
    # avoids error in case the temp dir was replaced by a link
    def cleanup(self) -> None:
        try:
            super(TemporaryLinkableDirectory, self).cleanup()
        except OSError:
            if not os.path.islink(self.name):
                raise
            os.remove(self.name)


# expect_files[i] = (Path, IsLink)
@pytest.mark.parametrize("listing_dir,out_method,include,exclude,matcher,expect_files", [
    ("dir/", OutputMethod.LINK, None, None, PathMatchingMethod.REGEX, [
        ("dir/", True),
        ("dir/file.txt", False),
        ("dir/sub/file.tmp", False),
        ("dir/sub/nested/file.cfg", False),
        ("dir/other/meta.txt", False),
        ("dir/other/link.lnk", True),
    ]),
    ("dir/", OutputMethod.COPY, None, None, PathMatchingMethod.REGEX, [
        ("dir/", False),
        ("dir/file.txt", False),
        ("dir/sub/file.tmp", False),
        ("dir/sub/nested/file.cfg", False),
        ("dir/other/meta.txt", False),
        ("dir/other/link.lnk", False),
    ]),
    ("dir/", OutputMethod.MOVE, None, None, PathMatchingMethod.REGEX, [
        ("dir/", False),
        ("dir/file.txt", False),
        ("dir/sub/file.tmp", False),
        ("dir/sub/nested/file.cfg", False),
        ("dir/other/meta.txt", False),
        ("dir/other/link.lnk", True),
    ]),
    ("dir/", OutputMethod.AUTO, None, None, PathMatchingMethod.REGEX, [
        ("dir/", False),
        ("dir/file.txt", False),
        ("dir/sub/file.tmp", False),
        ("dir/sub/nested/file.cfg", False),
        ("dir/other/meta.txt", False),
        ("dir/other/link.lnk", True),
    ]),
    ("another/", OutputMethod.LINK, None, None, PathMatchingMethod.REGEX, [
        ("another/", True),
        ("another/info.txt", False),
        ("another/nested/data.txt", False),
        ("another/nested/link.txt", True),
        ("another/link-dir/", True),
        ("another/link-dir/file.txt", False),
        ("another/link-dir/sub/file.tmp", False),
        ("another/link-dir/sub/nested/file.cfg", False),
        ("another/link-dir/other/meta.txt", False),
        ("another/link-dir/other/link.lnk", True),
    ]),
    ("another/", OutputMethod.COPY, None, None, PathMatchingMethod.REGEX, [
        ("another/", False),
        ("another/info.txt", False),
        ("another/nested/data.txt", False),
        ("another/nested/link.txt", False),
        ("another/link-dir/", False),
        ("another/link-dir/file.txt", False),
        ("another/link-dir/sub/file.tmp", False),
        ("another/link-dir/sub/nested/file.cfg", False),
        ("another/link-dir/other/meta.txt", False),
        ("another/link-dir/other/link.lnk", False),
    ]),
    ("another/", OutputMethod.MOVE, None, None, PathMatchingMethod.REGEX, [
        ("another/", False),
        ("another/info.txt", False),
        ("another/nested/data.txt", False),
        ("another/nested/link.txt", True),
        ("another/link-dir/", True),
        ("another/link-dir/file.txt", False),
        ("another/link-dir/sub/file.tmp", False),
        ("another/link-dir/sub/nested/file.cfg", False),
        ("another/link-dir/other/meta.txt", False),
        ("another/link-dir/other/link.lnk", True),
    ]),
    ("another/", OutputMethod.AUTO, None, None, PathMatchingMethod.REGEX, [
        ("another/", False),
        ("another/info.txt", False),
        ("another/nested/data.txt", False),
        ("another/nested/link.txt", True),
        ("another/link-dir/", True),
        ("another/link-dir/file.txt", False),
        ("another/link-dir/sub/file.tmp", False),
        ("another/link-dir/sub/nested/file.cfg", False),
        ("another/link-dir/other/meta.txt", False),
        ("another/link-dir/other/link.lnk", True),
    ]),
    ("link/", OutputMethod.LINK, None, None, PathMatchingMethod.REGEX, [
        ("link/", True),
        ("link/another/", True),
        ("link/another/info.txt", False),
        ("link/another/nested/data.txt", False),
        ("link/another/nested/link.txt", True),
        ("link/another/link-dir/", True),
        ("link/another/link-dir/file.txt", False),
        ("link/another/link-dir/sub/file.tmp", False),
        ("link/another/link-dir/sub/nested/file.cfg", False),
        ("link/another/link-dir/other/meta.txt", False),
        ("link/another/link-dir/other/link.lnk", True),
    ]),
    ("link/", OutputMethod.COPY, None, None, PathMatchingMethod.REGEX, [
        ("link/", False),
        ("link/another/", False),
        ("link/another/info.txt", False),
        ("link/another/nested/data.txt", False),
        ("link/another/nested/link.txt", False),
        ("link/another/link-dir/", False),
        ("link/another/link-dir/file.txt", False),
        ("link/another/link-dir/sub/file.tmp", False),
        ("link/another/link-dir/sub/nested/file.cfg", False),
        ("link/another/link-dir/other/meta.txt", False),
        ("link/another/link-dir/other/link.lnk", False),
    ]),
    ("link/", OutputMethod.MOVE, None, None, PathMatchingMethod.REGEX, [
        ("link/", False),
        ("link/another/", True),
        ("link/another/info.txt", False),
        ("link/another/nested/data.txt", False),
        ("link/another/nested/link.txt", True),
        ("link/another/link-dir/", True),
        ("link/another/link-dir/file.txt", False),
        ("link/another/link-dir/sub/file.tmp", False),
        ("link/another/link-dir/sub/nested/file.cfg", False),
        ("link/another/link-dir/other/meta.txt", False),
        ("link/another/link-dir/other/link.lnk", True),
    ]),
    ("link/", OutputMethod.AUTO, None, None, PathMatchingMethod.REGEX, [
        ("link/", False),
        ("link/another/", True),
        ("link/another/info.txt", False),
        ("link/another/nested/data.txt", False),
        ("link/another/nested/link.txt", True),
        ("link/another/link-dir/", True),
        ("link/another/link-dir/file.txt", False),
        ("link/another/link-dir/sub/file.tmp", False),
        ("link/another/link-dir/sub/nested/file.cfg", False),
        ("link/another/link-dir/other/meta.txt", False),
        ("link/another/link-dir/other/link.lnk", True),
    ]),
])
def test_fetch_directory_local(listing_dir,     # type: str
                               out_method,      # type: OutputMethod
                               include,         # type: Optional[List[str]]
                               exclude,         # type: Optional[List[str]]
                               matcher,         # type: PathMatchingMethod
                               expect_files,    # type: List[Tuple[str, bool]]
                               ):               # type: (...) -> None
    with contextlib.ExitStack() as stack:
        tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
        test_dir_files = [
            ("main.txt", None),
            ("dir/file.txt", None),
            ("dir/sub/file.tmp", None),
            ("dir/sub/nested/file.cfg", None),
            ("dir/other/meta.txt", None),
            ("dir/other/link.lnk", "main.txt"),
            ("another/info.txt", None),
            ("another/nested/data.txt", None),
            ("another/nested/link.txt", "dir/file.txt"),
            ("another/link-dir/", "dir/"),
            ("link/another/", "another/"),
        ]
        test_dir_files = setup_test_file_hierarchy(test_dir_files, tmp_dir)

        # test
        out_dir = stack.enter_context(TemporaryLinkableDirectory())  # must exist, but can be replaced by link if needed
        out_files = fetch_directory(f"file://{tmp_dir}/{listing_dir}", out_dir,
                                    out_method=out_method, include=include, exclude=exclude, matcher=matcher)
        out_files = [(out, os.path.islink(out)) for out in out_files]
        # get dirs only for link checks, they are not expected from output listing
        expect_dirs = [path for path in expect_files if path[0].endswith("/")]
        # add the original relative dirs without the out dir path adjustment to help debug/compare results,
        # since the requested sub-dir location will not be nested as the input anymore (subset is extracted)
        expect_dirs = [(os.path.join(out_dir, path[0].split("/", 1)[-1]), path[1], path[0]) for path in expect_dirs]
        expect_files = [file for file in expect_files if not file[0].endswith("/")]
        expect_files = [(os.path.join(out_dir, file[0].split("/", 1)[-1]), file[1]) for file in expect_files]
        assert list(out_files) == sorted(expect_files), (
            f"Out dir: [{out_dir}], Test dir:\n{repr_json(test_dir_files, indent=2)}"
        )
        out_dirs = [(path[0], os.path.islink(path[0].rstrip("/")), path[2]) for path in expect_dirs]
        assert out_dirs == expect_dirs, f"Out dir: [{out_dir}], Test dir:\n{repr_json(test_dir_files, indent=2)}"


@pytest.mark.parametrize("listing_dir,include,exclude,matcher,expect_files", [
    ("dir/", None, None, PathMatchingMethod.REGEX, [
        "dir/file.txt",
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
        "dir/other/meta.txt",
    ]),
    ("dir/", None, [r".*/.*\.txt"], PathMatchingMethod.REGEX, [
        # 'dir/file.txt' becomes 'file.txt' (at root of out-dir) after resolution with 'dir/' listing
        # since the exclude pattern has a '/' in it, it is not matched with relative path resolution
        "dir/file.txt",
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
    ]),
    ("dir/", None, [r"*/*.txt"], PathMatchingMethod.GLOB, [
        # 'dir/file.txt' becomes 'file.txt' (at root of out-dir) after resolution with 'dir/' listing
        # since the exclude pattern has a '/' in it, it is not matched with relative path resolution
        "dir/file.txt",
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
    ]),
    ("dir/", None, [r".*\.txt"], PathMatchingMethod.REGEX, [
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
    ]),
    ("dir/", None, [r"*.txt"], PathMatchingMethod.GLOB, [
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
    ]),
    ("dir/", [r".*/.*\.txt"], None, PathMatchingMethod.REGEX, [
        # adding include does not 'force' only those to be matched, only to "add back" excluded
        "dir/file.txt",
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
        "dir/other/meta.txt",
    ]),
    ("dir/", [r"*/*.txt"], None, PathMatchingMethod.GLOB, [
        # adding include does not 'force' only those to be matched, only to "add back" excluded
        "dir/file.txt",
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
        "dir/other/meta.txt",
    ]),
    ("dir/", [r".*\.txt"], None, PathMatchingMethod.REGEX, [
        "dir/file.txt",
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
        "dir/other/meta.txt",
    ]),
    ("dir/", [r"*.txt"], None, PathMatchingMethod.GLOB, [
        "dir/file.txt",
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
        "dir/other/meta.txt",
    ]),
    ("dir/", [r".*file\.txt"], [r".*\.txt"], PathMatchingMethod.REGEX, [
        "dir/file.txt",  # initially excluded, but the added back due to include
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
    ]),
    ("dir/", [r"*file.txt"], [r"*.txt"], PathMatchingMethod.GLOB, [
        "dir/file.txt",  # initially excluded, but the added back due to include
        "dir/sub/file.tmp",
        "dir/sub/nested/file.cfg",
    ]),
    ("", None, [r"dir/.*", r".*info\..*"], PathMatchingMethod.REGEX, [
        "main.txt",
        "another/nested/data.txt",
    ]),
    ("", None, [r"dir/*", r"*info.*"], PathMatchingMethod.GLOB, [
        "main.txt",
        "another/nested/data.txt",
    ]),
])
def test_fetch_directory_filters(listing_dir, include, exclude, matcher, expect_files):
    # type: (str, Optional[List[str]], Optional[List[str]], PathMatchingMethod, List[str]) -> None
    with contextlib.ExitStack() as stack:
        tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
        test_dir_files = [
            "main.txt",
            "dir/file.txt",
            "dir/sub/file.tmp",
            "dir/sub/nested/file.cfg",
            "dir/other/meta.txt",
            "another/info.txt",
            "another/nested/data.txt",
        ]
        test_dir_files = setup_test_file_hierarchy(test_dir_files, tmp_dir)

        out_dir = stack.enter_context(tempfile.TemporaryDirectory())
        out_files = fetch_directory(f"file://{tmp_dir}/{listing_dir}", out_dir,
                                    include=include, exclude=exclude, matcher=matcher)
        expect_files = [os.path.join(out_dir, file.split("/", 1)[-1] if listing_dir else file) for file in expect_files]
        assert list(out_files) == sorted(expect_files), (
            f"Out dir: [{out_dir}], Test dir:\n{repr_json(test_dir_files, indent=2)}"
        )


def test_fetch_directory_raise_missing_trailing_slash():
    with tempfile.TemporaryDirectory() as tmp_dir:  # make sure missing dir is not the error
        with pytest.raises(ValueError):
            fetch_directory(f"file://{tmp_dir}", "/tmp")  # input location with no trailing slash


def test_fetch_directory_unknown_scheme():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError):
            fetch_directory("unknown://random.location.com/dir/", tmpdir)


def test_fetch_directory_unknown_content_type():
    dir_http = "https://random.location.com/dir/"
    req_mock = responses.RequestsMock(assert_all_requests_are_fired=False)
    req_mock.add_callback(responses.GET, dir_http, callback=lambda _: (200, {"Content-Type": "application/random"}, ""))
    with req_mock:
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError):
                fetch_directory("https://random.location.com/dir/", tmpdir)


@pytest.mark.parametrize("source_link, out_method, result_link", [
    (False, OutputMethod.LINK, True),
    (False, OutputMethod.COPY, False),
    (False, OutputMethod.MOVE, False),
    (False, OutputMethod.AUTO, False),
    (True, OutputMethod.LINK, True),
    (True, OutputMethod.COPY, False),
    (True, OutputMethod.MOVE, False),
    (True, OutputMethod.AUTO, True),
])
def test_fetch_file_local_links(source_link, out_method, result_link):
    # type: (bool, OutputMethod, bool) -> None
    """
    Test handling of symbolic links by function :func:`weaver.utils.fetch_file` for local files.

    .. note::
        Because :attr:`OutputMethod.MOVE` is expected to "remove" the original temporary file, an :class:`OSError` is
        generated when :func:`tempfile.NamedTemporaryFile` attempts to delete it when closed on ``with`` exit, since
        it does not exist anymore (it was moved). Avoid the error by manually performing any necessary cleanup.
    """
    tmp_file = None
    tmp_dir = tempfile.gettempdir()
    src_dir = os.path.join(tmp_dir, str(uuid.uuid4()))
    dst_dir = os.path.join(tmp_dir, str(uuid.uuid4()))
    try:
        make_dirs(src_dir, exist_ok=True)
        make_dirs(dst_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=src_dir, mode="w", suffix=".json", delete=False) as tmp_json:
            tmp_data = {"message": "fetch-file-link"}
            tmp_json.write(json.dumps(tmp_data))
            tmp_json.seek(0)
            tmp_file = tmp_json.name
            tmp_path, tmp_name = os.path.split(tmp_file)
            tmp_link = os.path.join(tmp_path, "link.json")
            os.symlink(tmp_file, tmp_link)
            dst_path = os.path.join(dst_dir, tmp_name)
            src_path = tmp_link if source_link else tmp_file
            if os.path.exists(dst_path):
                os.remove(dst_path)
            fetch_file(src_path, dst_dir, out_method=out_method)
            assert os.path.isfile(dst_path), (
                f"File [{tmp_file}] should be accessible under [{dst_path}]. "
                f"Failed with: {(src_path, out_method, result_link)}"
            )
            if result_link:
                assert os.path.islink(dst_path), "Result is not a link when it is expected to be one."
            else:
                assert not os.path.islink(dst_path), "Result is a link when it is expected not to be one."
            exists = os.path.exists(src_path)
            assert not exists if out_method == OutputMethod.MOVE else exists
            with open(dst_path, mode="r", encoding="utf-8") as dst_file:
                dst_data = json.load(dst_file)
            assert dst_data == tmp_data, "File should be properly copied/referenced from original"
    except OSError as exc:
        pytest.fail(f"Unexpected error raised during test: [{exc!s}]")
    finally:
        shutil.rmtree(src_dir, ignore_errors=True)
        shutil.rmtree(dst_dir, ignore_errors=True)
        if tmp_file and os.path.isfile(tmp_file) or os.path.islink(tmp_file):
            os.remove(tmp_file)


@pytest.mark.parametrize("protocol", ["", "file://"])
def test_fetch_file_local_with_protocol(protocol):
    # type: (str) -> None
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
            tmp_path = protocol + tmp_json.name
            fetch_file(tmp_path, res_dir)
            assert os.path.isfile(res_path), f"File [{tmp_path}] should be accessible under [{res_path}]"
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
        tmp_http = f"http://weaver.mock{tmp_json.name}"
        tmp_retry = 2

        # share in below mocked_request, 'nonlocal' back compatible with Python 2
        tmp = {"retry": tmp_retry, "json": tmp_json, "http": tmp_http}

        def mocked_request(*_, **__):
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
            assert os.path.isfile(res_path), f"File [{tmp_http}] should be accessible under [{res_path}]"
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
        tmp_default = f"{tmp_random}.json"
        tmp_txt_ext = f"{tmp_random}.txt"
        tmp_normal = "spécial.json"
        tmp_escape = quote(tmp_normal)  # % characters
        tmp_ascii = "special.json"
        tmp_file = os.path.split(tmp_json.name)[-1]
        tmp_name, tmp_ext = tmp_file.rsplit(".", 1)
        tmp_http = f"http://weaver.mock/{tmp_random}"  # pseudo endpoint where file name is not directly visible

        def mock_response(__request, test_headers):
            # type: (AnyRequestType, HeadersType) -> Tuple[int, HeadersType, str]
            test_headers["Content-Length"] = str(len(tmp_text))
            test_headers.setdefault("Content-Type", ContentType.APP_JSON)
            return 200, headers, tmp_text

        res_dir = os.path.join(tmp_dir, str(uuid.uuid4()))
        req_mock = stack.enter_context(responses.RequestsMock())
        try:
            make_dirs(res_dir, exist_ok=True)
            for i, (target, headers) in enumerate([
                (tmp_file, {
                    "Content-Disposition": f"attachment; filename=\"{tmp_file}\";filename*=UTF-8''{tmp_file}"
                }),
                (tmp_file, {  # unusual spacing/order does not matter
                    "Content-Disposition": f" filename*=UTF-8''{tmp_file};   filename=\"{tmp_file}\";attachment;"
                }),
                (tmp_file, {
                    "Content-Disposition": f"attachment; filename=\"{tmp_file}\""
                }),
                (tmp_file, {
                    "Content-Disposition": f"attachment; filename={tmp_file}"
                }),
                # Special cases where 'werkzeug.utils.secure_filename' called within the fetch function
                # normally drops any leading or trailing underscores, although they are perfectly valid.
                # Tests would sporadically fail if not added explicitly depending on whether the temporary
                # file created by 'tempfile.NamedTemporaryFile' used a name with trailing underscore or not.
                (f"{tmp_name}_.{tmp_ext}", {
                    "Content-Disposition": f"attachment; filename={tmp_name}_.{tmp_ext}"
                }),
                (f"_{tmp_name}.{tmp_ext}", {
                    "Content-Disposition": f"attachment; filename=_{tmp_name}.{tmp_ext}"
                }),
                (f"__{tmp_name}__.{tmp_ext}", {
                    "Content-Disposition": f"attachment; filename=__{tmp_name}__.{tmp_ext}"
                }),
                (tmp_ascii, {  # valid character, but normalized UTF-8 into ASCII equivalent (e.g.: no accent)
                    "Content-Disposition": f"attachment; filename=\"{tmp_normal}\";filename*=UTF-8''{tmp_escape}"
                }),
                (tmp_ascii, {  # disallowed escape character in 'filename', but 'filename*' is valid and used first
                    "Content-Disposition": f"attachment; filename=\"{tmp_escape}\";filename*=UTF-8''{tmp_normal}"
                }),
                (tmp_ascii, {  # disallowed escape character in 'filename' (ASCII-only), reject since no alternative
                    "Content-Disposition": f"attachment; filename=\"{tmp_normal}\""
                }),
                (tmp_default, {  # disallowed escape character in 'filename' (ASCII-only), reject since no alternative
                    "Content-Disposition": f"attachment; filename=\"{tmp_escape}\""
                }),
                (tmp_default, {  # disallowed character
                    "Content-Disposition": "attachment; filename*=UTF-8''火"
                }),
                ("fire.txt", {
                    "Content-Disposition": "attachment; filename=\"fire.txt\"; filename*=UTF-8''火.txt"
                }),
                (tmp_txt_ext, {  # disallowed character and missing extension, but use extension by content-type
                    "Content-Type": ContentType.TEXT_PLAIN,
                    "Content-Disposition": "attachment; filename=\"fire\"; filename*=UTF-8''火"
                }),
                (tmp_default, {  # disallowed character and missing extension even if partial characters allowed
                    "Content-Disposition": "attachment; filename*=UTF-8''large_火"
                }),
                (tmp_default, {  # disallowed character
                    "Content-Disposition": "attachment; filename*=UTF-8''large_火.txt"
                }),
                (tmp_txt_ext, {  # disallowed character and missing extension even if partial characters allowed
                    "Content-Type": ContentType.TEXT_PLAIN,
                    "Content-Disposition": "attachment; filename*=UTF-8''large_火"
                }),
                (tmp_txt_ext, {  # disallowed character
                    "Content-Type": ContentType.TEXT_PLAIN,
                    "Content-Disposition": "attachment; filename*=UTF-8''large_火.txt"
                }),
                (tmp_default, {  # disallowed character
                    "Content-Disposition": f"attachment; filename=\"{quote('火')}\""
                }),
                (tmp_default, {  # disallowed character
                    "Content-Disposition": f"attachment; filename=\"{quote('火')}.txt\""
                }),
                (tmp_default, {  # disallowed character
                    "Content-Disposition": f"attachment; filename=\"large_{quote('火')}.txt\""
                }),
                (tmp_default, {  # disallowed character
                    "Content-Type": ContentType.APP_JSON,
                    "Content-Disposition": "attachment; filename=\"large_火\""
                }),
                (tmp_default, {  # valid characters, but missing extension
                    "Content-Type": ContentType.APP_JSON,
                    "Content-Disposition": "attachment; filename=\"simple\""
                }),
                (tmp_default, {  # valid characters, but missing extension
                    "Content-Type": ContentType.APP_JSON,
                    "Content-Disposition": "attachment; filename=UTF-8''simple"
                }),
                (tmp_default, {  # valid characters, but missing extension
                    "Content-Type": ContentType.APP_JSON,
                    "Content-Disposition": "attachment; filename=\"simple\"; filename=UTF-8''simple"
                }),
                ("simple.txt", {  # valid characters, extension takes precedence over content-type
                    "Content-Type": ContentType.APP_JSON,
                    "Content-Disposition": "attachment; filename=\"simple.txt\""
                }),
                (tmp_default, {  # empty header
                    "Content-Disposition": ""
                }),
                (tmp_default, {  # missing header
                }),
                (tmp_default, {  # missing filename
                    "Content-Disposition": "attachment"
                }),
                (tmp_default, {  # invalid filename
                    "Content-Disposition": "attachment; filename*=UTF-8''exec%20'echo%20test'"
                }),
                (tmp_default, {  # invalid encoding
                    "Content-Disposition": "attachment; filename*=random''%47%4F%4F%44.json"
                }),
                ("GOOD.json", {  # valid encoding and allowed characters after escape
                    "Content-Disposition": "attachment; filename*=UTF-8''%47%4F%4F%44.json"
                })
            ]):
                req_mock.remove("GET", tmp_http)  # reset previous iter
                req_mock.add_callback("GET", tmp_http, callback=lambda req: mock_response(req, headers))
                try:
                    res_path = fetch_file(tmp_http, res_dir)
                except Exception as exc:
                    raise AssertionError(f"Unexpected exception for test [{i}] with: [{headers}]. Exception: [{exc}]")
                assert res_path == os.path.join(res_dir, target), f"Not expected name for test [{i}] with: [{headers}]"
                assert os.path.isfile(res_path), f"File [{tmp_http}] should be accessible under [{res_path}]"
                assert json.load(open(res_path)) == tmp_data, "File should be properly generated from HTTP reference"
        except Exception:
            raise
        finally:
            shutil.rmtree(res_dir, ignore_errors=True)


@mocked_aws_config
@mocked_aws_s3
@pytest.mark.parametrize("s3_scheme, s3_region", [
    ("s3", "ca-central-1"),
    ("s3", "us-east-2"),
    ("s3", "eu-west-1"),
    ("https", "ca-central-1"),
    ("https", "us-east-2"),
    ("https", "eu-west-1"),
])
def test_fetch_file_remote_s3_bucket(s3_scheme, s3_region):
    # type: (S3Scheme, RegionName) -> None
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file_name = "test-file.txt"
        test_file_data = "dummy file"
        test_bucket_name = "test-fake-bucket"
        test_bucket_ref = mocked_aws_s3_bucket_test_file(
            test_bucket_name, test_file_name, test_file_data,
            s3_region=s3_region, s3_scheme=s3_scheme
        )
        result = fetch_file(test_bucket_ref, tmpdir)
        assert result == os.path.join(tmpdir, test_file_name)
        assert os.path.isfile(result)
        with open(result, mode="r") as test_file:
            assert test_file.read() == test_file_data


def test_fetch_file_unknown_scheme():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError):
            fetch_file("unknown://random.location.com/dir/file.txt", tmpdir)


@pytest.mark.parametrize("options, parameters, configuration", [
    (
        {"timeout": 10},
        {},
        {"connect_timeout": 10, "read_timeout": 10},
    ),
    (
        {"timeout": 10, "connect_timeout": 5},
        {},
        {"connect_timeout": 5, "read_timeout": 10},
    ),
    (
        {"timeout": 10, "read_timeout": 5},
        {},
        {"connect_timeout": 10, "read_timeout": 5},
    ),
    (
        {"timeout": 10, "connect_timeout": 5, "read_timeout": 20, "retries": 3},
        {},
        {"connect_timeout": 5, "read_timeout": 20, "retries": {"max_attempts": 3}},
    ),
    (
        {"retry": 5},  # alt name
        {},
        {"retries": {"max_attempts": 5}},
    ),
    (
        {"max_retries": 2},  # alt name
        {},
        {"retries": {"max_attempts": 2}},
    ),
    (
        {"cert": "some.crt", "verify": True},
        {"verify": True},
        {"client_cert": "some.crt"},
    ),
    (
        {"cert": ("some.crt", "some.pem")},
        {},
        {"client_cert": ("some.crt", "some.pem")},
    ),
    (
        {"cert": None, "verify": False},
        {"verify": False},
        {"client_cert": None},
    ),
    (
        {"headers": {"Content-Type": "ignore", "user-agent": "test"}},
        {},
        {"user_agent": "test"},
    )
])
def test_resolve_s3_http_options(options, parameters, configuration):
    # type: (Dict[str, Any], Dict[str, Any], Dict[str, Any]) -> None
    params = resolve_s3_http_options(**options)
    config = params.pop("config")
    assert params == parameters
    assert not isinstance(config, dict)
    for cfg, val in configuration.items():
        assert getattr(config, cfg) == val  # no None default because expected value
    for cfg in parameters:
        assert not hasattr(config, cfg)


@mocked_aws_config(default_region=MOCK_AWS_REGION)  # check that URL can be different from default
@mocked_aws_s3
@pytest.mark.parametrize(
    "s3_url, expect_region, expect_url",
    [
        (f"https://s3.{region}.amazonaws.com/test/file.txt", region, "s3://test/file.txt")
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ] + [
        (f"https://s3.{region}.amazonaws.com/test/dir/nested/file.txt", region, "s3://test/dir/nested/file.txt")
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ] + [
        (f"https://test.s3.{region}.amazonaws.com/dir/nested/file.txt", region, "s3://test/dir/nested/file.txt")
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ] + [
        (f"https://test.s3.{region}.amazonaws.com/dir/only/", region, "s3://test/dir/only/")
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ] + [
        (f"https://s3.{region}.amazonaws.com/test/dir/only/", region, "s3://test/dir/only/")
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ] + [
        (
            f"https://access-111122223333.s3-accesspoint.{region}.amazonaws.com/test/",
            region, f"s3://arn:aws:s3:{region}:111122223333:accesspoint/access/test/"
        )
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ] + [
        (
            f"https://test-location-123456789012.s3-accesspoint.{region}.amazonaws.com/dir/file.txt",
            region, f"s3://arn:aws:s3:{region}:123456789012:accesspoint/test-location/dir/file.txt"
        )
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ] + [
        (
            f"https://test-location-123456789012.s3-accesspoint.{region}.amazonaws.com/",
            region, f"s3://arn:aws:s3:{region}:123456789012:accesspoint/test-location/"
        )
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ] + [
        (
            f"https://test-location-123456789012.s3-accesspoint.{region}.amazonaws.com/nested/dir/",
            region, f"s3://arn:aws:s3:{region}:123456789012:accesspoint/test-location/nested/dir/"
        )
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ] + [
        (
            f"https://test-location-123456789012.outpost-123.s3-outposts.{region}.amazonaws.com/nested/dir/",
            region,
            f"s3://arn:aws:s3-outposts:{region}:123456789012:outpost/outpost-123/accesspoint/test-location/nested/dir/"
        )
        for region in AWS_S3_REGION_SUBSET_WITH_MOCK
    ]
)
def test_resolve_s3_from_http(s3_url, expect_region, expect_url):
    # type: (str, RegionName, str) -> None
    s3_location, s3_region = resolve_s3_from_http(s3_url)
    assert s3_region == expect_region
    assert s3_location == expect_url


@mocked_aws_config
@mocked_aws_s3
@pytest.mark.parametrize("s3_url_invalid", [
    f"https://s3.{MOCK_AWS_REGION}.amazonaws.com/",        # missing bucket and dir/file reference
    f"https://s3.{MOCK_AWS_REGION}.amazonaws.com/bucket",  # missing trailing slash (dir reference)
    f"https://bucket.s3.{MOCK_AWS_REGION}.amazonaws.com",  # missing trailing slash (dir reference)
    f"https://123456789012.s3-accesspoint.{MOCK_AWS_REGION}.amazonaws.com",  # missing access-point
    f"https://s3.{AWS_S3_REGION_NON_DEFAULT}.amazonaws.com/",        # missing bucket and dir/file reference
    f"https://s3.{AWS_S3_REGION_NON_DEFAULT}.amazonaws.com/bucket",  # missing trailing slash (dir reference)
    f"https://bucket.s3.{AWS_S3_REGION_NON_DEFAULT}.amazonaws.com",  # missing trailing slash (dir reference)
    f"https://123456789012.s3-accesspoint.{AWS_S3_REGION_NON_DEFAULT}.amazonaws.com",  # missing access-point
    "https://access-111122223333.s3-accesspoint.amazonaws.com/test/",  # missing region
])
def test_resolve_s3_from_http_invalid(s3_url_invalid):
    with pytest.raises(ValueError, match=r"^Invalid AWS S3 reference format.*"):
        resolve_s3_from_http(s3_url_invalid)


@pytest.mark.parametrize("s3_reference, expect_region, expect_bucket, expect_path", [
    (
        "s3://some-bucket/",
        None,
        "some-bucket",
        "/"
    ),
    (
        "s3://some-bucket/dir/",
        None,
        "some-bucket",
        "dir/"
    ),
    (
        "s3://some-bucket/dir/file.txt",
        None,
        "some-bucket",
        "dir/file.txt"
    ),
    (
        "s3://arn:aws:s3:ca-central-1:12345:accesspoint/location/",
        "ca-central-1",
        "arn:aws:s3:ca-central-1:12345:accesspoint/location",
        "/"
    ),
    (
        "s3://arn:aws:s3:ca-central-1:12345:accesspoint/location/file-key",
        "ca-central-1",
        "arn:aws:s3:ca-central-1:12345:accesspoint/location",
        "file-key"
    ),
    (
        "s3://arn:aws:s3-outposts:ca-central-1:12345:outpost/11235/bucket/here/some-dir/some-file.txt",
        "ca-central-1",
        "arn:aws:s3-outposts:ca-central-1:12345:outpost/11235/bucket/here",
        "some-dir/some-file.txt"
    ),
    (
        "s3://arn:aws:s3-outposts:us-east-2:12345:outpost/11235/accesspoint/thing/dir/stuff.txt",
        "us-east-2",
        "arn:aws:s3-outposts:us-east-2:12345:outpost/11235/accesspoint/thing",
        "dir/stuff.txt"
    ),
    (
        "s3://arn:aws:s3-outposts:us-east-2:12345:outpost/11235/accesspoint/thing/much/nested/stuff.txt",
        "us-east-2",
        "arn:aws:s3-outposts:us-east-2:12345:outpost/11235/accesspoint/thing",
        "much/nested/stuff.txt"
    ),
    (
        "s3://arn:aws:s3-outposts:us-east-2:12345:outpost/11235/accesspoint/thing/only-file.txt",
        "us-east-2",
        "arn:aws:s3-outposts:us-east-2:12345:outpost/11235/accesspoint/thing",
        "only-file.txt"
    ),
])
def test_resolve_s3_reference(s3_reference, expect_region, expect_bucket, expect_path):
    # type: (str, Optional[RegionName], str, str) -> None
    s3_bucket, s3_path, s3_region = resolve_s3_reference(s3_reference)
    assert s3_region == expect_region
    assert s3_bucket == expect_bucket
    assert s3_path == expect_path


@pytest.mark.parametrize("s3_reference, valid", [
    ("s3://", False),
    ("s3://test", False),
    ("s3://test/", True),
    ("s3://test/file.txt", True),
    ("s3://test/test/item", True),
    ("s3://test/test/item/", True),
    ("s3://-test/test/item/", False),
    ("s3://_test/test/item/", False),
    ("s3://.test/test/item/", False),
    ("s3://test-/test/item/", False),
    ("s3://test_/test/item/", False),
    ("s3://test./test/item/", False),
    ("s3://test/test/item//", False),
    ("s3://test/test/item//asm1112123-----....._____!xyz//", False),
    ("s3://test/test/item/sm1112123-----....._____!xyz//", False),
    ("s3://test/test/item/sm1112123-----....._____xyz//", False),
    ("s3://test/test/item//asm1112123-----....._____!xyz/", False),
    ("s3://test/test/item/sm1112123-----....._____!xyz/", False),
    ("s3://test/test/item/sm111//2123-----....._____xyz/", False),
    ("s3://test/test/item/sm1112123-----....._____xyz", True),
    ("s3://test/test/item/sm1112123-----....._____xyz.txt", True),
    ("s3://test/test/item/sm111/2123-----....._____xyz/", True),
])
def test_validate_s3_reference(s3_reference, valid):
    # type: (str, bool) -> None
    match = re.match(AWS_S3_BUCKET_REFERENCE_PATTERN, s3_reference)
    assert bool(match) is valid


@pytest.mark.parametrize(
    "combo",
    itertools.chain(
        # invalid combinations
        itertools.product(
            # invalid bucket combinations
            [
                "a123--..__!xyz",
                "as!xyz",
                "sxyz-",
                "-sxyz",
                ".sxyz",
                "sxyz-",
                "sxyz.",
                "abc_def",
                "abc..def",  # adjacent not allowed
                # specific case disallowed
                "bucket-s3alias",
                "xn--bucket",
            ],
            # invalid region combinations
            [
                "abc",
                "-us-east-1",
                "1us-east-1",
                "us-east-123",
                # add valid region to check bucket invalid still triggers
                AWS_S3_REGION_NON_DEFAULT,
            ],
            [False],
        ),
        # valid combinations
        itertools.product(
            # valid bucket combinations
            [
                "bucket1",
                "1bucket",
                "bucket-test",
                "bucket--test",
                "bucket.test",
                "bucket.test.2",
            ],
            # valid region combinations
            AWS_S3_REGION_SUBSET,
            [True],
        )
    )
)
def test_validate_s3_parameters(combo):
    # type: (Tuple[str, str, bool]) -> None
    bucket, region, valid = combo
    try:
        validate_s3(region=region, bucket=bucket)
    except ValueError as exc:
        if valid:
            pytest.fail(f"Raised exception not expected for [{combo}]. {exc}")
    else:
        if not valid:
            pytest.fail(f"Not raised expected exception for [{combo}]. (ValueError)")


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


@pytest.mark.parametrize("query,params,expected", [
    ("key1=val1;key2=val21,val22;key3=val3;key4", {},
     {"key1": ["val1"], "key2": ["val21", "val22"], "key3": ["val3"], "key4": []}),
    ("key1='  value 1  '  ; key2 = val2 ", {},
     {"key1": ["  value 1  "], "key2": ["val2"]}),
    ("key1='  value 1  '  ; key2 = val2 ", {"unescape_quotes": False},
     {"key1": ["'  value 1  '"], "key2": ["val2"]}),
    ("key1='  value 1  '  ; key2 = val2 ", {"unescape_quotes": False, "strip_spaces": False},
     {"key1": ["'  value 1  '  "], " key2 ": [" val2 "]}),
    ("key1=val1,val2;key1=val3", {},
     {"key1": ["val1", "val2", "val3"]}),
    ("key1=val1,val2;KEY1=val3", {},
     {"key1": ["val1", "val2", "val3"]}),
    ("key1=val1,val2;KEY1=val3", {"case_insensitive": False},
     {"key1": ["val1", "val2"], "KEY1": ["val3"]}),
    ("format=json&inputs=key1=value1;key2=val2,val3", {"pair_sep": "&", "nested_pair_sep": ";"},
     {"format": ["json"], "inputs": {"key1": ["value1"], "key2": ["val2", "val3"]}}),
])
def test_parse_kvp(query, params, expected):
    result = parse_kvp(query, **params)
    assert result == expected


@pytest.mark.parametrize("headers,support,expected", [
    # both modes supported (sync attempted upto max/specified wait time, unless async requested explicitly)
    ({}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
     (ExecuteMode.SYNC, 10, {})),
    ({"Prefer": ""}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
     (ExecuteMode.SYNC, 10, {})),
    ({"Prefer": "respond-async"}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
     (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
    ({"Prefer": "respond-async, wait=4"}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
     (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
    ({"Prefer": "wait=4"}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
     (ExecuteMode.SYNC, 4, {"Preference-Applied": "wait=4"})),
    ({"Prefer": "wait=20"}, [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC],
     (ExecuteMode.ASYNC, None, {})),  # larger than max time
    # only supported async (enforced) - original behaviour
    ({}, [ExecuteControlOption.ASYNC],
     (ExecuteMode.ASYNC, None, {})),
    ({"Prefer": ""}, [ExecuteControlOption.ASYNC],
     (ExecuteMode.ASYNC, None, {})),
    ({"Prefer": "respond-async"}, [ExecuteControlOption.ASYNC],
     (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
    ({"Prefer": "respond-async, wait=4"}, [ExecuteControlOption.ASYNC],
     (ExecuteMode.ASYNC, None, {"Preference-Applied": "respond-async"})),
    ({"Prefer": "wait=4"}, [ExecuteControlOption.ASYNC],
     (ExecuteMode.ASYNC, None, {})),
])
def test_prefer_header_execute_mode(headers, support, expected):
    result = parse_prefer_header_execute_mode(headers, support)
    assert result == expected


@pytest.mark.parametrize("number,binary,unit,expect", [
    (1.234, False, "B", "1.234 B"),
    (10_000_000, False, "B", "10.000 MB"),
    (10_000_000, True, "B", "9.537 MiB"),
    (10_000_000_000, False, "B", "10.000 GB"),
    (10_737_418_240, True, "B", "10.000 GiB"),
    (10_000_000_000, True, "B", "9.313 GiB"),
    (10**25, False, "", "10.000 Y"),
    (10**25, True, "B", "8.272 YiB"),
    (10**28, False, "", "10000.000 Y"),  # last unit goes over bound
    (10**-28, False, "s", "0.000 ys"),   # out of bound, cannot represent smaller
    (-10 * 10**3, False, "s", "-10.000 ks"),  # negative & positive power
    (-0.001234, False, "s", "-1.234 ms"),  # negative & reducing power
    (0, False, "", "0.000"),
    (0.000, True, "", "0.000 B"),
])
def test_apply_number_with_unit(number, binary, unit, expect):
    result = apply_number_with_unit(number, unit=unit, binary=binary)
    assert result == expect


@pytest.mark.parametrize("number,binary,expect", [
    ("1 B", None, 1),
    # note: 'k' lower
    ("1k", False, 1_000),            # normal
    ("1kB", False, 1_000),           # forced unmatched 'B'
    ("1kB", None, 1_024),            # auto from 'B'
    ("1kB", True, 1_024),            # forced but matches
    # note: 'K' upper
    ("1K", False, 1_000),            # normal
    ("1KB", False, 1_000),           # forced unmatched 'B'
    ("1KB", None, 1_024),            # auto from 'B'
    ("1KB", True, 1_024),            # forced but matches
    # normal
    ("1KiB", True, 1_024),           # forced but matches
    ("1KiB", None, 1_024),           # normal
    ("1KiB", False, 1_000),          # forced unmatched 'B'
    ("1G", False, 1_000_000_000),    # normal
    ("1GB", False, 1_000_000_000),   # forced unmatched 'B'
    ("1GB", None, 1_073_741_824),    # auto from 'B'
    ("1GB", True, 1_073_741_824),    # forced but matches
    ("1GiB", True, 1_073_741_824),   # forced but matches
    ("1GiB", None, 1_073_741_824),   # normal
    ("1GiB", False, 1_000_000_000),  # forced unmatched 'B'
    # rounding expected for binary (ie: 1 x 2^30 + 400 x 2^20 for accurate result)
    # if not rounded, converting causes floating remainder (1.4 x 2^30 = 1503238553.6)
    ("1.4GiB", True, 1_503_238_554),
])
def test_parse_number_with_unit(number, binary, expect):
    result = parse_number_with_unit(number, binary=binary)
    assert result == expect


def test_parse_number_with_unit_error():
    with pytest.raises(ValueError):
        parse_number_with_unit(123)  # noqa


def custom_handler_fail(*_):
    raise NotImplementedError("test not implemented error")


def custom_handler_valid(exception):
    return "sporadic error" in str(exception)


@pytest.mark.parametrize("errors,raises,conditions,retries", [
    ([True, False, None], TypeError, ValueError, 2),    # first ValueError handled, second raises TypeError directly
    ([True, False, None], ValueError, ValueError, 0),   # first ValueError handled but re-raised since retries exhausted
    ([True, None], None, ValueError, 2),                # first ValueError handled, second succeeds
    ([None, False], None, ValueError, 10),              # immediate success, no retry required
    ([False, None], TypeError, ValueError, 0),          # no retry, first ValueError re-raised since retries exhausted
    ([False, None], TypeError, ValueError, -1),         # same as previous, non positive retries defaults to zero
    ([True, False, None], None, (ValueError, TypeError), 4),    # both errors allowed, succeeds on 3rd after 2 retries
    ([True, False, None], NotImplementedError, custom_handler_fail, 3),  # itself raises, bubbles up error with no-retry
    ([True, False, None], TypeError, custom_handler_valid, 3),  # first ValueError handled with text, TypeError re-raise
])
def test_retry_on_condition(errors, raises, conditions, retries):
    test_errors = []

    def function_no_args():
        err = test_errors.pop(0)
        if err is True:
            raise ValueError("test sporadic error")
        if err is False:
            raise TypeError("test unhandled error")
        return "OK"

    def function_with_args(value, keyword=None):  # noqa
        return function_no_args()

    def run_test(*args, **kwargs):
        test_errors.clear()
        test_errors.extend(errors)
        test_case = f" (operation {'with' if args and kwargs else 'without'} args)"
        result = None
        try:
            if args and kwargs:
                result = retry_on_condition(function_with_args, *args, **kwargs, condition=conditions, retries=retries)
            else:
                result = retry_on_condition(function_no_args, condition=conditions, retries=retries)
        except Exception as exc:
            assert raises is not None, f"Expected no unhandled error raised{test_case}"
            assert isinstance(exc, raises), f"Expected specific error to be raised{test_case}"
        if raises is None:
            assert result == "OK", f"Expected to succeed after retries{test_case}"
        else:
            assert result is None, f"Expected failure following raised error{test_case}"

    run_test()
    run_test(1, keyword="test")
