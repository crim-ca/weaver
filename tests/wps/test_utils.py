import contextlib
import copy

import mock

from tests.utils import mocked_remote_wps
from weaver.formats import ACCEPT_LANGUAGE_EN_US, ACCEPT_LANGUAGE_FR_CA, CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML
from weaver.wps.utils import get_wps_client, set_wps_language


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
