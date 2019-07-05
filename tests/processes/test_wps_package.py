# noinspection PyProtectedMember
from weaver.processes.wps_package import (
    _json2wps_datatype,
    _is_cwl_array_type,
    _is_cwl_enum_type,
    _merge_io_formats,
    DefaultFormat,
    WPS_LITERAL
)
from weaver.exceptions import PackageTypeError
from weaver.formats import CONTENT_TYPE_APP_NETCDF, CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_PLAIN
from pywps.inout.literaltypes import AnyValue
from pywps.inout.formats import Format
from pywps.validator.mode import MODE
from copy import deepcopy
# noinspection PyPackageRequirements
import pytest


def test_json2wps_datatype():
    test_cases = [
        ("float",   {"type": WPS_LITERAL, "data_type": "float"}),                       # noqa: E241
        ("integer", {"type": WPS_LITERAL, "data_type": "integer"}),                     # noqa: E241
        ("integer", {"type": WPS_LITERAL, "data_type": "int"}),                         # noqa: E241
        ("boolean", {"type": WPS_LITERAL, "data_type": "boolean"}),                     # noqa: E241
        ("boolean", {"type": WPS_LITERAL, "data_type": "bool"}),                        # noqa: E241
        ("string",  {"type": WPS_LITERAL, "data_type": "string"}),                      # noqa: E241
        ("float",   {"type": WPS_LITERAL, "default": 1.0}),                             # noqa: E241
        ("integer", {"type": WPS_LITERAL, "default": 1}),                               # noqa: E241
        ("boolean", {"type": WPS_LITERAL, "default": True}),                            # noqa: E241
        ("string",  {"type": WPS_LITERAL, "default": "1"}),                             # noqa: E241
        ("float",   {"type": WPS_LITERAL, "supported_values": [1.0, 2.0]}),             # noqa: E241
        ("integer", {"type": WPS_LITERAL, "supported_values": [1, 2]}),                 # noqa: E241
        ("boolean", {"type": WPS_LITERAL, "supported_values": [True, False]}),          # noqa: E241
        ("string",  {"type": WPS_LITERAL, "supported_values": ["yes", "no"]}),          # noqa: E241
        ("float",   {"data_type": "float"}),                                            # noqa: E241
        ("integer", {"data_type": "integer"}),                                          # noqa: E241
        ("integer", {"data_type": "int"}),                                              # noqa: E241
        ("boolean", {"data_type": "boolean"}),                                          # noqa: E241
        ("boolean", {"data_type": "bool"}),                                             # noqa: E241
        ("string",  {"data_type": "string"}),                                           # noqa: E241
    ]

    for expect, test_io in test_cases:
        copy_io = deepcopy(test_io)  # can get modified by function
        assert _json2wps_datatype(test_io) == expect, "Failed for [{}]".format(copy_io)


def test_is_cwl_array_type_explicit_invalid_item():
    io_info = {
        "name": "test",
        "type": {
            "type": "array",
            "items": "unknown-type-item"
        }
    }
    with pytest.raises(PackageTypeError):
        _is_cwl_array_type(io_info)


def test_is_cwl_array_type_shorthand_invalid_item():
    """
    In case of shorthand syntax, because type is only a string, it shouldn't raise.
    Type is returned as is and value validation is left to later calls.
    """
    io_info = {
        "name": "test",
        "type": "unknown[]"
    }
    try:
        res = _is_cwl_array_type(io_info)
        assert res[0] is False
        assert res[1] == "unknown[]"
        assert res[2] == MODE.NONE
        assert res[3] == AnyValue
    except PackageTypeError:
        pytest.fail("should not raise an error in this case")


def test_is_cwl_array_type_not_array():
    io_info = {
        "name": "test",
        "type": "float",
    }
    res = _is_cwl_array_type(io_info)
    assert res[0] is False
    assert res[1] == "float"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def test_is_cwl_array_type_simple_enum():
    io_info = {
        "name": "test",
        "type": "enum",
        "symbols": ["a", "b", "c"]
    }
    res = _is_cwl_array_type(io_info)
    assert res[0] is False
    assert res[1] == "enum"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def test_is_cwl_array_type_explicit_base():
    io_info = {
        "name": "test",
        "type": {
            "type": "array",
            "items": "string"
        }
    }
    res = _is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def test_is_cwl_array_type_explicit_enum():
    io_info = {
        "name": "test",
        "type": {
            "type": "array",
            "items": {
                "type": "enum",
                "symbols": ["a", "b", "c"]
            }
        }
    }
    res = _is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def test_is_cwl_array_type_shorthand_base():
    io_info = {
        "name": "test",
        "type": "string[]",
    }
    res = _is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def test_is_cwl_array_type_shorthand_enum():
    io_info = {
        "name": "test",
        "type": "enum[]",
        "symbols": ["a", "b", "c"]
    }
    res = _is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def test_is_cwl_enum_type_string():
    io_info = {
        "name": "test",
        "type": {
            "type": "enum",
            "symbols": ["a", "b", "c"]
        }
    }
    res = _is_cwl_enum_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def test_is_cwl_enum_type_float():
    io_info = {
        "name": "test",
        "type": {
            "type": "enum",
            "symbols": [1.9, 2.8, 3.7]
        }
    }
    res = _is_cwl_enum_type(io_info)
    assert res[0] is True
    assert res[1] == "float"
    assert res[2] == MODE.SIMPLE
    assert res[3] == [1.9, 2.8, 3.7]


def test_is_cwl_enum_type_int():
    io_info = {
        "name": "test",
        "type": {
            "type": "enum",
            "symbols": [1, 2, 3]
        }
    }
    res = _is_cwl_enum_type(io_info)
    assert res[0] is True
    assert res[1] == "int"
    assert res[2] == MODE.SIMPLE
    assert res[3] == [1, 2, 3]


def assert_formats_equal_any_order(format_result, format_expect):
    assert len(format_result) == len(format_expect), "Expected formats sizes mismatch"
    for r_fmt in format_result:
        for e_fmt in format_expect:
            if r_fmt.json == e_fmt.json:
                format_expect.remove(e_fmt)
                break
    assert not format_expect, "Not all expected formats matched {}".format([f.json for f in format_expect])


def test_merge_io_formats_no_wps():
    wps_fmt = []
    cwl_fmt = [DefaultFormat]
    res_fmt = _merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert len(res_fmt) == 1
    assert res_fmt[0] is DefaultFormat


def test_merge_io_formats_with_wps_and_default_cwl():
    wps_fmt = [Format(CONTENT_TYPE_APP_NETCDF)]
    cwl_fmt = [DefaultFormat]
    res_fmt = _merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert_formats_equal_any_order(res_fmt, [Format(CONTENT_TYPE_APP_NETCDF)])


def test_merge_io_formats_both_wps_and_cwl():
    wps_fmt = [Format(CONTENT_TYPE_APP_NETCDF)]
    cwl_fmt = [Format(CONTENT_TYPE_APP_JSON)]
    res_fmt = _merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert_formats_equal_any_order(res_fmt, [Format(CONTENT_TYPE_APP_NETCDF), Format(CONTENT_TYPE_APP_JSON)])


def test_merge_io_formats_wps_complements_cwl():
    wps_fmt = [Format(CONTENT_TYPE_APP_JSON, encoding="utf-8")]
    cwl_fmt = [Format(CONTENT_TYPE_APP_JSON)]
    res_fmt = _merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert_formats_equal_any_order(res_fmt, [Format(CONTENT_TYPE_APP_JSON, encoding="utf-8")])


def test_merge_io_formats_wps_overlaps_cwl():
    wps_fmt = [
        Format(CONTENT_TYPE_APP_JSON, encoding="utf-8"),    # complements CWL details
        Format(CONTENT_TYPE_APP_NETCDF),                    # duplicated in CWL (but different index)
        Format(CONTENT_TYPE_TEXT_PLAIN)                     # extra (but not default)
    ]
    cwl_fmt = [
        Format(CONTENT_TYPE_APP_JSON),      # overridden by WPS version
        Format(CONTENT_TYPE_APP_XML),       # extra preserved
        Format(CONTENT_TYPE_APP_NETCDF),    # duplicated with WPS, merged
    ]
    res_fmt = _merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert_formats_equal_any_order(res_fmt, [
        Format(CONTENT_TYPE_APP_JSON, encoding="utf-8"),
        Format(CONTENT_TYPE_APP_NETCDF),
        Format(CONTENT_TYPE_APP_XML),
        Format(CONTENT_TYPE_TEXT_PLAIN),
    ])
