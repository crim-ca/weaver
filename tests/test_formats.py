import contextlib
import datetime
import inspect
import itertools
import os
import uuid
from urllib.error import URLError
from urllib.request import urlopen

import mock
import pytest
from pyramid.httpexceptions import HTTPOk, HTTPRequestTimeout
from pyramid.response import Response
from pywps.inout.formats import Format
from requests.exceptions import ConnectionError

from tests.utils import MockedRequest
from weaver import formats as f
from weaver.utils import null, request_extra

_ALLOWED_MEDIA_TYPE_CATEGORIES = [
    "application",
    "archives",
    "audio",
    "data",
    "documents",
    "image",
    "multipart",
    "text",
    "video",
]


@pytest.mark.parametrize(
    "media_type",
    (
        {
            f.get_content_type(_ext)
            for _ext in f.get_allowed_extensions()
            if f.get_content_type(_ext) is not None
        }
        | {_ctype for _ctype in f.ContentType.values() if isinstance(_ctype, str)}
        | set(f.IANA_MAPPING)
        | set(f.EDAM_MAPPING)
        | set(f.OGC_MAPPING)
        | set(f.OPENGIS_MAPPING)
    ) - {f.ContentType.ANY}
)
def test_valid_media_type_categories(media_type):
    assert media_type.split("/")[0] in _ALLOWED_MEDIA_TYPE_CATEGORIES


@pytest.mark.parametrize(
    ["test_extension", "extra_params", "expected_content_type"],
    [
        ("", {"dot": False}, ""),
        (f.ContentType.APP_JSON, {}, ".json"),  # basic
        (f"{f.ContentType.APP_JSON}; charset=UTF-8", {}, ".json"),  # ignore extra parameters
        (f.ContentType.APP_GEOJSON, {}, ".geojson"),  # pywps <4.4 definition
        (f.ContentType.APP_VDN_GEOJSON, {}, ".geojson"),  # pywps>=4.4 definition
        (f.ContentType.IMAGE_GEOTIFF, {}, ".tiff"),  # pywps definition
        ("application/x-custom", {}, ".custom"),
        ("application/unknown", {}, ".unknown"),
        (f.ContentType.APP_DIR, {"dot": True}, "/"),
        (f.ContentType.APP_DIR, {"dot": False}, "/"),
        (f.ContentType.APP_JSON, {"dot": False}, "json"),
        ("x", {"dot": True}, ".x"),
        ("x", {"dot": False}, "x"),
        ("x/y", {"dot": True}, ".y"),
        ("x/.y", {"dot": False}, "y"),
        (f.ContentType.ANY, {}, ".*"),
    ]
)
def test_get_extension(test_extension, extra_params, expected_content_type):
    assert f.get_extension(test_extension, **extra_params) == expected_content_type


@pytest.mark.parametrize(
    ["test_extension", "extra_params", "expected_content_type"],
    [
        (".json", {}, f.ContentType.APP_JSON),
        (".tif", {}, f.ContentType.IMAGE_TIFF),
        (".tiff", {}, f.ContentType.IMAGE_TIFF),
        (".yml", {}, f.ContentType.APP_YAML),
        (".yaml", {}, f.ContentType.APP_YAML),
        ("/", {}, f.ContentType.APP_DIR),
        (".unknown", {"default": f.ContentType.TEXT_PLAIN}, f.ContentType.TEXT_PLAIN),
        (".txt", {"charset": "UTF-8"}, f"{f.ContentType.TEXT_PLAIN}; charset=UTF-8"),
        (".tif", {"charset": "UTF-8"}, f.ContentType.IMAGE_TIFF),  # not added by error
        (".unknown", {}, None),
    ]
)
def test_get_content_type(test_extension, extra_params, expected_content_type):
    assert f.get_content_type(test_extension, **extra_params) == expected_content_type


@pytest.mark.parametrize(
    ["content_type", "charset", "expected_content_type"],
    [
        (f.ContentType.APP_JSON, "UTF-8", f"{f.ContentType.APP_JSON}; charset=UTF-8"),
        (f.ContentType.APP_JSON, "ISO-8859-1", f"{f.ContentType.APP_JSON}; charset=ISO-8859-1"),
        (f"{f.ContentType.APP_XML}; profile=test", "UTF-8", f"{f.ContentType.APP_XML}; profile=test; charset=UTF-8"),
        (f"{f.ContentType.APP_XML}; charset=UTF-8", "UTF-8", f"{f.ContentType.APP_XML}; charset=UTF-8"),
    ]
)
def test_add_content_type_charset(content_type, charset, expected_content_type):
    assert f.add_content_type_charset(content_type, charset) == expected_content_type


@pytest.mark.parametrize(
    ["test_encoding", "expected_encoding"],
    [
        (f.ContentEncoding.UTF_8.upper(), f.ContentEncoding.UTF_8),
        (f.ContentEncoding.UTF_8.lower(), f.ContentEncoding.UTF_8),
        (f.ContentEncoding.BINARY, f.ContentEncoding.BINARY),
        (f.ContentEncoding.BASE64, f.ContentEncoding.BASE64),
        ("", None),
        (None, None),
    ]
)
def test_content_encoding_get(test_encoding, expected_encoding):
    assert f.ContentEncoding.get(test_encoding) == expected_encoding


@pytest.mark.parametrize(
    ["data", "encoding", "binary", "result"],
    [
        ("123", f.ContentEncoding.UTF_8, False, "123"),
        ("123", f.ContentEncoding.UTF_8, True, b"123"),
        (b"123", f.ContentEncoding.UTF_8, False, "123"),
        (b"123", f.ContentEncoding.UTF_8, True, b"123"),
        ("123", f.ContentEncoding.BASE16, False, "313233"),
        ("123", f.ContentEncoding.BASE16, True, b"313233"),
        (b"123", f.ContentEncoding.BASE16, False, "313233"),
        (b"123", f.ContentEncoding.BASE16, True, b"313233"),
        ("123", f.ContentEncoding.BASE32, False, "GEZDG==="),
        ("123", f.ContentEncoding.BASE32, True, b"GEZDG==="),
        (b"123", f.ContentEncoding.BASE32, False, "GEZDG==="),
        (b"123", f.ContentEncoding.BASE32, True, b"GEZDG==="),
        ("123", f.ContentEncoding.BASE64, False, "MTIz"),
        ("123", f.ContentEncoding.BASE64, True, b"MTIz"),
        (b"123", f.ContentEncoding.BASE64, False, "MTIz"),
        (b"123", f.ContentEncoding.BASE64, True, b"MTIz"),
        ("123", f.ContentEncoding.BINARY, False, "MTIz"),
        ("123", f.ContentEncoding.BINARY, True, b"MTIz"),
        (b"123", f.ContentEncoding.BINARY, False, "MTIz"),
        (b"123", f.ContentEncoding.BINARY, True, b"MTIz"),
    ]
)
def test_content_encoding_encode_decode(data, encoding, binary, result):
    # type: (str | bytes, f.ContentEncoding, bool, str | bytes) -> None
    assert f.ContentEncoding.encode(data, encoding, binary) == result  # type: ignore
    b_data = isinstance(data, bytes)
    assert f.ContentEncoding.decode(result, encoding, b_data) == data  # type: ignore


def test_content_encoding_values():
    assert set(f.ContentEncoding.values()) == {
        f.ContentEncoding.UTF_8,
        f.ContentEncoding.BINARY,
        f.ContentEncoding.BASE16,
        f.ContentEncoding.BASE32,
        f.ContentEncoding.BASE64,
    }


@pytest.mark.parametrize(
    ["encoding", "expect"],
    itertools.chain(
        itertools.product(
            set(f.ContentEncoding.values()) - {f.ContentEncoding.UTF_8},
            [False],
        ),
        [
            (f.ContentEncoding.UTF_8, True)
        ]
    )
)
def test_content_encoding_is_text(encoding, expect):
    assert f.ContentEncoding.is_text(encoding) == expect


@pytest.mark.parametrize(
    ["encoding", "expect"],
    itertools.chain(
        itertools.product(
            set(f.ContentEncoding.values()) - {f.ContentEncoding.UTF_8},
            [True],
        ),
        [
            (f.ContentEncoding.UTF_8, False)
        ]
    )
)
def test_content_encoding_is_binary(encoding, expect):
    assert f.ContentEncoding.is_binary(encoding) == expect


@pytest.mark.parametrize(
    ["encoding", "mode"],
    itertools.product(
        f.ContentEncoding.values(),
        ["r", "w", "a", "r+", "w+"],
    )
)
def test_content_encoding_open_parameters(encoding, mode):
    result = f.ContentEncoding.open_parameters(encoding, mode)
    if encoding == f.ContentEncoding.UTF_8:
        assert result[0] == mode
        assert result[1] == f.ContentEncoding.UTF_8
    else:
        assert result[0][-1] == "b"
        assert result[0][:-1] == mode
        assert result[1] is None


@pytest.mark.parametrize(
    ["test_content_type", "expected_content_type", "expected_content_encoding"],
    [
        (f.ContentType.APP_JSON, f.ContentType.APP_JSON, ""),  # basic
        (f"{f.ContentType.APP_JSON}; charset=UTF-8", f.ContentType.APP_JSON, ""),  # detailed
        (f.ContentType.APP_GEOJSON, f.ContentType.APP_GEOJSON, ""),  # pywps vendor MIME-type
        (f.ContentType.APP_NETCDF, f.ContentType.APP_NETCDF, "base64"),  # extra encoding data available
    ]
)
def test_get_format(test_content_type, expected_content_type, expected_content_encoding):
    assert f.get_format(test_content_type) == Format(expected_content_type, encoding=expected_content_encoding)


@pytest.mark.parametrize(
    "test_extension",
    [
        f.ContentType.APP_OCTET_STREAM,
        f.ContentType.APP_FORM,
        f.ContentType.MULTIPART_FORM,
    ]
)
def test_get_format_media_type_no_extension(test_extension):
    fmt = f.get_format(test_extension)
    assert fmt == Format(test_extension, extension=None)
    assert fmt.extension == ""
    assert fmt.schema == ""


@pytest.mark.parametrize(
    "test_format",
    [
        "http://www.opengis.net/def/glossary/term/FeatureCollection",
        "https://geojson.org/schema/FeatureCollection.json",
    ]
)
def test_get_format_media_type_no_extension_with_schema(test_format):
    fmt = f.get_format(test_format)
    assert fmt.extension == ".geojson"
    assert fmt.mime_type == f.ContentType.APP_GEOJSON
    assert fmt.schema == test_format


@pytest.mark.parametrize(
    ["test_format", "expect_media_type"],
    [
        (
            "https://geojson.org/schema/FeatureCollection.json",
            f.ContentType.APP_GEOJSON,
        ),
        (
            "https://schemas.opengis.net/gmlcov/1.0/coverage.xsd",
            f.ContentType.APP_XML,
        ),
        (
            "https://example.com/unknown/reference.abc",
            f.ContentType.TEXT_PLAIN,
        ),
        (
            "https://example.com/unknown",
            f.ContentType.TEXT_PLAIN,
        )
    ]
)
def test_get_format_media_type_from_schema(test_format, expect_media_type):
    fmt = f.get_format(test_format)
    assert fmt.mime_type == expect_media_type


@pytest.mark.parametrize(
    ["test_extension", "default_content_type"],
    itertools.product(
        ["", None],
        [
            f.ContentType.APP_OCTET_STREAM,
            f.ContentType.APP_FORM,
            f.ContentType.MULTIPART_FORM,
        ]
    )
)
def test_get_format_default_no_extension(test_extension, default_content_type):
    fmt = f.get_format(test_extension, default=default_content_type)
    assert fmt == Format(default_content_type, extension=None)
    assert fmt.extension == ""


@pytest.mark.parametrize(
    ["cwl_format", "expect_media_type"],
    [
        (f"{f.IANA_NAMESPACE}:{f.ContentType.APP_JSON}", f.ContentType.APP_JSON),
        (f"{f.IANA_NAMESPACE_URL}{f.ContentType.APP_JSON}", f.ContentType.APP_JSON),
        (f"{f.IANA_NAMESPACE}:{f.ContentType.IMAGE_JPEG}", f.ContentType.IMAGE_JPEG),
        (f"{f.IANA_NAMESPACE_URL}{f.ContentType.IMAGE_JPEG}", f.ContentType.IMAGE_JPEG),
        (f"{f.EDAM_NAMESPACE}:{f.ContentType.APP_HDF5}", f.ContentType.APP_HDF5),
        (f"{f.EDAM_NAMESPACE_URL}{f.ContentType.APP_HDF5}", f.ContentType.APP_HDF5),
        (f"{f.EDAM_NAMESPACE}:{f.EDAM_MAPPING[f.ContentType.APP_HDF5]}", f.ContentType.APP_HDF5),
        (f"{f.EDAM_NAMESPACE_URL}{f.EDAM_MAPPING[f.ContentType.APP_HDF5]}", f.ContentType.APP_HDF5),
        (f"{f.EDAM_NAMESPACE}:does-not-exist", None),
        (f"{f.EDAM_NAMESPACE_URL}does-not-exist", None),
        (f"{f.EDAM_NAMESPACE}:format_123456", None),
        (f"{f.EDAM_NAMESPACE_URL}format_123456", None),
        ("application/unknown", "application/unknown"),
        ("custom:application/unknown", "application/unknown"),
        ("invalid-unknown", None),
    ]
)
def test_map_cwl_media_type(cwl_format, expect_media_type):
    result_media_type = f.map_cwl_media_type(cwl_format)
    assert result_media_type == expect_media_type


def test_get_cwl_file_format_tuple():
    untested = set(f.FORMAT_NAMESPACES)
    tests = [
        f.ContentType.APP_JSON,
        f.ContentType.APP_NETCDF,
        f.ContentType.APP_HDF5,
    ]
    for mime_type in tests:
        res = f.get_cwl_file_format(mime_type, make_reference=False)
        assert isinstance(res, tuple) and len(res) == 2
        ns, fmt = res
        assert isinstance(ns, dict) and len(ns) == 1
        assert any(fmt in ns for fmt in f.FORMAT_NAMESPACES)  # pylint: disable=E1135
        assert list(ns.values())[0].startswith("http")
        ns_name = list(ns.keys())[0]
        assert fmt.startswith(f"{ns_name}:")
        untested.remove(ns_name)
    for ns in list(untested):
        ns_map_name = f"{ns.upper()}_MAPPING"
        ns_map = getattr(f, ns_map_name, None)
        if ns_map is not None and len(ns_map) == 0:
            untested.remove(ns)  # ignore empty mappings
    assert len(untested) == 0, "test did not evaluate every namespace variation"


def test_get_cwl_file_format_reference():
    untested = set(f.FORMAT_NAMESPACES)
    tests = [
        (f.IANA_NAMESPACE_DEFINITION, f.ContentType.APP_JSON),
        (f.EDAM_NAMESPACE_DEFINITION, f.ContentType.APP_HDF5),
        (f.OGC_NAMESPACE_DEFINITION, f.ContentType.IMAGE_OGC_GEOTIFF),
    ]
    for ns, mime_type in tests:
        res = f.get_cwl_file_format(mime_type, make_reference=True)
        ns_name, ns_url = list(ns.items())[0]
        assert isinstance(res, str)
        assert res.startswith(ns_url), f"[{res}] does not start with [{ns_url}]"
        untested.remove(ns_name)
    for ns in list(untested):
        ns_map_name = f"{ns.upper()}_MAPPING"
        ns_map = getattr(f, ns_map_name, None)
        if ns_map is not None and len(ns_map) == 0:
            untested.remove(ns)  # ignore empty mappings
    assert len(untested) == 0, "test did not evaluate every namespace variation"


def test_get_cwl_file_format_unknown():
    res = f.get_cwl_file_format("application/unknown", make_reference=False, must_exist=True)
    assert isinstance(res, tuple)
    assert res == (None, None)
    res = f.get_cwl_file_format("application/unknown", make_reference=True, must_exist=True)
    assert res is None


def test_get_cwl_file_format_default():
    fmt = "application/unknown"
    iana_url = f.IANA_NAMESPACE_DEFINITION[f.IANA_NAMESPACE]
    iana_fmt = f"{f.IANA_NAMESPACE}:{fmt}"
    res = f.get_cwl_file_format("application/unknown", make_reference=False, must_exist=False)
    assert isinstance(res, tuple)
    assert res[0] == {f.IANA_NAMESPACE: iana_url}
    assert res[1] == iana_fmt
    res = f.get_cwl_file_format("application/unknown", make_reference=True, must_exist=False)
    assert res == iana_url + fmt


def test_get_cwl_file_format_retry_attempts():
    """
    Verifies that failing request will not immediately fail the MIME-type validation.
    """
    codes = {"codes": [HTTPOk.code, HTTPRequestTimeout.code]}  # note: used in reverse order (pop)

    def mock_request_extra(*_, **__):
        m_resp = Response()
        m_resp.status_code = codes["codes"].pop()
        return m_resp

    with mock.patch("weaver.utils.get_settings", return_value={"cache.request.enabled": "false"}):
        with mock.patch("requests.Session.request", side_effect=mock_request_extra) as mocked_request:
            _, fmt = f.get_cwl_file_format(f.ContentType.IMAGE_PNG)
            assert fmt == f"{f.IANA_NAMESPACE}:{f.ContentType.IMAGE_PNG}"
            assert mocked_request.call_count == 2


def test_get_cwl_file_format_retry_fallback_urlopen():
    """
    Verifies that failing request because of critical error still validate the MIME-type using the fallback.
    """
    def mock_connect_error(*_, **__):
        raise ConnectionError()

    @contextlib.contextmanager
    def mock_urlopen(*_, **__):
        yield HTTPOk()

    f.get_cwl_file_format.cache_clear()
    with mock.patch("weaver.utils.get_settings", return_value={"cache.request.enabled": "false"}):
        with mock.patch("requests.Session.request", side_effect=mock_connect_error) as mocked_request:
            with mock.patch("weaver.formats.urlopen", side_effect=mock_urlopen) as mocked_urlopen:
                _, fmt = f.get_cwl_file_format(f.ContentType.IMAGE_PNG)
                assert fmt == f"{f.IANA_NAMESPACE}:{f.ContentType.IMAGE_PNG}"
                assert mocked_request.call_count == 4, "Expected internally attempted 4 times (1 attempt + 3 retries)"
                assert mocked_urlopen.call_count == 1, "Expected internal fallback request calls"


def test_get_cwl_file_format_retry_fallback_ssl_error():
    def http_only_request_extra(method, url, *_, **__):
        if url.startswith("https://"):
            raise ConnectionError("fake SSL error")
        return request_extra(method, url, *_, **__)

    def http_only_urlopen(url, *_, **__):
        if url.startswith("https://"):
            raise URLError("urlopen fake SSL error: The handshake operation timed out")
        return urlopen(url, *_, **__)

    with mock.patch("weaver.utils.request_extra", side_effect=http_only_request_extra) as mocked_request_extra:
        with mock.patch("weaver.formats.urlopen", side_effect=http_only_urlopen) as mocked_urlopen:
            test_type = f"{f.IANA_NAMESPACE}:text/javascript"
            url_ctype = f"{f.IANA_NAMESPACE_URL}text/javascript"
            ns, ctype = f.get_cwl_file_format(test_type)
            assert ns == f.IANA_NAMESPACE_DEFINITION
            assert ctype == test_type
            assert mocked_urlopen.call_count == 1, "1 call for urllib approach as first attempt failing HTTPS SSL check"
            assert mocked_request_extra.call_count == 2, "2 calls should occur, 1 for HTTPS, 1 for HTTP fallback"
            assert mocked_request_extra.call_args_list[0].args == ("head", url_ctype)
            assert mocked_request_extra.call_args_list[1].args == ("head", url_ctype.replace("https://", "http://"))


def test_get_cwl_file_format_synonym():
    """
    Test handling of special non-official MIME-type that have a synonym redirection to an official one.
    """
    res = f.get_cwl_file_format(f.ContentType.APP_TAR_GZ, make_reference=False, must_exist=True, allow_synonym=False)
    assert res == (None, None), "Non-official MIME-type without allowed synonym should resolve as not-found"
    res = f.get_cwl_file_format(f.ContentType.APP_TAR_GZ, make_reference=False, must_exist=True, allow_synonym=True)
    assert isinstance(res, tuple)
    assert res != (None, None), "Synonym type should have been mapped to its base reference"
    assert res[1].split(":")[1] == f.ContentType.APP_GZIP, "Synonym type should have been mapped to its base reference"
    assert f.get_extension(f.ContentType.APP_TAR_GZ) == ".tar.gz", "Original extension resolution needed, not synonym"
    fmt = f.get_format(f.ContentType.APP_TAR_GZ)
    assert fmt.extension == ".tar.gz"
    assert fmt.mime_type == f.ContentType.APP_TAR_GZ
    # above tests validated that synonym is defined and works, so following must not use that synonym
    res = f.get_cwl_file_format(f.ContentType.APP_TAR_GZ, make_reference=True, must_exist=False, allow_synonym=True)
    assert res.endswith(f.ContentType.APP_TAR_GZ), \
        "Literal MIME-type expected instead of its existing synonym since non-official is allowed (must_exist=False)"


def test_clean_media_type_format_iana():
    iana_fmt = f"{f.IANA_NAMESPACE}:{f.ContentType.APP_JSON}"  # "iana:mime_type"
    res_type = f.clean_media_type_format(iana_fmt)
    assert res_type == f.ContentType.APP_JSON
    iana_url = list(f.IANA_NAMESPACE_DEFINITION.values())[0]
    iana_fmt = str(os.path.join(iana_url, f.ContentType.APP_JSON))
    res_type = f.clean_media_type_format(iana_fmt)
    assert res_type == f.ContentType.APP_JSON  # application/json


def test_clean_media_type_format_edam():
    mime_type, fmt = list(f.EDAM_MAPPING.items())[0]
    edam_fmt = f"{f.EDAM_NAMESPACE}:{fmt}"  # "edam:format_####"
    res_type = f.clean_media_type_format(edam_fmt)
    assert res_type == mime_type
    edam_fmt = str(os.path.join(list(f.EDAM_NAMESPACE_DEFINITION.values())[0], fmt))  # "edam-url/format_####"
    res_type = f.clean_media_type_format(edam_fmt)
    assert res_type == mime_type  # application/x-type


@pytest.mark.skipif(condition=not f.OPENGIS_MAPPING, reason="No OpenGIS format mappings defined to test")
def test_clean_media_type_format_opengis():
    mime_type, fmt = list(f.OPENGIS_MAPPING.items())[0]
    gis_fmt = f"{f.OPENGIS_NAMESPACE}:{fmt}"  # "opengis:####"
    res_type = f.clean_media_type_format(gis_fmt)
    assert res_type == mime_type
    gis_fmt = str(os.path.join(list(f.OPENGIS_NAMESPACE_DEFINITION.values())[0], fmt))
    res_type = f.clean_media_type_format(gis_fmt)
    assert res_type == mime_type  # application/x-type


def test_clean_media_type_format_ogc():
    mime_type, fmt = list(f.OGC_MAPPING.items())[0]
    ogc_fmt = f"{f.OGC_NAMESPACE}:{fmt}"  # "ogc:####"
    res_type = f.clean_media_type_format(ogc_fmt)
    assert res_type == mime_type
    ogc_fmt = str(os.path.join(list(f.OGC_NAMESPACE_DEFINITION.values())[0], fmt))
    res_type = f.clean_media_type_format(ogc_fmt)
    assert res_type == mime_type  # application/x-type


@pytest.mark.parametrize(
    ["expected_content_type", "test_content_type"],
    [
        (f.ContentType.APP_JSON, f.ContentType.APP_JSON),
        (f.ContentType.APP_JSON, f"{f.ContentType.APP_JSON}; charset=UTF-8"),
        (f.ContentType.APP_XML, f"{f.ContentType.APP_XML}; charset=UTF-8; version=1.0"),
        ("application/vnd.api+json", "application/vnd.api+json; charset=UTF-8"),
        ("application/vnd.api+json", "application/vnd.api+json"),
    ]
)
def test_clean_media_type_format_io_remove_extra_parameters(expected_content_type, test_content_type):
    res_type = f.clean_media_type_format(test_content_type, strip_parameters=True)
    assert res_type == expected_content_type


@pytest.mark.parametrize(
    ["expected_content_type", "test_content_type"],
    [
        (f.ContentType.APP_JSON, f.ContentType.APP_JSON),
        (f"{f.ContentType.APP_JSON}; charset=UTF-8", f"{f.ContentType.APP_JSON}; charset=UTF-8"),
        (f"{f.ContentType.APP_XML}; charset=UTF-8; version=1.0",
         f"{f.ContentType.APP_XML}; charset=UTF-8; version=1.0"),
        (f"{f.ContentType.APP_JSON}; charset=UTF-8", "application/vnd.api+json; charset=UTF-8"),
        (f.ContentType.APP_JSON, "application/vnd.api+json"),
    ]
)
def test_clean_media_type_format_io_strip_base_type(expected_content_type, test_content_type):
    res_type = f.clean_media_type_format(test_content_type, suffix_subtype=True)
    assert res_type == expected_content_type


@pytest.mark.parametrize(
    ["expected_content_type", "test_content_type"],
    [
        (f.ContentType.APP_JSON, f.ContentType.APP_JSON),
        (f.ContentType.APP_JSON, f"{f.ContentType.APP_JSON}; charset=UTF-8"),
        (f.ContentType.APP_XML, f"{f.ContentType.APP_XML}; charset=UTF-8; version=1.0"),
        (f.ContentType.APP_JSON, "application/vnd.api+json; charset=UTF-8"),
        (f.ContentType.APP_JSON, "application/vnd.api+json"),
    ]
)
def test_clean_media_type_format_io_strip_base_and_remove_parameters(expected_content_type, test_content_type):
    res_type = f.clean_media_type_format(test_content_type, suffix_subtype=True, strip_parameters=True)
    assert res_type == expected_content_type


@pytest.mark.parametrize(
    ["suffix_subtype", "strip_parameters"],
    itertools.product([True, False], repeat=2)
)
def test_clean_media_type_format_default(suffix_subtype, strip_parameters):
    assert f.clean_media_type_format("", suffix_subtype=suffix_subtype, strip_parameters=strip_parameters) is None


@pytest.mark.parametrize(
    ["accept", "query", "default", "user_agent", "source", "expect"],
    [
        (None, None, None, None, "default", f.ContentType.APP_JSON),
        (None, None, None, "Mozilla/5.0", "default", f.ContentType.APP_JSON),
        (None, None, None, "python-requests/1.2.3", "default", f.ContentType.APP_JSON),
        (None, None, f.ContentType.APP_XML, None, "default", f.ContentType.APP_XML),
        (None, None, f.ContentType.APP_XML, "Mozilla/5.0", "default", f.ContentType.APP_XML),
        (None, None, f.ContentType.APP_XML, "python-requests/1.2.3", "default", f.ContentType.APP_XML),
        (None, "unknown", None, None, "query", f.ContentType.APP_JSON),
        (None, f.OutputFormat.JSON, None, None, "query", f.ContentType.APP_JSON),
        (None, f.OutputFormat.HTML, None, None, "query", f.ContentType.TEXT_HTML),
        (f.ContentType.ANY, None, None, None, "default", f.ContentType.APP_JSON),
        (f.ContentType.ANY, None, f.ContentType.APP_XML, None, "default", f.ContentType.APP_XML),
        (f.ContentType.APP_JSON, None, None, None, "header", f.ContentType.APP_JSON),
        (f.ContentType.TEXT_HTML, None, None, None, "header", f.ContentType.TEXT_HTML),
    ]
)
def test_guess_target_format(accept, query, default, user_agent, source, expect):
    req = MockedRequest()
    if user_agent:
        req.headers["User-Agent"] = user_agent
    if accept:
        req.headers["Accept"] = accept
    if query:
        req.params["format"] = query
    fmt, src = f.guess_target_format(req, default=default, return_source=True, override_user_agent=True)
    assert src == source
    assert fmt == expect


def test_repr_json_default_string():
    obj_ref = object()
    values = {"test": obj_ref}
    expect = f"{{'test': {str(obj_ref)}}}"
    result = f.repr_json(values)
    assert result == expect


@pytest.mark.parametrize(
    ["test", "expect", "force_string"],
    [
        ("abc", "abc", True),
        (123, 123, False),
        (123, "123", True),
        ([1, 2], [1, 2], False),
        ([1, 2], "[1, 2]", True),
        ("[1, 2]", "[1, 2]", True),
        ({"a": 1}, {"a": 1}, False),
        ({"a": 1}, "{\"a\": 1}", True),
        ("{\"a\": 1}", "{\"a\": 1}", True),
        (null, str(null), False),
        (null, str(null), True),
    ]
)
def test_repr_json_force_string_handling(test, expect, force_string):
    result = f.repr_json(test, force_string=force_string, indent=None)
    assert result == expect


def test_repr_json_handle_datetime():
    values = {
        "date": datetime.datetime(2022, 6, 12, 11, 55, 44),
        "number": 123,
        "none": None
    }
    expect = inspect.cleandoc("""
        {
          "date": "2022-06-12T11:55:44",
          "number": 123,
          "none": null
        }
    """)
    result = f.repr_json(values)
    assert result == expect


@pytest.mark.parametrize(
    ["unknown_format", "default_format", "expect_format"],
    [
        (None, None, f.OutputFormat.JSON),
        ("random", None, f.OutputFormat.JSON),
        (uuid.uuid4(), None, f.OutputFormat.JSON),
        (None, f.OutputFormat.XML, f.OutputFormat.XML),
        ("random", f.OutputFormat.XML, f.OutputFormat.XML),
        (uuid.uuid4(), f.OutputFormat.XML, f.OutputFormat.XML),
    ]
)
def test_output_format_default(unknown_format, default_format, expect_format):
    assert f.OutputFormat.get(unknown_format, default=default_format) == expect_format


@pytest.mark.parametrize(
    "test_format",
    f.OutputFormat.values()
)
def test_output_format_values(test_format):
    # use a different/impossible 'default' just to make sure the actual default is not matched 'just by chance'
    output = f.OutputFormat.get(test_format, default="DEFAULT")  # type: ignore
    assert output == test_format


@pytest.mark.parametrize(
    ["test_format", "expect_type"],
    [
        (f.ContentType.APP_JSON, f.OutputFormat.JSON),
        (f.ContentType.APP_XML, f.OutputFormat.XML),
        (f.ContentType.TEXT_XML, f.OutputFormat.XML),
        (f.ContentType.TEXT_HTML, f.OutputFormat.HTML),
        (f.ContentType.TEXT_PLAIN, f.OutputFormat.TXT),
        (f.ContentType.APP_YAML, f.OutputFormat.YML),
    ]
)
def test_output_format_media_type(test_format, expect_type):
    # use a different/impossible 'default' just to make sure the actual default is not matched 'just by chance'
    output = f.OutputFormat.get(test_format, default="DEFAULT")  # type: ignore
    assert output == expect_type


@pytest.mark.parametrize(
    ["test_format", "allow_version", "expect_type"],
    [
        ("1.0.0", True, f.OutputFormat.XML),
        ("1.0.0", False, "DEFAULT"),
        ("2.0.0", True, f.OutputFormat.JSON),
        ("2.0.0", False, "DEFAULT"),
        ("other", True, "DEFAULT"),
        ("other", False, "DEFAULT"),
    ]
)
def test_output_format_version(test_format, allow_version, expect_type):
    # use a different/impossible 'default' just to make sure the actual default is not matched 'just by chance'
    output = f.OutputFormat.get(test_format, allow_version=allow_version, default="DEFAULT")  # type: ignore
    assert output == expect_type


@pytest.mark.parametrize(
    ["test_format", "expect_data"],
    [
        (
            "DEFAULT",
            {"data": [123]}
        ),
        (
            f.OutputFormat.JSON,
            {"data": [123]}
        ),
        (
            f.OutputFormat.YAML,
            inspect.cleandoc("""
            data:
            - 123
            """) + "\n"
        ),
        (
            f.OutputFormat.XML,
            inspect.cleandoc("""
            <?xml version="1.0" encoding="UTF-8" ?>
            <item>
            <data type="list">
            <item type="int">123</item>
            </data>
            </item>
            """).replace("\n", "").encode()
        ),
        (
            f.OutputFormat.XML_STR,
            # FIXME: 'encoding="UTF-8"' missing (https://github.com/vinitkumar/json2xml/pull/213)
            inspect.cleandoc("""
            <?xml version="1.0" ?>
            <item>
                <data type="list">
                    <item type="int">123</item>
                </data>
            </item>
            """).replace("    ", "\t")
        ),
    ]
)
def test_output_format_convert(test_format, expect_data):
    data = f.OutputFormat.convert({"data": [123]}, test_format)
    assert data == expect_data


@pytest.mark.parametrize(
    ["io_definition", "expected_media_type"],
    [
        ({}, None),
        (
            {"formats": [{"type": f.ContentType.APP_GEOJSON}]},
            [f.ContentType.APP_GEOJSON],
        ),
        (
            {"formats": [{"type": f.ContentType.IMAGE_JPEG}, {"type": f.ContentType.IMAGE_COG}]},
            [f.ContentType.IMAGE_JPEG, f.ContentType.IMAGE_COG],
        ),
        (
            {"formats": [{"type": f.ContentType.IMAGE_JPEG}, {"random": "ignore"}]},
            [f.ContentType.IMAGE_JPEG],
        ),
    ]
)
def test_find_supported_media_types(io_definition, expected_media_type):
    found_media_type = f.find_supported_media_types(io_definition)
    if isinstance(found_media_type, list):
        assert sorted(found_media_type) == sorted(expected_media_type)
    else:
        assert found_media_type == expected_media_type
