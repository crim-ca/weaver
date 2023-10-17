import datetime
import inspect
import itertools
import os

import mock
import pytest
from pyramid.httpexceptions import HTTPOk, HTTPRequestTimeout
from pyramid.response import Response
from pywps.inout.formats import Format
from requests.exceptions import ConnectionError

from weaver import formats as f


@pytest.mark.parametrize(
    ["test_extension", "extra_params", "expected_content_type"],
    [
        (f.ContentType.APP_JSON, {}, ".json"),  # basic
        (f"{f.ContentType.APP_JSON}; charset=UTF-8", {}, ".json"),  # ignore extra parameters
        (f.ContentType.APP_GEOJSON, {}, ".geojson"),  # pywps <4.4 definition
        (f.ContentType.APP_VDN_GEOJSON, {}, ".geojson"),  # pywps>=4.4 definition
        (f.ContentType.IMAGE_GEOTIFF, {}, ".tiff"),  # pywps definition
        ("application/x-custom", {}, ".custom"),
        ("application/unknown", {}, ".unknown"),
        (f.ContentType.APP_DIR, {"dot": True}, "/"),
        (f.ContentType.APP_DIR, {"dot": False}, "/"),
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
def test_content_encoding_encode(data, encoding, binary, result):
    assert f.ContentEncoding.encode(data, encoding, binary) == result


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
        f.ContentType.MULTI_PART_FORM,
    ]
)
def test_get_format_media_type_no_extension(test_extension):
    fmt = f.get_format(test_extension)
    assert fmt == Format(test_extension, extension=None)
    assert fmt.extension == ""


@pytest.mark.parametrize(
    ["test_extension", "default_content_type"],
    itertools.product(
        ["", None],
        [
            f.ContentType.APP_OCTET_STREAM,
            f.ContentType.APP_FORM,
            f.ContentType.MULTI_PART_FORM,
        ]
    )
)
def test_get_format_default_no_extension(test_extension, default_content_type):
    fmt = f.get_format(test_extension, default=default_content_type)
    assert fmt == Format(default_content_type, extension=None)
    assert fmt.extension == ""


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

    def mock_urlopen(*_, **__):
        return HTTPOk()

    with mock.patch("weaver.utils.get_settings", return_value={"cache.request.enabled": "false"}):
        with mock.patch("requests.Session.request", side_effect=mock_connect_error) as mocked_request:
            with mock.patch("weaver.formats.urlopen", side_effect=mock_urlopen) as mocked_urlopen:
                _, fmt = f.get_cwl_file_format(f.ContentType.IMAGE_PNG)
                assert fmt == f"{f.IANA_NAMESPACE}:{f.ContentType.IMAGE_PNG}"
                assert mocked_request.call_count == 4, "Expected internally attempted 4 times (1 attempt + 3 retries)"
                assert mocked_urlopen.call_count == 1, "Expected internal fallback request calls"


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


def test_clean_mime_type_format_iana():
    iana_fmt = f"{f.IANA_NAMESPACE}:{f.ContentType.APP_JSON}"  # "iana:mime_type"
    res_type = f.clean_mime_type_format(iana_fmt)
    assert res_type == f.ContentType.APP_JSON
    iana_url = list(f.IANA_NAMESPACE_DEFINITION.values())[0]
    iana_fmt = os.path.join(iana_url, f.ContentType.APP_JSON)
    res_type = f.clean_mime_type_format(iana_fmt)
    assert res_type == f.ContentType.APP_JSON  # application/json


def test_clean_mime_type_format_edam():
    mime_type, fmt = list(f.EDAM_MAPPING.items())[0]
    edam_fmt = f"{f.EDAM_NAMESPACE}:{fmt}"  # "edam:format_####"
    res_type = f.clean_mime_type_format(edam_fmt)
    assert res_type == mime_type
    edam_fmt = os.path.join(list(f.EDAM_NAMESPACE_DEFINITION.values())[0], fmt)  # "edam-url/format_####"
    res_type = f.clean_mime_type_format(edam_fmt)
    assert res_type == mime_type  # application/x-type


@pytest.mark.skipif(condition=not f.OPENGIS_MAPPING, reason="No OpenGIS format mappings defined to test")
def test_clean_mime_type_format_opengis():
    mime_type, fmt = list(f.OPENGIS_MAPPING.items())[0]
    gis_fmt = f"{f.OPENGIS_NAMESPACE}:{fmt}"  # "opengis:####"
    res_type = f.clean_mime_type_format(gis_fmt)
    assert res_type == mime_type
    gis_fmt = os.path.join(list(f.OPENGIS_NAMESPACE_DEFINITION.values())[0], fmt)
    res_type = f.clean_mime_type_format(gis_fmt)
    assert res_type == mime_type  # application/x-type


def test_clean_mime_type_format_ogc():
    mime_type, fmt = list(f.OGC_MAPPING.items())[0]
    ogc_fmt = f"{f.OGC_NAMESPACE}:{fmt}"  # "ogc:####"
    res_type = f.clean_mime_type_format(ogc_fmt)
    assert res_type == mime_type
    ogc_fmt = os.path.join(list(f.OGC_NAMESPACE_DEFINITION.values())[0], fmt)
    res_type = f.clean_mime_type_format(ogc_fmt)
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
def test_clean_mime_type_format_io_remove_extra_parameters(expected_content_type, test_content_type):
    res_type = f.clean_mime_type_format(test_content_type, strip_parameters=True)
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
def test_clean_mime_type_format_io_strip_base_type(expected_content_type, test_content_type):
    res_type = f.clean_mime_type_format(test_content_type, suffix_subtype=True)
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
def test_clean_mime_type_format_io_strip_base_and_remove_parameters(expected_content_type, test_content_type):
    res_type = f.clean_mime_type_format(test_content_type, suffix_subtype=True, strip_parameters=True)
    assert res_type == expected_content_type


@pytest.mark.parametrize(
    ["suffix_subtype", "strip_parameters"],
    itertools.product([True, False], repeat=2)
)
def test_clean_mime_type_format_default(suffix_subtype, strip_parameters):
    assert f.clean_mime_type_format("", suffix_subtype=suffix_subtype, strip_parameters=strip_parameters) is None


def test_repr_json_default_string():
    obj_ref = object()
    values = {"test": obj_ref}
    expect = f"{{'test': {str(obj_ref)}}}"
    result = f.repr_json(values)
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
