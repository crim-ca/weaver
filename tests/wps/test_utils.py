import contextlib
import copy
import os
import shutil
import tempfile

import mock
import pytest
from pyramid.httpexceptions import HTTPUnprocessableEntity
from pyramid.testing import DummyRequest

from tests.utils import mocked_remote_wps
from weaver.formats import AcceptLanguage, ContentType
from weaver.wps.utils import get_wps_client, get_wps_output_context, map_wps_output_location, set_wps_language


def test_set_wps_language():
    wps = mock.Mock()
    languages = mock.Mock()
    wps.languages = languages
    languages.default = AcceptLanguage.EN_US
    languages.supported = [AcceptLanguage.EN_US, AcceptLanguage.FR_CA]

    set_wps_language(wps, "ru, fr;q=0.5")
    assert wps.language == AcceptLanguage.FR_CA


def test_get_wps_client_headers_preserved():
    """
    Validate that original request headers are not modified following WPS client sub-requests.
    """
    test_wps_url = "http://dont-care.com/wps"
    test_headers = {
        "Content-Type": ContentType.APP_XML,
        "Content-Length": "0",
        "Accept-Language": AcceptLanguage.FR_CA,
        "Accept": ContentType.APP_JSON,
        "Authorization": "Bearer: FAKE",  # nosec
    }
    test_copy_headers = copy.deepcopy(test_headers)
    # following are removed for sub-request
    test_wps_headers = {
        "Accept-Language": AcceptLanguage.FR_CA,
        "Authorization": "Bearer: FAKE",  # nosec
    }

    with contextlib.ExitStack() as stack:
        patches = mocked_remote_wps([], [AcceptLanguage.FR_CA])
        mocks = []
        for patch in patches:
            mocks.append(stack.enter_context(patch))

        wps = get_wps_client(test_wps_url, headers=test_headers)

    for mocked in mocks:
        assert mocked.called
    assert test_headers == test_copy_headers, "Input headers must be unmodified after WPS client call"
    assert wps.headers == test_wps_headers, "Only allowed headers should have been passed down to WPS client"
    assert wps.language == AcceptLanguage.FR_CA, "Language should have been passed down to WPS client from header"
    assert wps.url == test_wps_url


def test_get_wps_output_context_validation():
    bad_cases = [
        "test/////test",
        "test/test//",
        "test/./test/test",
        "test/../test/test",
        "/test/test/test/test",
        "/test/test/",
        "/test",
        "/test/",
        "./test",
        "../test",
        "/"
    ]
    good_cases = [
        ("test", "test"),
        ("test/test", "test/test"),
        ("test/test/", "test/test"),  # allow trailing slash auto-removed
        ("test/test/test/test", "test/test/test/test"),
        ("test-test", "test-test"),
        ("test_test", "test_test"),
        ("test-test/test/test_test", "test-test/test/test_test"),
    ]

    header_names = [
        "x-wps-output-context",
        "X-WPS-OUTPUT-CONTEXT",
        "X-WPS-Output-Context"
    ]

    for header in header_names:
        for case in bad_cases:
            # validate against provided header
            try:
                req = DummyRequest(headers={header: case})
                get_wps_output_context(req)
            except HTTPUnprocessableEntity:
                pass
            else:
                pytest.fail("Exception not raised when expected: (header={}, case={})".format(header, case))
            # validate same conditions fulfilled by default context if header omitted
            try:
                settings = {"weaver.wps_output_context": case}
                with mock.patch("weaver.wps.utils.get_settings", return_value=settings):
                    req = DummyRequest(headers={})
                    get_wps_output_context(req)
            except HTTPUnprocessableEntity:
                pass
            else:
                pytest.fail("Exception not raised when expected: (<setting>, case={})".format(case))

        for case, result in good_cases:
            # validate against provided header
            try:
                req = DummyRequest(headers={header: case})
                ctx = get_wps_output_context(req)
                assert ctx == result
            except Exception as exc:
                pytest.fail("Exception raised when none is expected: (header={}, case={})\n"
                            "Exception: {!s}: ${!s}".format(header, case, exc.__class__.__name__, exc))

            # validate same conditions fulfilled by default context if header omitted
            settings = {"weaver.wps_output_context": case}
            with mock.patch("weaver.wps.utils.get_settings", return_value=settings):
                try:
                    req = DummyRequest(headers={})
                    ctx = get_wps_output_context(req)
                    assert ctx == result
                except Exception as exc:
                    pytest.fail("Exception raised when none is expected: (<setting>, case={})\n"
                                "Exception: {!s}: ${!s}".format(case, exc.__class__.__name__, exc))


def test_get_wps_output_context_resolution():
    test_cases = [
        # header provided uses it regardless of setting
        ("somewhere", None, "somewhere"),
        ("somewhere", "", "somewhere"),
        ("somewhere", "test", "somewhere"),
        # header empty or omitted defaults to none used when no/empty default context
        ("", None, None),
        ("", "", None),
        (None, None, None),
        (None, "", None),
        # header empty or omitted defaults to defined default context setting
        ("", "test", "test"),
        (None, "test", "test"),
    ]

    for i, (test_header, test_setting, expect_result) in enumerate(test_cases):
        try:
            headers = {"X-WPS-Output-Context": test_header}
            settings = {"weaver.wps_output_context": test_setting}
            req = DummyRequest(headers=headers)
            with mock.patch("weaver.wps.utils.get_settings", return_value=settings):
                res = get_wps_output_context(req)
            assert res == expect_result
        except Exception as exc:
            pytest.fail(
                "Exception raised when none is expected [{}]: {!s}: ${!s}".format(i, exc.__class__.__name__, exc)
            )


def test_map_wps_output_location_duplicate_subdir():
    for tmp_dir in [
        "/tmp/tmp/tmp",
        "/tmp/tmpdir"
    ]:
        wps_out = "http:///localhost/wps-output/tmp"
        settings = {
            "weaver.wps_output_dir": tmp_dir,
            "weaver.wps_output_url": wps_out
        }
        path = map_wps_output_location(f"{wps_out}/tmp/some-file-tmp.tmp", settings, exists=False)
        assert path == f"{tmp_dir}/tmp/some-file-tmp.tmp"

        path = map_wps_output_location(f"{tmp_dir}/here/some-file-tmp.tmp", settings, exists=False, url=True)
        assert path == f"{wps_out}/here/some-file-tmp.tmp"


def test_map_wps_output_location_exists():
    wps_url = "http:///localhost/wps-output/tmp"
    wps_dir = "/tmp/weaver-test/test-outputs"
    settings = {
        "weaver.wps_output_dir": wps_dir,
        "weaver.wps_output_url": wps_url
    }
    try:
        os.makedirs(wps_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=wps_dir, suffix="test.txt", mode="w") as tmp_file:
            tmp_file.write("fake data")
            tmp_file.flush()
            tmp_file.seek(0)
            tmp_path = tmp_file.name
            tmp_name = os.path.split(tmp_file.name)[-1]
            tmp_http = f"{wps_url}/{tmp_name}"
            assert os.path.isfile(tmp_path), "failed setup test file"

            path = map_wps_output_location(tmp_http, settings, exists=True)
            assert path == tmp_path
            path = map_wps_output_location(tmp_http, settings, exists=False)
            assert path == tmp_path

            path = map_wps_output_location(tmp_path, settings, exists=True, url=True)
            assert path == tmp_http
            path = map_wps_output_location(tmp_path, settings, exists=False, url=True)
            assert path == tmp_http

        assert not os.path.isfile(tmp_path), "test file expected to be auto-cleaned"

        path = map_wps_output_location(tmp_http, settings, exists=True)
        assert path is None
        path = map_wps_output_location(tmp_http, settings, exists=False)
        assert path == tmp_path

        path = map_wps_output_location(tmp_path, settings, exists=True, url=True)
        assert path is None
        path = map_wps_output_location(tmp_path, settings, exists=False, url=True)
        assert path == tmp_http

    except AssertionError:
        raise
    except Exception as exc:
        pytest.fail(f"Failed due to unexpected exception: [{exc}]")
    finally:
        shutil.rmtree(wps_dir, ignore_errors=True)
