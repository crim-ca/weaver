"""
Unit tests of functions within :mod:`weaver.processes.convert`.
"""
# pylint: disable=R1729  # ignore non-generator representation employed for displaying test log results

from collections import OrderedDict
from copy import deepcopy

import pytest
from pywps.inout.formats import Format
from pywps.inout.inputs import LiteralInput
from pywps.inout.literaltypes import AllowedValue, AnyValue
from pywps.inout.outputs import ComplexOutput
from pywps.validator.mode import MODE

from weaver.exceptions import PackageTypeError
from weaver.formats import ContentType
from weaver.processes.constants import WPS_INPUT, WPS_LITERAL, WPS_OUTPUT, ProcessSchema
from weaver.processes.convert import _are_different_and_set  # noqa: W0212
from weaver.processes.convert import (
    DEFAULT_FORMAT,
    PACKAGE_ARRAY_MAX_SIZE,
    convert_input_values_schema,
    cwl2json_input_values,
    cwl2wps_io,
    is_cwl_array_type,
    is_cwl_enum_type,
    is_cwl_file_type,
    json2wps_allowed_values,
    json2wps_datatype,
    merge_io_formats,
    normalize_ordered_io,
    repr2json_input_values
)
from weaver.utils import null


class ObjectWithEqProperty(object):
    """
    Dummy object for some test evaluations.
    """
    _prop = "prop"

    def __init__(self, prop="prop"):
        self._prop = prop

    @property
    def some_property(self):
        return self._prop

    def __eq__(self, other):
        return self.some_property == other.some_property


def test_are_different_and_set_both_set():
    assert _are_different_and_set(1, 2) is True
    assert _are_different_and_set(1, 1) is False
    assert _are_different_and_set({"a": 1}, {"a": 2}) is True
    assert _are_different_and_set({"a": 1}, {"a": 1}) is False
    assert _are_different_and_set({"a": 1, "b": 2}, {"a": 1}) is True
    assert _are_different_and_set(ObjectWithEqProperty(), ObjectWithEqProperty()) is False
    assert _are_different_and_set(ObjectWithEqProperty("a"), ObjectWithEqProperty("b")) is True


def test_are_different_and_set_similar_str_formats():
    assert _are_different_and_set(b"something", u"something") is False
    assert _are_different_and_set(u"something", u"something") is False
    assert _are_different_and_set(b"something", b"something") is False
    assert _are_different_and_set(b"something", u"else") is True
    assert _are_different_and_set(u"something", u"else") is True
    assert _are_different_and_set(b"something", b"else") is True


def test_are_different_and_set_both_null():
    assert _are_different_and_set(null, null) is False


def test_are_different_and_set_single_null():
    """
    Tests that equality check is correctly handled when a single item amongst the two is ``null``.

    This was identified as problematic is case when the checked and set item implements ``__eq__`` and expects a
    property to exist, which is not the case for the second item being ``null``.
    """

    item = ObjectWithEqProperty()
    assert _are_different_and_set(item, null) is False
    assert _are_different_and_set(null, item) is False


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
        assert json2wps_datatype(test_io) == expect, "Failed for [{}]".format(copy_io)


def test_json2wps_allowed_values():
    for i, (values, expect) in enumerate([
        ({"allowedvalues": [1, 2, 3]},
         [AllowedValue(value=1), AllowedValue(value=2), AllowedValue(value=3)]),
        ({"allowedvalues": ["A", "B"]},
         [AllowedValue(value="A"), AllowedValue(value="B")]),
        ({"allowedvalues": [{"closure": "open", "minimum": 1, "maximum": 5}]},
         [AllowedValue(minval=1, maxval=5, range_closure="open")]),
        ({"allowedvalues": [{"closure": "open-closed", "minimum": 0, "maximum": 6, "spacing": 2}]},
         [AllowedValue(minval=0, maxval=6, spacing=2, range_closure="open-closed")]),
        ({"literalDataDomains": [{"valueDefinition": [1, 2, 3]}]},
         [AllowedValue(value=1), AllowedValue(value=2), AllowedValue(value=3)]),
        ({"literalDataDomains": [{"valueDefinition": ["A", "B"]}]},
         [AllowedValue(value="A"), AllowedValue(value="B")]),
        ({"literalDataDomains": [{"valueDefinition": [{"closure": "open", "minimum": 1, "maximum": 5}]}]},
         [AllowedValue(minval=1, maxval=5, range_closure="open")]),
        ({"literalDataDomains": [
            {"valueDefinition": [{"closure": "open-closed", "minimum": 0, "maximum": 6, "spacing": 2}]}]},
         [AllowedValue(minval=0, maxval=6, spacing=2, range_closure="open-closed")]),
    ]):
        result = json2wps_allowed_values(values)
        assert result == expect, "Failed test {}".format(i)


def test_cwl2wps_io_null_or_array_of_enums():
    """
    I/O `CWL` with ``["null", "<enum-type>", "<array-enum-type>]`` must be parsed as `WPS` with parameters
    ``minOccurs=0``, ``maxOccurs>1`` and ``allowedValues`` as restricted set of values.
    """
    allowed_values = ["A", "B", "C"]
    io_info = {
        "name": "test",
        "type": [
            "null",  # minOccurs=0
            {"type": "enum", "symbols": allowed_values},  # if maxOccurs=1, only this variant would be provided
            {"type": "array", "items": {"type": "enum", "symbols": allowed_values}},  # but also this for maxOccurs>1
        ],
    }
    wps_io = cwl2wps_io(io_info, WPS_INPUT)
    assert isinstance(wps_io, LiteralInput)
    assert wps_io.min_occurs == 0
    assert wps_io.max_occurs == PACKAGE_ARRAY_MAX_SIZE
    assert wps_io.data_type == "string"
    assert wps_io.allowed_values == [AllowedValue(value=val) for val in allowed_values]


def test_cwl2wps_io_raise_mixed_types():
    io_type1 = ["string", "int"]
    io_type2 = [
        "int",
        {"type": "array", "items": "string"}
    ]
    io_type3 = [
        {"type": "enum", "symbols": ["1", "2"]},  # symbols as literal strings != int literal
        "null",
        "int"
    ]
    io_type4 = [
        "null",
        {"type": "enum", "symbols": ["1", "2"]},  # symbols as literal strings != int items
        {"type": "array", "items": "int"}
    ]
    for i, test_type in enumerate([io_type1, io_type2, io_type3, io_type4]):
        io_info = {"name": "test-{}".format(i), "type": test_type}
        with pytest.raises(PackageTypeError):
            cwl2wps_io(io_info, WPS_INPUT)


def test_cwl2wps_io_record_format():
    """
    Validate handling of alternative representation by CWL I/O record after parsing contents into a tool instance.

    CWL record for an application named ``package`` rewrites ``format`` field of a ``File`` I/O
    originally defined as ``iana:application/json`` to ``file:///tmp/<tmpXYZ>/package#application/json``
    after it resolved the remote ontology ``iana`` from ``$namespace``.
    """
    cwl_io_record = {
        "name": "output",
        "type": "File",
        "outputBinding": {"glob": "*.json"},
        "format": f"file:///tmp/tmp-random-dir/package#{ContentType.APP_JSON}",
    }
    wps_io = cwl2wps_io(cwl_io_record, WPS_OUTPUT)
    assert isinstance(wps_io, ComplexOutput)
    assert len(wps_io.supported_formats) == 1
    assert isinstance(wps_io.supported_formats[0], Format)
    assert wps_io.supported_formats[0].mime_type == ContentType.APP_JSON


def testis_cwl_array_type_explicit_invalid_item():
    io_info = {
        "name": "test",
        "type": {
            "type": "array",
            "items": "unknown-type-item"
        }
    }
    with pytest.raises(PackageTypeError):
        is_cwl_array_type(io_info)


def testis_cwl_array_type_shorthand_invalid_item():
    """
    In case of shorthand syntax, because type is only a string, it shouldn't raise.

    Type is returned as is and value validation is left to later calls.
    """
    io_info = {
        "name": "test",
        "type": "unknown[]"
    }
    try:
        res = is_cwl_array_type(io_info)
        assert res[0] is False
        assert res[1] == "unknown[]"
        assert res[2] == MODE.NONE
        assert res[3] == AnyValue
    except PackageTypeError:
        pytest.fail("should not raise an error in this case")


def testis_cwl_array_type_not_array():
    io_info = {
        "name": "test",
        "type": "float",
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is False
    assert res[1] == "float"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def testis_cwl_array_type_simple_enum():
    io_info = {
        "name": "test",
        "type": "enum",
        "symbols": ["a", "b", "c"]
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is False
    assert res[1] == "enum"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def testis_cwl_array_type_explicit_base():
    io_info = {
        "name": "test",
        "type": {
            "type": "array",
            "items": "string"
        }
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def testis_cwl_array_type_explicit_enum():
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
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def testis_cwl_array_type_shorthand_base():
    io_info = {
        "name": "test",
        "type": "string[]",
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def testis_cwl_array_type_shorthand_enum():
    io_info = {
        "name": "test",
        "type": "enum[]",
        "symbols": ["a", "b", "c"]
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def testis_cwl_array_type_explicit_optional_not_array():
    io_info = {
        "name": "test",
        "type": ["null", "float"],
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is False
    assert res[1] == "float"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def testis_cwl_array_type_explicit_optional_simple_enum():
    io_info = {
        "name": "test",
        "type": ["null", "enum"],
        "symbols": ["a", "b", "c"]
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is False
    assert res[1] == "enum"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def testis_cwl_array_type_explicit_optional_explicit_base():
    io_info = {
        "name": "test",
        "type": [
            "null",
            {"type": "array", "items": "string"}
        ]
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def testis_cwl_array_type_explicit_optional_explicit_enum():
    io_info = {
        "name": "test",
        "type": [
            "null",
            {
                "type": "array",
                "items": {
                    "type": "enum",
                    "symbols": ["a", "b", "c"]
                }
            }
        ]
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def testis_cwl_array_type_explicit_optional_shorthand_base():
    io_info = {
        "name": "test",
        "type": ["null", "string[]"]
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def testis_cwl_array_type_explicit_optional_shorthand_enum():
    io_info = {
        "name": "test",
        "type": ["null", "enum[]"],
        "symbols": ["a", "b", "c"]
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def testis_cwl_enum_type_string():
    io_info = {
        "name": "test",
        "type": {
            "type": "enum",
            "symbols": ["a", "b", "c"]
        }
    }
    res = is_cwl_enum_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def testis_cwl_enum_type_float():
    io_info = {
        "name": "test",
        "type": {
            "type": "enum",
            "symbols": [1.9, 2.8, 3.7]
        }
    }
    res = is_cwl_enum_type(io_info)
    assert res[0] is True
    assert res[1] == "float"
    assert res[2] == MODE.SIMPLE
    assert res[3] == [1.9, 2.8, 3.7]


def testis_cwl_enum_type_int():
    io_info = {
        "name": "test",
        "type": {
            "type": "enum",
            "symbols": [1, 2, 3]
        }
    }
    res = is_cwl_enum_type(io_info)
    assert res[0] is True
    assert res[1] == "int"
    assert res[2] == MODE.SIMPLE
    assert res[3] == [1, 2, 3]


def test_is_cwl_file_type_guaranteed_file():
    io_info = {
        "name": "test",
        "type": "File"
    }
    assert is_cwl_file_type(io_info)


def test_is_cwl_file_type_potential_file():
    io_info = {
        "name": "test",
        "type": ["null", "File"]
    }
    assert is_cwl_file_type(io_info)


def test_is_cwl_file_type_file_array():
    io_info = {
        "name": "test",
        "type": {"type": "array", "items": "File"}
    }
    assert is_cwl_file_type(io_info)


def test_is_cwl_file_type_none_one_or_many_files():
    io_info = {
        "name": "test",
        "type": [
            "null",
            "File",
            {"type": "array", "items": "File"}
        ]
    }
    assert is_cwl_file_type(io_info)


def test_is_cwl_file_type_not_files():
    test_types = [
        "int",
        "string",
        "float",
        ["null", "string"],
        {"type": "enum", "symbols": [1, 2]},
        {"type": "enum", "symbols": ["A", "B"]},
        {"type": "array", "items": "string"},
        {"type": "array", "items": "int"},
        ["null", {"type": "array", "items": "string"}],
    ]
    for i, io_type in enumerate(test_types):
        io_info = {"name": "test-{}".format(i), "type": io_type}
        assert not is_cwl_file_type(io_info), "Test [{}]: {}".format(i, io_info)


def assert_formats_equal_any_order(format_result, format_expect):
    assert len(format_result) == len(format_expect), "Expected formats sizes mismatch"
    for r_fmt in format_result:
        for e_fmt in format_expect:
            if r_fmt.json == e_fmt.json:
                format_expect.remove(e_fmt)
                break
    assert not format_expect, "Not all expected formats matched {}".format([fmt.json for fmt in format_expect])


def test_merge_io_formats_no_wps():
    wps_fmt = []
    cwl_fmt = [DEFAULT_FORMAT]
    res_fmt = merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert len(res_fmt) == 1
    assert res_fmt[0] is DEFAULT_FORMAT


def test_merge_io_formats_with_wps_and_default_cwl():
    wps_fmt = [Format(ContentType.APP_NETCDF)]
    cwl_fmt = [DEFAULT_FORMAT]
    res_fmt = merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert_formats_equal_any_order(res_fmt, [Format(ContentType.APP_NETCDF)])


def test_merge_io_formats_both_wps_and_cwl():
    wps_fmt = [Format(ContentType.APP_NETCDF)]
    cwl_fmt = [Format(ContentType.APP_JSON)]
    res_fmt = merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert_formats_equal_any_order(res_fmt, [Format(ContentType.APP_NETCDF), Format(ContentType.APP_JSON)])


def test_merge_io_formats_wps_complements_cwl():
    wps_fmt = [Format(ContentType.APP_JSON, encoding="utf-8")]
    cwl_fmt = [Format(ContentType.APP_JSON)]
    res_fmt = merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert_formats_equal_any_order(res_fmt, [Format(ContentType.APP_JSON, encoding="utf-8")])


def test_merge_io_formats_wps_overlaps_cwl():
    wps_fmt = [
        Format(ContentType.APP_JSON, encoding="utf-8"),    # complements CWL details
        Format(ContentType.APP_NETCDF),                    # duplicated in CWL (but different index)
        Format(ContentType.TEXT_PLAIN)                     # extra (but not default)
    ]
    cwl_fmt = [
        Format(ContentType.APP_JSON),      # overridden by WPS version
        Format(ContentType.APP_XML),       # extra preserved
        Format(ContentType.APP_NETCDF),    # duplicated with WPS, merged
    ]
    res_fmt = merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert_formats_equal_any_order(res_fmt, [
        Format(ContentType.APP_JSON, encoding="utf-8"),
        Format(ContentType.APP_NETCDF),
        Format(ContentType.APP_XML),
        Format(ContentType.TEXT_PLAIN),
    ])


def test_normalize_ordered_io_with_builtin_dict_and_hints():
    """
    Validate that I/O are all still there in the results with their respective contents.

    Literal types should be modified to a dictionary with ``type`` key.
    All dictionary contents should then remain as is, except with added ``id``.

    .. note::
        Ordering is not mandatory, so we don't validate this.
        Also actually hard to test since employed python version running the test changes the behaviour.
    """
    test_inputs = {
        "id-literal-type": "float",
        "id-dict-details": {
            "type": "string"
        },
        "id-array-type": {
            "type": {
                "type": "array",
                "items": "float"
            }
        },
        "id-literal-array": "string[]"
    }
    test_wps_hints = [
        {"id": "id-literal-type"},
        {"id": "id-array-type"},
        {"id": "id-dict-with-more-stuff"},
        {"id": "id-dict-details"},
    ]
    expected_result = [
        {"id": "id-literal-type", "type": "float"},
        {"id": "id-dict-details", "type": "string"},
        {"id": "id-array-type", "type": {"type": "array", "items": "float"}},
        {"id": "id-literal-array", "type": "string[]"}
    ]
    result = normalize_ordered_io(test_inputs, test_wps_hints)
    assert isinstance(result, list) and len(result) == len(expected_result)
    # *maybe* not same order, so validate values accordingly
    for expect in expected_result:
        validated = False
        for res in result:
            if res["id"] == expect["id"]:
                assert res == expect
                validated = True
        if not validated:
            raise AssertionError("expected '{}' was not validated against any result value".format(expect["id"]))


def test_normalize_ordered_io_with_ordered_dict():
    test_inputs = OrderedDict([
        ("id-literal-type", "float"),
        ("id-dict-details", {"type": "string"}),
        ("id-array-type", {
            "type": {
                "type": "array",
                "items": "float"
            }
        }),
        ("id-literal-array", "string[]"),
    ])
    expected_result = [
        {"id": "id-literal-type", "type": "float"},
        {"id": "id-dict-details", "type": "string"},
        {"id": "id-array-type", "type": {"type": "array", "items": "float"}},
        {"id": "id-literal-array", "type": "string[]"}
    ]
    result = normalize_ordered_io(test_inputs)
    assert isinstance(result, list) and len(result) == len(expected_result)
    assert result == expected_result


def test_normalize_ordered_io_with_list():
    """
    Everything should remain the same as list variant is only allowed to have I/O objects.

    (i.e.: not allowed to have both objects and literal string-type simultaneously as for dictionary variant).
    """
    expected_result = [
        {"id": "id-literal-type", "type": "float"},
        {"id": "id-dict-details", "type": "string"},
        {"id": "id-array-type", "type": {"type": "array", "items": "float"}},
        {"id": "id-literal-array", "type": "string[]"}
    ]
    result = normalize_ordered_io(deepcopy(expected_result))
    assert isinstance(result, list) and len(result) == len(expected_result)
    assert result == expected_result


def test_normalize_ordered_io_when_direct_type_string():
    inputs_as_strings = {
        "input-1": "File[]",
        "input-2": "float"
    }
    result = normalize_ordered_io(inputs_as_strings)
    assert isinstance(result, list)
    assert len(result) == len(inputs_as_strings)
    assert all([isinstance(res_i, dict) for res_i in result])
    assert all([i in [res_i["id"] for res_i in result] for i in inputs_as_strings])
    assert all(["type" in res_i and res_i["type"] == inputs_as_strings[res_i["id"]] for res_i in result])


def test_cwl2json_input_values_ogc_format():
    values = {
        "test1": "value",
        "test2": 1,
        "test3": 1.23,
        "test4": {"class": "File", "path": "/tmp/random.txt"},
        "test5": ["val1", "val2"],
        "test6": [1, 2],
        "test7": [1.23, 4.56],
        "test8": [{"class": "File", "path": "/tmp/other.txt"}]
    }
    expect = {
        "test1": {"value": "value"},
        "test2": {"value": 1},
        "test3": {"value": 1.23},
        "test4": {"href": "/tmp/random.txt"},
        "test5": [{"value": "val1"}, {"value": "val2"}],
        "test6": [{"value": 1}, {"value": 2}],
        "test7": [{"value": 1.23}, {"value": 4.56}],
        "test8": [{"href": "/tmp/other.txt"}]
    }
    result = cwl2json_input_values(values, ProcessSchema.OGC)
    assert result == expect


def test_cwl2json_input_values_old_format():
    values = {
        "test1": "value",
        "test2": 1,
        "test3": 1.23,
        "test4": {"class": "File", "path": "/tmp/random.txt"},
        "test5": ["val1", "val2"],
        "test6": [1, 2],
        "test7": [1.23, 4.56],
        "test8": [{"class": "File", "path": "/tmp/other.txt"}]
    }
    expect = [
        {"id": "test1", "value": "value"},
        {"id": "test2", "value": 1},
        {"id": "test3", "value": 1.23},
        {"id": "test4", "href": "/tmp/random.txt"},
        {"id": "test5", "value": "val1"},
        {"id": "test5", "value": "val2"},
        {"id": "test6", "value": 1},
        {"id": "test6", "value": 2},
        {"id": "test7", "value": 1.23},
        {"id": "test7", "value": 4.56},
        {"id": "test8", "href": "/tmp/other.txt"}
    ]
    result = cwl2json_input_values(values, ProcessSchema.OLD)
    assert result == expect


def test_convert_input_values_schema_from_old():
    inputs_old = [
        {"id": "test1", "value": "data"},
        {"id": "test2", "value": 1},
        {"id": "test3", "value": 1.23},
        {"id": "test4", "href": "/data/random.txt"},
        {"id": "test5", "value": ["val1", "val2"]},
        {"id": "test6", "value": [1, 2]},
        {"id": "test7", "value": [1.23, 4.56]},
        {"id": "test8", "href": "/data/other.txt"},
        {"id": "test9", "value": "short"},
        {"id": "test10", "value": "long"},
        {"id": "test10", "value": "more"},
        {"id": "test11", "href": "/data/file1.txt", "format": {"mediaType": "text/plain"}},
        {"id": "test11", "href": "/data/file2.txt", "format": {"mediaType": "text/plain"}},
    ]
    inputs_ogc = {
        "test1": "data",
        "test2": 1,
        "test3": 1.23,
        "test4": {"href": "/data/random.txt"},
        "test5": ["val1", "val2"],
        "test6": [1, 2],
        "test7": [1.23, 4.56],
        "test8": {"href": "/data/other.txt"},
        "test9": "short",
        "test10": ["long", "more"],
        "test11": [
            {"href": "/data/file1.txt", "format": {"mediaType": "text/plain"}},
            {"href": "/data/file2.txt", "format": {"mediaType": "text/plain"}}
        ]
    }
    assert convert_input_values_schema(inputs_old, ProcessSchema.OLD) == inputs_old
    assert convert_input_values_schema(inputs_old, ProcessSchema.OGC) == inputs_ogc


def test_convert_input_values_schema_from_ogc():
    inputs_ogc = {
        "test1": "data",
        "test2": 1,
        "test3": 1.23,
        "test4": {"href": "/data/random.txt"},
        "test5": ["val1", "val2"],
        "test6": [1, 2],
        "test7": [1.23, 4.56],
        "test8": {"href": "/data/other.txt"},
        "test9": "short",
        "test10": ["long", "more"],
        "test11": [
            {"href": "/data/file1.txt", "format": {"mediaType": "text/plain"}},
            {"href": "/data/file2.txt", "format": {"mediaType": "text/plain"}}
        ]
    }
    inputs_old = [
        {"id": "test1", "value": "data"},
        {"id": "test2", "value": 1},
        {"id": "test3", "value": 1.23},
        {"id": "test4", "href": "/data/random.txt"},
        {"id": "test5", "value": "val1"},
        {"id": "test5", "value": "val2"},
        {"id": "test6", "value": 1},
        {"id": "test6", "value": 2},
        {"id": "test7", "value": 1.23},
        {"id": "test7", "value": 4.56},
        {"id": "test8", "href": "/data/other.txt"},
        {"id": "test9", "value": "short"},
        {"id": "test10", "value": "long"},
        {"id": "test10", "value": "more"},
        {"id": "test11", "href": "/data/file1.txt", "format": {"mediaType": "text/plain"}},
        {"id": "test11", "href": "/data/file2.txt", "format": {"mediaType": "text/plain"}},
    ]
    assert convert_input_values_schema(inputs_ogc, ProcessSchema.OGC) == inputs_ogc
    assert convert_input_values_schema(inputs_ogc, ProcessSchema.OLD) == inputs_old


def test_repr2json_input_values():
    values = [
        "test1=value",
        "test2:int=1",
        "test3:float=1.23",
        "test4:File=/tmp/random.txt",
        "test5=val1;val2",
        "test6:int=1;2",
        "test7:float=1.23;4.56",
        "test8:file=/tmp/other.txt",
        "test9:str=short",
        "test10:string=long",
    ]
    expect = [
        {"id": "test1", "value": "value"},
        {"id": "test2", "value": 1},
        {"id": "test3", "value": 1.23},
        {"id": "test4", "href": "/tmp/random.txt"},
        {"id": "test5", "value": ["val1", "val2"]},
        {"id": "test6", "value": [1, 2]},
        {"id": "test7", "value": [1.23, 4.56]},
        {"id": "test8", "href": "/tmp/other.txt"},
        {"id": "test9", "value": "short"},
        {"id": "test10", "value": "long"}
    ]
    result = repr2json_input_values(values)
    assert result == expect
