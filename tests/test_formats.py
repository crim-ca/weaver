import os

import mock
import six
from pyramid.httpexceptions import HTTPOk, HTTPRequestTimeout
from pyramid.response import Response
from pywps.inout.formats import Format
from requests.exceptions import ConnectionError

from weaver.formats import (
    CONTENT_TYPE_ANY,
    CONTENT_TYPE_APP_JSON,
    CONTENT_TYPE_APP_GEOJSON,
    CONTENT_TYPE_APP_NETCDF,
    CONTENT_TYPE_APP_XML,
    CONTENT_TYPE_IMAGE_GEOTIFF,
    EDAM_MAPPING,
    EDAM_NAMESPACE,
    EDAM_NAMESPACE_DEFINITION,
    FORMAT_NAMESPACES,
    IANA_NAMESPACE,
    IANA_NAMESPACE_DEFINITION,
    clean_mime_type_format,
    get_cwl_file_format,
    get_extension,
    get_format,
)


def test_get_extension():
    assert get_extension(CONTENT_TYPE_APP_JSON) == ".json"  # basic
    assert get_extension(CONTENT_TYPE_APP_JSON + "; charset=UTF-8") == ".json"  # ignore extra parameters
    assert get_extension(CONTENT_TYPE_APP_GEOJSON) == ".geojson"  # pywps definition
    assert get_extension(CONTENT_TYPE_IMAGE_GEOTIFF) == ".tiff"  # pywps definition
    assert get_extension("application/x-custom") == ".custom"
    assert get_extension("application/unknown") == ".unknown"


def test_get_extension_glob_any():
    assert get_extension(CONTENT_TYPE_ANY) == ".*"


def test_get_format():
    assert get_format(CONTENT_TYPE_APP_JSON) == Format(CONTENT_TYPE_APP_JSON)  # basic
    assert get_format(CONTENT_TYPE_APP_JSON + "; charset=UTF-8") == Format(CONTENT_TYPE_APP_JSON)
    assert get_format(CONTENT_TYPE_APP_GEOJSON) == Format(CONTENT_TYPE_APP_GEOJSON)  # pywps vendor MIME-type
    assert get_format(CONTENT_TYPE_APP_NETCDF).encoding == "base64"  # extra encoding data available


def test_get_cwl_file_format_tuple():
    tested = set(FORMAT_NAMESPACES)
    for mime_type in [CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_NETCDF]:
        res = get_cwl_file_format(mime_type, make_reference=False)
        assert isinstance(res, tuple) and len(res) == 2
        ns, fmt = res
        assert isinstance(ns, dict) and len(ns) == 1
        assert any(f in ns for f in FORMAT_NAMESPACES)
        assert list(ns.values())[0].startswith("http")
        ns_name = list(ns.keys())[0]
        assert fmt.startswith("{}:".format(ns_name))
        tested.remove(ns_name)
    assert len(tested) == 0, "test did not evaluate every namespace variation"


def test_get_cwl_file_format_reference():
    tested = set(FORMAT_NAMESPACES)
    tests = [(IANA_NAMESPACE_DEFINITION, CONTENT_TYPE_APP_JSON), (EDAM_NAMESPACE_DEFINITION, CONTENT_TYPE_APP_NETCDF)]
    for ns, mime_type in tests:
        res = get_cwl_file_format(mime_type, make_reference=True)
        ns_name, ns_url = list(ns.items())[0]
        assert isinstance(res, six.string_types)
        assert res.startswith(ns_url)
        tested.remove(ns_name)
    assert len(tested) == 0, "test did not evaluate every namespace variation"


def test_get_cwl_file_format_unknown():
    res = get_cwl_file_format("application/unknown", make_reference=False, must_exist=True)
    assert isinstance(res, tuple)
    assert res == (None, None)
    res = get_cwl_file_format("application/unknown", make_reference=True, must_exist=True)
    assert res is None


def test_get_cwl_file_format_default():
    fmt = "application/unknown"
    iana_url = IANA_NAMESPACE_DEFINITION[IANA_NAMESPACE]
    iana_fmt = "{}:{}".format(IANA_NAMESPACE, fmt)
    res = get_cwl_file_format("application/unknown", make_reference=False, must_exist=False)
    assert isinstance(res, tuple)
    assert res[0] == {IANA_NAMESPACE: iana_url}
    assert res[1] == iana_fmt
    res = get_cwl_file_format("application/unknown", make_reference=True, must_exist=False)
    assert res == iana_url + fmt


def test_get_cwl_file_format_retry_attempts():
    """Verifies that failing request will not immediately fail the MIME-type validation."""
    codes = {"codes": [HTTPOk.code, HTTPRequestTimeout.code]}  # note: used in reverse order

    def mock_request_extra(*args, **kwargs):  # noqa: E811
        m_resp = Response()
        m_resp.status_code = codes["codes"].pop()
        return m_resp

    with mock.patch("requests.Session.request", side_effect=mock_request_extra) as mocked_request:
        _, fmt = get_cwl_file_format(CONTENT_TYPE_APP_JSON)
        assert fmt == "{}:{}".format(IANA_NAMESPACE, CONTENT_TYPE_APP_JSON)
        assert mocked_request.call_count == 2


def test_get_cwl_file_format_retry_fallback_urlopen():
    """Verifies that failing request because of critical error still validate the MIME-type using the fallback."""
    def mock_connect_error(*args, **kwargs):  # noqa: E811
        raise ConnectionError()

    def mock_urlopen(*args, **kwargs):  # noqa: E811
        return HTTPOk()

    with mock.patch("requests.Session.request", side_effect=mock_connect_error) as mocked_request:
        with mock.patch("weaver.formats.urlopen", side_effect=mock_urlopen) as mocked_urlopen:
            _, fmt = get_cwl_file_format(CONTENT_TYPE_APP_JSON)
            assert fmt == "{}:{}".format(IANA_NAMESPACE, CONTENT_TYPE_APP_JSON)
            assert mocked_request.call_count == 4   # internally attempted 4 times (1 attempt + 3 retries)
            assert mocked_urlopen.call_count == 1


def test_clean_mime_type_format_iana():
    iana_fmt = "{}:{}".format(IANA_NAMESPACE, CONTENT_TYPE_APP_JSON)  # "iana:mime_type"
    res_type = clean_mime_type_format(iana_fmt)
    assert res_type == CONTENT_TYPE_APP_JSON
    iana_fmt = os.path.join(list(IANA_NAMESPACE_DEFINITION.values())[0], CONTENT_TYPE_APP_JSON)  # "iana-url/mime_type"
    res_type = clean_mime_type_format(iana_fmt)
    assert res_type == CONTENT_TYPE_APP_JSON  # application/json


def test_clean_mime_type_format_edam():
    mime_type, fmt = list(EDAM_MAPPING.items())[0]
    edam_fmt = "{}:{}".format(EDAM_NAMESPACE, fmt)  # "edam:format_####"
    res_type = clean_mime_type_format(edam_fmt)
    assert res_type == mime_type
    edam_fmt = os.path.join(list(EDAM_NAMESPACE_DEFINITION.values())[0], fmt)  # "edam-url/format_####"
    res_type = clean_mime_type_format(edam_fmt)
    assert res_type == mime_type  # application/x-type


def test_clean_mime_type_format_io_remove_extra_parameters():
    test_input_formats = [
        (CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_JSON),
        (CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_JSON + "; charset=UTF-8"),
        (CONTENT_TYPE_APP_XML, CONTENT_TYPE_APP_XML + "; charset=UTF-8; version=1.0"),
        ("application/vnd.api+json", "application/vnd.api+json; charset=UTF-8"),
        ("application/vnd.api+json", "application/vnd.api+json"),
    ]
    for expect_fmt, test_fmt in test_input_formats:
        res_type = clean_mime_type_format(test_fmt, strip_parameters=True)
        assert res_type == expect_fmt


def test_clean_mime_type_format_io_strip_base_type():
    test_input_formats = [
        (CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_JSON),
        (CONTENT_TYPE_APP_JSON + "; charset=UTF-8", CONTENT_TYPE_APP_JSON + "; charset=UTF-8"),
        (CONTENT_TYPE_APP_XML + "; charset=UTF-8; version=1.0", CONTENT_TYPE_APP_XML + "; charset=UTF-8; version=1.0"),
        (CONTENT_TYPE_APP_JSON + "; charset=UTF-8", "application/vnd.api+json; charset=UTF-8"),
        (CONTENT_TYPE_APP_JSON, "application/vnd.api+json"),
    ]
    for expect_fmt, test_fmt in test_input_formats:
        res_type = clean_mime_type_format(test_fmt, base_subtype=True)
        assert res_type == expect_fmt


def test_clean_mime_type_format_io_strip_base_and_remove_parameters():
    test_input_formats = [
        (CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_JSON),
        (CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_JSON + "; charset=UTF-8"),
        (CONTENT_TYPE_APP_XML, CONTENT_TYPE_APP_XML + "; charset=UTF-8; version=1.0"),
        (CONTENT_TYPE_APP_JSON, "application/vnd.api+json; charset=UTF-8"),
        (CONTENT_TYPE_APP_JSON, "application/vnd.api+json"),
    ]
    for expect_fmt, test_fmt in test_input_formats:
        res_type = clean_mime_type_format(test_fmt, base_subtype=True, strip_parameters=True)
        assert res_type == expect_fmt
