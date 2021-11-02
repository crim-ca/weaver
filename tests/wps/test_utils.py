import contextlib
import copy

import mock
import pytest
from pyramid.httpexceptions import HTTPUnprocessableEntity
from pyramid.testing import DummyRequest

from tests.utils import mocked_remote_wps
from weaver.formats import ACCEPT_LANGUAGE_EN_US, ACCEPT_LANGUAGE_FR_CA, CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML
from weaver.wps.utils import get_wps_client, get_wps_output_context, set_wps_language


def test_set_wps_language():
    wps = mock.Mock()
    languages = mock.Mock()
    wps.languages = languages
    languages.default = ACCEPT_LANGUAGE_EN_US
    languages.supported = [ACCEPT_LANGUAGE_EN_US, ACCEPT_LANGUAGE_FR_CA]

    set_wps_language(wps, "ru, fr;q=0.5")
    assert wps.language == ACCEPT_LANGUAGE_FR_CA


def test_get_wps_client_headers_preserved():
    """
    Validate that original request headers are not modified following WPS client sub-requests.
    """
    test_wps_url = "http://dont-care.com/wps"
    test_headers = {
        "Content-Type": CONTENT_TYPE_APP_XML,
        "Content-Length": "0",
        "Accept-Language": ACCEPT_LANGUAGE_FR_CA,
        "Accept": CONTENT_TYPE_APP_JSON,
        "Authorization": "Bearer: FAKE",  # nosec
    }
    test_copy_headers = copy.deepcopy(test_headers)
    # following are removed for sub-request
    test_wps_headers = {
        "Accept-Language": ACCEPT_LANGUAGE_FR_CA,
        "Authorization": "Bearer: FAKE",  # nosec
    }

    with contextlib.ExitStack() as stack:
        patches = mocked_remote_wps([], [ACCEPT_LANGUAGE_FR_CA])
        mocks = []
        for patch in patches:
            mocks.append(stack.enter_context(patch))

        wps = get_wps_client(test_wps_url, headers=test_headers)

    for mocked in mocks:
        assert mocked.called
    assert test_headers == test_copy_headers, "Input headers must be unmodified after WPS client call"
    assert wps.headers == test_wps_headers, "Only allowed headers should have been passed down to WPS client"
    assert wps.language == ACCEPT_LANGUAGE_FR_CA, "Language should have been passed down to WPS client from header"
    assert wps.url == test_wps_url


def test_get_wps_output_context():
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
            with pytest.raises(HTTPUnprocessableEntity):
                req = DummyRequest(headers={header: case})
                get_wps_output_context(req)
        for case, result in good_cases:
            try:
                req = DummyRequest(headers={header: case})
                ctx = get_wps_output_context(req)
                assert ctx == result
            except Exception as exc:
                pytest.fail("Exception raised when none is expected: {!s}: ${!s}".format(exc.__class__.__name__, exc))
