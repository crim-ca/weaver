"""
Unit tests of functions within :mod:`weaver.processes.convert`.
"""
# pylint: disable=R1729  # ignore non-generator representation employed for displaying test log results

import json
import tempfile
from collections import OrderedDict
from copy import deepcopy

import pytest
import yaml
from owslib.wps import ComplexData, Input as OWSInput
from pywps.inout.formats import Format
from pywps.inout.inputs import ComplexInput, LiteralInput
from pywps.inout.literaltypes import AllowedValue, AnyValue
from pywps.inout.outputs import ComplexOutput
from pywps.validator.mode import MODE

from weaver.exceptions import PackageTypeError
from weaver.formats import (
    IANA_NAMESPACE_DEFINITION,
    OGC_MAPPING,
    OGC_NAMESPACE_DEFINITION,
    ContentType
)
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_OGC_API,
    WPS_BOUNDINGBOX,
    WPS_COMPLEX,
    WPS_COMPLEX_TYPES,
    WPS_INPUT,
    WPS_LITERAL,
    WPS_LITERAL_DATA_TYPES,
    WPS_OUTPUT,
    ProcessSchema
)
from weaver.processes.convert import _are_different_and_set  # noqa: W0212
from weaver.processes.convert import (
    DEFAULT_FORMAT,
    PACKAGE_ARRAY_MAX_SIZE,
    CWLIODefinition,
    any2cwl_io,
    complex2json,
    convert_input_values_schema,
    cwl2json_input_values,
    cwl2wps_io,
    get_cwl_io_type,
    get_io_type_category,
    is_cwl_array_type,
    is_cwl_enum_type,
    is_cwl_file_type,
    json2wps_allowed_values,
    json2wps_datatype,
    merge_io_formats,
    normalize_ordered_io,
    ogcapi2cwl_process,
    repr2json_input_values,
    set_field,
    wps2json_io
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


def test_any2cwl_io_from_wps():
    fmt = Format(ContentType.APP_NETCDF)
    wps_io = ComplexInput("test", "", supported_formats=[fmt], data_format=fmt)
    # use 'json' to obtain 'type' field, but otherwise fields are named the same as if using the object
    wps_as_json = wps_io.json
    cwl_io, cwl_ns = any2cwl_io(wps_as_json, "input")
    assert cwl_io == {
        "id": "test",
        "type": "File",
        "format": f"ogc:{OGC_MAPPING[ContentType.APP_NETCDF]}"
    }
    assert cwl_ns == OGC_NAMESPACE_DEFINITION

    # retry by manually injecting the type to validate that
    # pre-resolved type can also be converted directly from object
    # since the object is used rather than its JSON representation,
    # potentially more field definitions are available to extract CWL equivalents
    setattr(wps_io, "type", "complex")
    cwl_io, cwl_ns = any2cwl_io(wps_io, "input")
    assert cwl_io == {
        "id": "test",
        "type": "File",
        "format": f"ogc:{OGC_MAPPING[ContentType.APP_NETCDF]}",
        "default": None,
    }
    assert cwl_ns == OGC_NAMESPACE_DEFINITION

    wps_io.min_occurs = 10
    wps_io.max_occurs = 20
    # use 'json' to obtain 'type' field, but otherwise fields are named the same as if using the object
    cwl_io, cwl_ns = any2cwl_io(wps_io, "input")
    assert cwl_io == {
        "id": "test",
        "type": {"type": "array", "items": "File"},
        "format": f"ogc:{OGC_MAPPING[ContentType.APP_NETCDF]}",
        "default": None,
    }
    assert cwl_ns == OGC_NAMESPACE_DEFINITION


class MockElementXML(dict):
    value = {}

    def __init__(self, value):  # noqa  # pylint: disable=W0231
        self.value = value

    def __call__(self, *_, **__):
        return MockElementXML([])

    def __getattr__(self, _):
        return MockElementXML({})

    def find(self, key):
        if isinstance(self.value, dict):
            return self.value.get(key)
        return None


def test_any2cwl_io_from_ows():
    ows_io = OWSInput(MockElementXML({}))  # skip parsing from XML, inject corresponding results directly
    ows_io.identifier = "test"
    ows_io.supportedValues = [ComplexData(mimeType=ContentType.APP_NETCDF)]
    setattr(ows_io, "type", "complex")
    # use 'json' to obtain 'type' field, but otherwise fields are named the same as if using the object
    cwl_io, cwl_ns = any2cwl_io(ows_io, "input")
    assert cwl_io == {
        "id": "test",
        "type": "File",
        "format": f"ogc:{OGC_MAPPING[ContentType.APP_NETCDF]}",
        "default": None,
    }
    assert cwl_ns == OGC_NAMESPACE_DEFINITION

    ows_io = OWSInput(MockElementXML({}))  # skip parsing from XML, inject corresponding results directly
    ows_io.identifier = "test"
    ows_io.supportedValues = [ComplexData(mimeType=ContentType.APP_NETCDF)]
    ows_io.minOccurs = 10
    ows_io.maxOccurs = 20
    setattr(ows_io, "type", "complex")
    # use 'json' to obtain 'type' field, but otherwise fields are named the same as if using the object
    cwl_io, cwl_ns = any2cwl_io(ows_io, "input")
    assert cwl_io == {
        "id": "test",
        "type": {"type": "array", "items": "File"},
        "format": f"ogc:{OGC_MAPPING[ContentType.APP_NETCDF]}",
        "default": None,
    }
    assert cwl_ns == OGC_NAMESPACE_DEFINITION


def test_any2cwl_io_from_json():
    # different than WPS as JSON representation, here we employ directly the OGC-API JSON representation
    json_io = {
        "id": "test",
        "formats": [{"mediaType": ContentType.APP_NETCDF, "default": True}]
    }
    # need to inject the following, would be provided by other merging/resolution steps prior to 'any2cwl_io' call
    json_io["type"] = "complex"
    # use 'json' to obtain 'type' field, but otherwise fields are named the same as if using the object
    cwl_io, cwl_ns = any2cwl_io(json_io, "input")
    assert cwl_io == {
        "id": "test",
        "type": "File",
        "format": f"ogc:{OGC_MAPPING[ContentType.APP_NETCDF]}"
    }
    assert cwl_ns == OGC_NAMESPACE_DEFINITION

    json_io["minOccurs"] = 10
    json_io["maxOccurs"] = 20
    # use 'json' to obtain 'type' field, but otherwise fields are named the same as if using the object
    cwl_io, cwl_ns = any2cwl_io(json_io, "input")
    assert cwl_io == {
        "id": "test",
        "type": {"type": "array", "items": "File"},
        "format": f"ogc:{OGC_MAPPING[ContentType.APP_NETCDF]}",
    }
    assert cwl_ns == OGC_NAMESPACE_DEFINITION


def test_any2cwl_io_from_oas():
    # different than WPS as JSON representation, here we employ directly the OGC-API JSON representation
    json_io = {
        "id": "test",
        "formats": [{"mediaType": ContentType.APP_NETCDF, "default": True}]
    }
    # need to inject the following, would be provided by other merging/resolution steps prior to 'any2cwl_io' call
    json_io["type"] = "complex"
    # use 'json' to obtain 'type' field, but otherwise fields are named the same as if using the object
    cwl_io, cwl_ns = any2cwl_io(json_io, "input")
    assert cwl_io == {
        "id": "test",
        "type": "File",
        "format": f"ogc:{OGC_MAPPING[ContentType.APP_NETCDF]}"
    }
    assert cwl_ns == OGC_NAMESPACE_DEFINITION

    json_io["minOccurs"] = 10
    json_io["maxOccurs"] = 20
    # use 'json' to obtain 'type' field, but otherwise fields are named the same as if using the object
    cwl_io, cwl_ns = any2cwl_io(json_io, "input")
    assert cwl_io == {
        "id": "test",
        "type": {"type": "array", "items": "File"},
        "format": f"ogc:{OGC_MAPPING[ContentType.APP_NETCDF]}",
    }
    assert cwl_ns == OGC_NAMESPACE_DEFINITION


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
        assert json2wps_datatype(test_io) == expect, f"Failed for [{copy_io}]"


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
        assert result == expect, f"Failed test {i}"


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
        io_info = {"name": f"test-{i}", "type": test_type}
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


@pytest.mark.parametrize("io_type, io_info", [
    (WPS_LITERAL, {"type": WPS_LITERAL}),
    (WPS_COMPLEX, {"type": WPS_COMPLEX}),
    (WPS_BOUNDINGBOX, {"type": WPS_BOUNDINGBOX}),
] + [
    (WPS_LITERAL, {"type": _type}) for _type in WPS_LITERAL_DATA_TYPES
] + [
    (WPS_COMPLEX, {"type": _type}) for _type in WPS_COMPLEX_TYPES
] + [
    (WPS_LITERAL, {"type": ["null", _type]}) for _type in WPS_LITERAL_DATA_TYPES
] + [
    (WPS_LITERAL, {"type": {"type": "array", "items": _type}}) for _type in WPS_LITERAL_DATA_TYPES
])
def test_get_io_type_category(io_type, io_info):
    assert get_io_type_category(io_info) == io_type, f"Testing: {io_info}"


@pytest.mark.parametrize("io_info, io_def", [
    ({"type": "string"},
     CWLIODefinition(type="string")),
    ({"type": "int"},
     CWLIODefinition(type="int")),
    ({"type": "float"},
     CWLIODefinition(type="float")),
    ({"type": {"type": "enum", "symbols": ["a", "b", "c"]}},
     CWLIODefinition(type="string", enum=True, symbols=["a", "b", "c"], mode=MODE.SIMPLE)),
    ({"type": {"type": "array", "items": "string"}},
     CWLIODefinition(type="string", array=True, min_occurs=1, max_occurs=PACKAGE_ARRAY_MAX_SIZE)),
    ({"type": ["null", "string"]},
     CWLIODefinition(type="string", null=True, min_occurs=0)),
    ({"type": "string?"},
     CWLIODefinition(type="string", null=True, min_occurs=0)),
])
def test_get_cwl_io_type(io_info, io_def):
    io_def.name = io_info["name"] = "test"
    io_res = get_cwl_io_type(io_info)
    assert io_res == io_def


def test_is_cwl_array_type_explicit_invalid_item():
    io_info = {
        "name": "test",
        "type": {
            "type": "array",
            "items": "unknown-type-item"
        }
    }
    with pytest.raises(PackageTypeError):
        is_cwl_array_type(io_info)


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
        res = is_cwl_array_type(io_info)
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
    res = is_cwl_array_type(io_info)
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
    res = is_cwl_array_type(io_info)
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
    res = is_cwl_array_type(io_info)
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
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def test_is_cwl_array_type_shorthand_base():
    io_info = {
        "name": "test",
        "type": "string[]",
    }
    res = is_cwl_array_type(io_info)
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
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def test_is_cwl_array_type_explicit_optional_not_array():
    io_info = {
        "name": "test",
        "type": ["null", "float"],
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is False
    assert res[1] == "float"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def test_is_cwl_array_type_explicit_optional_simple_enum():
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


def test_is_cwl_array_type_explicit_optional_explicit_base():
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


def test_is_cwl_array_type_explicit_optional_explicit_enum():
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


def test_is_cwl_array_type_explicit_optional_shorthand_base():
    io_info = {
        "name": "test",
        "type": ["null", "string[]"]
    }
    res = is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.NONE
    assert res[3] == AnyValue


def test_is_cwl_array_type_explicit_optional_shorthand_enum():
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


def test_is_cwl_enum_type_string():
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


def test_is_cwl_enum_type_float():
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


def test_is_cwl_enum_type_int():
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
        io_info = {"name": f"test-{i}", "type": io_type}
        assert not is_cwl_file_type(io_info), f"Test [{i}]: {io_info}"


def assert_formats_equal_any_order(format_result, format_expect):
    assert len(format_result) == len(format_expect), "Expected formats sizes mismatch"
    for r_fmt in format_result:
        for e_fmt in format_expect:
            if r_fmt.json == e_fmt.json:
                format_expect.remove(e_fmt)
                break
    assert not format_expect, f"Not all expected formats matched {[fmt.json for fmt in format_expect]}"


def test_wps2json_io_default_format():
    # must create object with matching data/supported formats or error otherwise
    wps_io = ComplexInput("test", "", supported_formats=[DEFAULT_FORMAT], data_format=DEFAULT_FORMAT)
    # then simulate that a merging/resolution replaced the supported formats
    wps_io.supported_formats = []
    # conversion should employ the default format since none specified
    json_io = wps2json_io(wps_io)
    default = {
        "default": True,
        "mediaType": DEFAULT_FORMAT.mime_type,
        "extension": DEFAULT_FORMAT.extension,
        "encoding": DEFAULT_FORMAT.encoding,
        "schema": DEFAULT_FORMAT.schema,
    }
    assert json_io["formats"] == [default]

    # do the same thing again, but 'default' should be False because default plain/text
    # format is not defined as 'data_format' (used as default specifier)
    json_fmt = Format(ContentType.APP_JSON)
    wps_io = ComplexInput("test", "", supported_formats=[json_fmt], data_format=json_fmt)
    wps_io.supported_formats = []
    json_io = wps2json_io(wps_io)
    default = {
        "default": False,   # <-- this is what must be different
        "mediaType": DEFAULT_FORMAT.mime_type,
        "extension": DEFAULT_FORMAT.extension,
        "encoding": DEFAULT_FORMAT.encoding,
        "schema": DEFAULT_FORMAT.schema,
    }
    assert json_io["formats"] == [default]


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
            expect_id = expect["id"]
            raise AssertionError(f"expected '{expect_id}' was not validated against any result value")


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


def test_complex2json():
    data = ComplexData(ContentType.IMAGE_GEOTIFF, encoding="base64", schema="")
    set_field(data, "maximumMegabytes", "100")  # possibly injected from parsed XML
    json_data = complex2json(data)
    assert json_data == {
        "mimeType": ContentType.IMAGE_GEOTIFF,
        "encoding": "base64",
        "schema": "",
        "maximumMegabytes": 100,
        "default": False,
    }

    data = ComplexData(ContentType.APP_JSON, encoding=None, schema="https://geojson.org/schema/FeatureCollection.json")
    set_field(data, "maximumMegabytes", "15")  # possibly injected from parsed XML
    json_data = complex2json(data)
    assert json_data == {
        "mimeType": ContentType.APP_JSON,
        "encoding": None,
        "schema": "https://geojson.org/schema/FeatureCollection.json",
        "maximumMegabytes": 15,
        "default": False,
    }


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
        # verify that '@parameters' handle some special logic to convert known format fields (not just passed directly)
        f"test11:File=/tmp/file.json@mediaType={ContentType.APP_JSON}@schema=http://schema.org/random.json",
        f"test12:File=/tmp/other.xml@mimeType={ContentType.TEXT_XML}@contentSchema=http://schema.org/random.xml",
        # different representations can be used simultaneously, each parameter is attached to the specific array item
        f"test13:File=/tmp/one.json@mimeType={ContentType.APP_JSON};/tmp/two.xml@mediaType={ContentType.TEXT_XML}",
    ]
    expect = [
        {"id": "test1", "value": "value"},
        {"id": "test2", "value": 1},
        {"id": "test3", "value": 1.23},
        {"id": "test4", "href": "/tmp/random.txt"},
        # array values are extended to OLD listing format
        # CLI would then convert them to OGC using 'convert_input_values_schema'
        {"id": "test5", "value": "val1"},
        {"id": "test5", "value": "val2"},
        {"id": "test6", "value": 1},
        {"id": "test6", "value": 2},
        {"id": "test7", "value": 1.23},
        {"id": "test7", "value": 4.56},
        {"id": "test8", "href": "/tmp/other.txt"},
        {"id": "test9", "value": "short"},
        {"id": "test10", "value": "long"},
        {"id": "test11", "href": "/tmp/file.json", "format": {
            "mediaType": ContentType.APP_JSON, "schema": "http://schema.org/random.json"
        }},
        {"id": "test12", "href": "/tmp/other.xml", "format": {
            "mediaType": ContentType.TEXT_XML, "schema": "http://schema.org/random.xml"
        }},
        {"id": "test13", "href": "/tmp/one.json", "format": {"mediaType": ContentType.APP_JSON}},
        {"id": "test13", "href": "/tmp/two.xml", "format": {"mediaType": ContentType.TEXT_XML}},
    ]
    result = repr2json_input_values(values)
    assert result == expect


def test_set_field():
    data = {"x": 1}
    set_field(data, "y", 2)
    assert data == {"x": 1, "y": 2}

    set_field(data, "z", null)
    assert data == {"x": 1, "y": 2}

    set_field(data, "z", null, force=True)
    assert data == {"x": 1, "y": 2, "z": null}

    set_field(data, "z", None)
    assert data == {"x": 1, "y": 2, "z": None}

    class Data(object):
        pass

    data = Data()
    set_field(data, "y", 2)
    assert getattr(data, "y", 2)

    set_field(data, "z", null)
    assert not hasattr(data, "z")

    set_field(data, "z", null, force=True)
    assert getattr(data, "y", 2)
    assert getattr(data, "z", None) == null

    set_field(data, "z", None)
    assert getattr(data, "y", 2)
    assert getattr(data, "z", null) is None


def test_ogcapi2cwl_process_with_extra_href():
    href = "https://remote-server.com/processes/test-process"
    with tempfile.NamedTemporaryFile(mode="w", suffix="test-package.cwl") as tmp_file:
        cwl_ns = {}
        cwl_ns.update(IANA_NAMESPACE_DEFINITION)
        cwl_ns.update(OGC_NAMESPACE_DEFINITION)
        pkg = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": ["dont-care"],
            "arguments": ["irrelevant"],
            "inputs": {
                "in-str": {"type": "string", "inputBinding": {"position": 1}},
                "in-int": {"type": "int", "inputBinding": {"position": 2}},
                "in-float": {"type": "float", "inputBinding": {"position": 3}},
                "in-file": {"type": "File", "format": f"iana:{ContentType.APP_JSON}",
                            "inputBinding": {"prefix": "-f"}},
            },
            "outputs": {
                "output": {"type": "File", "format": "ogc:geotiff",
                           "outputBinding": {"glob": "output/*.tiff"}},
            },
            "$namespaces": cwl_ns
        }
        yaml.safe_dump(pkg, tmp_file, sort_keys=False)
        tmp_file.flush()
        tmp_file.seek(0)
        body = {
            "process": {"href": tmp_file.name}
        }
        cwl, info = ogcapi2cwl_process(body, href)
    assert info is not body, "copy should be created, not inplace modifications"
    assert cwl != pkg, "Conversion should have slightly modified the reference CWL"
    pkg.pop("baseCommand")
    pkg.pop("arguments")
    pkg["hints"] = {
        CWL_REQUIREMENT_APP_OGC_API: {
            "process": href
        }
    }
    assert pkg == cwl
    assert info == {
        "process": {"href": tmp_file.name},  # carried over, rest is generated
        "executionUnit": [{"unit": cwl}],
        "deploymentProfile": "http://www.opengis.net/profiles/eoc/ogcapiApplication",
    }, "Process information should have been generated with additional details extracted from CWL."


def test_ogcapi2cwl_process_with_extra_exec_unit():
    href = "https://remote-server.com/processes/test-process"
    cwl_ns = {}
    cwl_ns.update(IANA_NAMESPACE_DEFINITION)
    cwl_ns.update(OGC_NAMESPACE_DEFINITION)
    pkg = {
        "cwlVersion": "v1.0",
        "class": "CommandLineTool",
        "baseCommand": ["dont-care"],
        "arguments": ["irrelevant"],
        "inputs": {
            "in-str": {"type": "string", "inputBinding": {"position": 1}},
            "in-int": {"type": "int", "inputBinding": {"position": 2}},
            "in-float": {"type": "float", "inputBinding": {"position": 3}},
            "in-file": {"type": "File", "format": f"iana:{ContentType.APP_JSON}",
                        "inputBinding": {"prefix": "-f"}},
        },
        "outputs": {
            "output": {"type": "File", "format": "ogc:geotiff",
                       "outputBinding": {"glob": "output/*.tiff"}},
        },
        "$namespaces": cwl_ns
    }
    body = {
        "process": {
            "id": "test-process"
        },
        "executionUnit": [
            {"unit": pkg}
        ]
    }
    cwl, info = ogcapi2cwl_process(body, href)
    assert info is not body and info != body, "copy should be created, not inplace modifications"
    assert cwl is not pkg and cwl != pkg
    pkg.pop("baseCommand")
    pkg.pop("arguments")
    pkg["hints"] = {
        CWL_REQUIREMENT_APP_OGC_API: {
            "process": href
        }
    }
    assert pkg == cwl
    body["deploymentProfile"] = "http://www.opengis.net/profiles/eoc/ogcapiApplication"
    assert info == body


def test_ogcapi2cwl_process_with_extra_exec_href():
    href = "https://remote-server.com/processes/test-process"
    cwl_ns = {}
    cwl_ns.update(IANA_NAMESPACE_DEFINITION)
    cwl_ns.update(OGC_NAMESPACE_DEFINITION)
    with tempfile.NamedTemporaryFile(mode="w", suffix="test-package.cwl") as tmp_file:
        pkg = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": ["dont-care"],
            "arguments": ["irrelevant"],
            "inputs": {
                "in-str": {"type": "string", "inputBinding": {"position": 1}},
                "in-int": {"type": "int", "inputBinding": {"position": 2}},
                "in-float": {"type": "float", "inputBinding": {"position": 3}},
                "in-file": {"type": "File", "format": f"iana:{ContentType.APP_JSON}",
                            "inputBinding": {"prefix": "-f"}},
            },
            "outputs": {
                "output": {"type": "File", "format": "ogc:geotiff",
                           "outputBinding": {"glob": "output/*.tiff"}},
            },
            "$namespaces": cwl_ns
        }
        json.dump(pkg, tmp_file)
        tmp_file.flush()
        tmp_file.seek(0)
        body = {
            "process": {
                "id": "test-process"
            },
            "executionUnit": [
                {"href": tmp_file.name}
            ]
        }
        cwl, info = ogcapi2cwl_process(body, href)
    assert info is not body and info != body, "copy should be created, not inplace modifications"
    assert cwl is not pkg and cwl != pkg
    pkg.pop("baseCommand")
    pkg.pop("arguments")
    pkg["hints"] = {
        CWL_REQUIREMENT_APP_OGC_API: {
            "process": href
        }
    }
    assert pkg == cwl
    body["executionUnit"] = [{"unit": cwl}]
    body["deploymentProfile"] = "http://www.opengis.net/profiles/eoc/ogcapiApplication"
    assert info == body, "Execution unit should be rewritten with OGC-API hints requirement."


def test_ogcapi2cwl_process_without_extra():
    href = "https://remote-server.com/processes/test-process"
    body = {
        "inputs": {
            "in-str": {"schema": {"type": "string"}},
            "in-int": {"schema": {"type": "integer"}},
            "in-float": {"schema": {"type": "number"}},
            "in-file": {"schema": {"type": "string", "contentMediaType": ContentType.APP_JSON}},
        },
        "outputs": {
            "output": {"schema": {"type": "string", "contentMediaType": ContentType.IMAGE_GEOTIFF}},
        }
    }
    cwl, info = ogcapi2cwl_process(body, href)
    assert info is not body, "copy should be created, not inplace modifications"
    cwl_ns = {}
    cwl_ns.update(IANA_NAMESPACE_DEFINITION)
    cwl_ns.update(OGC_NAMESPACE_DEFINITION)
    assert cwl == {
        "cwlVersion": "v1.0",
        "class": "CommandLineTool",
        "hints": {
            CWL_REQUIREMENT_APP_OGC_API: {
                "process": href
            }
        },
        "inputs": {
            "in-str": {"type": "string"},
            "in-int": {"type": "int"},
            "in-float": {"type": "float"},
            "in-file": {"type": "File", "format": f"iana:{ContentType.APP_JSON}"},
        },
        "outputs": {
            "output": {"type": "File", "format": "ogc:geotiff",
                       "outputBinding": {"glob": "output/*.tiff"}},
        },
        "$namespaces": cwl_ns
    }
    assert info != body
    body["executionUnit"] = [{"unit": cwl}]
    body["deploymentProfile"] = "http://www.opengis.net/profiles/eoc/ogcapiApplication"
    assert info == body, "Process information should be updated with minimal details since no CWL detected in input."
