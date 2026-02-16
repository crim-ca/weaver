"""
Unit tests of functions within :mod:`weaver.processes.convert`.
"""
import inspect
import logging

# pylint: disable=R1729  # ignore non-generator representation employed for displaying test log results

import json
import tempfile
from collections import OrderedDict
from copy import deepcopy
from typing import TYPE_CHECKING

import pint
import pytest
import yaml
from cwltool.errors import WorkflowException
from cwltool.factory import Factory as CWLFactory
from owslib.crs import Crs
from owslib.wps import ComplexData, Input as OWSInput, Output as OWSOutput
from pywps.inout.basic import UOM
from pywps.inout.formats import Format
from pywps.inout.inputs import ComplexInput, LiteralInput
from pywps.inout.literaltypes import AllowedValue, AnyValue
from pywps.inout.outputs import ComplexOutput
from pywps.validator.mode import MODE

from tests import resources
from tests.utils import MockedResponse, assert_equal_any_order, mocked_remote_server_requests_wps1
from weaver import xml_util
from weaver.exceptions import PackageTypeError
from weaver.formats import (
    DEFAULT_FORMAT,
    EDAM_MAPPING,
    EDAM_NAMESPACE,
    IANA_NAMESPACE,
    IANA_NAMESPACE_DEFINITION,
    OGC_MAPPING,
    OGC_NAMESPACE_DEFINITION,
    ContentEncoding,
    ContentType,
    get_cwl_file_format
)
from weaver.processes.constants import (
    CWL_NAMESPACE_CWLTOOL_URL,
    CWL_REQUIREMENT_APP_OGC_API,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_INLINE_JAVASCRIPT,
    CWL_REQUIREMENT_SECRETS,
    IO_INPUT,
    IO_OUTPUT,
    WPS_BOUNDINGBOX,
    WPS_BOUNDINGBOX_DATA,
    WPS_COMPLEX,
    WPS_COMPLEX_DATA,
    WPS_COMPLEX_TYPES,
    WPS_LITERAL,
    WPS_LITERAL_DATA_TYPES,
    ProcessSchema
)
from weaver.processes.convert import _are_different_and_set  # noqa: W0212
from weaver.processes.convert import _convert_any2cwl_io_complex  # noqa: W0212
from weaver.processes.convert import _get_cwl_js_value_from  # noqa: W0212
from weaver.processes.convert import (
    PACKAGE_ARRAY_MAX_SIZE,
    CWLIODefinition,
    any2cwl_io,
    complex2json,
    convert_input_values_schema,
    convert_value_units,
    cwl2json_input_values,
    cwl2wps_io,
    get_cwl_io_type,
    get_io_type_category,
    is_cwl_complex_type,
    json2oas_io,
    json2wps_allowed_values,
    json2wps_datatype,
    json2wps_io,
    json2wps_supported_uoms,
    merge_io_formats,
    normalize_ordered_io,
    oas2json_io,
    ogcapi2cwl_process,
    ows2json_io,
    ows2json_output_data,
    parse_cwl_array_type,
    parse_cwl_enum_type,
    repr2json_input_values,
    resolve_cwl_namespaced_name,
    set_field,
    wps2json_io,
    xml_wps2cwl
)
from weaver.utils import null
from weaver.wps_restapi.swagger_definitions import OGC_API_BBOX_FORMAT, OGC_API_BBOX_SCHEMA

if TYPE_CHECKING:
    from typing import List


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


@pytest.mark.parametrize("value1, value2, expect", [
    (1, 2, True),
    (1, 1, False),
    ({"a": 1}, {"a": 2}, True),
    ({"a": 1}, {"a": 1}, False),
    ({"a": 1, "b": 2}, {"a": 1}, True),
    (ObjectWithEqProperty(), ObjectWithEqProperty(), False),
    (ObjectWithEqProperty("a"), ObjectWithEqProperty("b"), True),
])
def test_are_different_and_set_both_set(value1, value2, expect):
    assert _are_different_and_set(value1, value2) is expect


@pytest.mark.parametrize("value1, value2, expect", [
    # pylint: disable=W1406,redundant-u-string-prefix  # left for readability
    (b"something", u"something", False),
    (u"something", u"something", False),
    (b"something", b"something", False),
    (b"something", u"else", True),
    (u"something", u"else", True),
    (b"something", b"else", True),
])
def test_are_different_and_set_similar_str_formats(value1, value2, expect):
    assert _are_different_and_set(value1, value2) is expect


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


@pytest.mark.parametrize(
    ["wps_io", "cwl_io_expect"],
    [
        (
            {
                "id": "output",
                "formats": [
                    {"mimeType": ContentType.APP_JSON, "encoding": None, "default": True},
                ]
            },
            {
                "id": "output",
                "type": "File",
                "format": f"{IANA_NAMESPACE}:{ContentType.APP_JSON}",
                "outputBinding": {
                    "glob": "*.json"
                }
            }
        ),
        (
            {
                "id": "output",
                "formats": [
                    {"mimeType": ContentType.TEXT_PLAIN, "encoding": None, "default": True},
                ]
            },
            {
                "id": "output",
                "type": "File",
                "format": f"{EDAM_NAMESPACE}:{EDAM_MAPPING[ContentType.TEXT_PLAIN]}",
                "outputBinding": {
                    "glob": "*.*"  # *.txt replaced by *.* since anything can be text/plain
                }
            }
        ),
        (
            {
                "id": "output",
                "formats": [
                    {"mimeType": ContentType.TEXT_PLAIN, "encoding": None, "default": True},
                    {"mimeType": ContentType.APP_JSON, "encoding": None, "default": True},
                ]
            },
            {
                "id": "output",
                "type": "File",
                "outputBinding": {
                    "glob": "*.*"  # *.txt replaced by *.* since anything can be text/plain, including JSON
                }
            }
        ),
        (
            {
                "id": "output",
                "formats": [
                    {"mimeType": ContentType.APP_XML, "encoding": "base64", "default": True},
                    {"mimeType": ContentType.APP_XML, "encoding": None, "default": True},
                ]
            },
            {
                "id": "output",
                "type": "File",
                "format": f"{IANA_NAMESPACE}:{ContentType.APP_XML}",
                "outputBinding": {
                    "glob": "*.xml"
                }
            }
        ),
        (
            {
                "id": "output",
                "formats": [
                    {"mimeType": ContentType.APP_NETCDF, "encoding": "base64", "default": True},
                    {"mimeType": ContentType.APP_ZIP, "encoding": "base64", "default": False}
                ]
            },
            {
                "id": "output",
                "type": "File",
                # no "format" since more than one, CWL does not support many
                "outputBinding": {
                    "glob": ["*.nc", "*.zip"]
                }
            }
        )
    ]
)
def test_convert_any2cwl_io_complex(wps_io, cwl_io_expect):
    cwl_io = {"id": wps_io["id"]}
    _convert_any2cwl_io_complex(cwl_io, {}, wps_io, IO_OUTPUT)
    assert cwl_io == cwl_io_expect


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

    @property
    def tag(self):
        return [""]

    def find(self, key):
        if isinstance(self.value, dict):
            return self.value.get(key)
        return None


class MockBboxElementXML(MockElementXML):
    def __init__(self, bbox, crs):
        super().__init__(None)
        self.minx, self.miny, self.maxx, self.maxy = bbox
        self.crs = crs


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


@pytest.mark.parametrize(
    ["io_select", "test_io", "expect"],
    [
        (
            IO_INPUT,
            {
                "id": "test",
                "data_type": "string",
                "allowed_values": ["1", "2", "3"],
                "any_value": False,
                "min_occurs": 1,
                "max_occurs": 1,
            },
            {
                "id": "test",
                "type": {
                    "type": "enum",
                    "symbols": ["1", "2", "3"],
                },
            },
        ),
        (
            IO_INPUT,
            {
                "id": "test",
                "data_type": "string",
                "allowed_values": ["1", "2", "3"],
                "any_value": False,
                "min_occurs": 2,
                "max_occurs": 3,
            },
            {
                "id": "test",
                "type": {
                    "type": "array",
                    "items": {
                        "type": "enum",
                        "symbols": ["1", "2", "3"],
                    },
                },
            },
        ),
        (
            IO_INPUT,
            {
                "id": "test",
                "data_type": "string",
                "allowed_values": ["1", "2", "3"],
                "any_value": False,
                "min_occurs": 0,
                "max_occurs": 3,
            },
            {
                "id": "test",
                "type": [
                    "null",
                    {
                        "type": "enum",
                        "symbols": ["1", "2", "3"],
                    },
                    {
                        "type": "array",
                        "items": {
                            "type": "enum",
                            "symbols": ["1", "2", "3"],
                        },
                    },
                ]
            },
        ),
        (
            IO_INPUT,
            {
                "id": "test",
                "data_type": "integer",
                "allowed_values": [1, 2, 3],
                "any_value": False,
                "min_occurs": 1,
                "max_occurs": 1,
            },
            {
                "id": "test",
                "type": "int",
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=False)},
            },
        ),
        (
            IO_INPUT,
            {
                "id": "test",
                "data_type": "integer",
                "allowed_values": [1, 2, 3],
                "any_value": False,
                "min_occurs": 2,
                "max_occurs": 3,
            },
            {
                "id": "test",
                "type": {"type": "array", "items": "int"},
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=False, allow_array=True)},
            },
        ),
        (
            IO_INPUT,
            {
                "id": "test",
                "data_type": "integer",
                "allowed_values": [1, 2, 3],
                "any_value": False,
                "min_occurs": 0,
                "max_occurs": 3,
            },
            {
                "id": "test",
                "type": [
                    "null",
                    "int",
                    {
                        "type": "array",
                        "items": "int",
                    },
                ],
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=True)},
            },
        ),
        (
            # documentation example
            IO_INPUT,
            {
                "id": "test",
                "schema": {
                    "type": "string",
                    "enum": ["value-1", "value-2"]
                },
                "minOccurs": 2,
                "maxOccurs": 4,
            },
            {
                "id": "test",
                "type": {
                    "type": "array",
                    "items": {
                        "type": "enum",
                        "symbols": ["value-1", "value-2"],
                    },
                }
            }
        ),
        (
            # documentation example
            IO_INPUT,
            {
                "id": "test",
                "schema": {
                    "type": "string",
                    "enum": ["value-1", "value-2"]
                },
                "minOccurs": 1,
                "maxOccurs": 4,
            },
            {
                "id": "test",
                "type": [
                    {
                        "type": "enum",
                        "symbols": ["value-1", "value-2"],
                    },
                    {
                        "type": "array",
                        "items": {
                            "type": "enum",
                            "symbols": ["value-1", "value-2"],
                        },
                    }
                ]
            }
        ),
        (
            # documentation example
            IO_INPUT,
            {
                "id": "test",
                "schema": {
                    "type": "string",
                    "enum": ["value-1", "value-2"]
                },
                "minOccurs": 0,
                "maxOccurs": 4,
            },
            {
                "id": "test",
                "type": [
                    "null",
                    {
                        "type": "enum",
                        "symbols": ["value-1", "value-2"],
                    },
                    {
                        "type": "array",
                        "items": {
                            "type": "enum",
                            "symbols": ["value-1", "value-2"],
                        },
                    }
                ]
            }
        ),
        (
            # documentation example
            IO_INPUT,
            {
                "id": "test",
                "schema": {
                    # explicitly array, MUST force CWL to be an array as well
                    # doesn't matter that default min/max occurs = 1
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["value-1", "value-2"]
                    }
                }
            },
            {
                "id": "test",
                # note: "type" as array of single mapping with "type: array" would also be valid ([] around the {})
                "type": {
                    "type": "array",
                    "items": {
                        "type": "enum",
                        "symbols": ["value-1", "value-2"],
                    },
                }
            }
        ),
        (
            # documentation example
            IO_INPUT,
            {
                "id": "test",
                "minOccurs": 1,  # same as previous, but explicitly specified rather than default
                "schema": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["value-1", "value-2"]
                    }
                }
            },
            {
                "id": "test",
                "type": {
                    "type": "array",
                    "items": {
                        "type": "enum",
                        "symbols": ["value-1", "value-2"],
                    },
                }
            }
        ),
        (
            # documentation example
            IO_INPUT,
            {
                "id": "test",
                "minOccurs": 0,  # because optional, array must be combined with "null"
                "schema": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["value-1", "value-2"]
                    }
                }
            },
            {
                "id": "test",
                "type": [
                    "null",
                    {
                        "type": "array",
                        "items": {
                            "type": "enum",
                            "symbols": ["value-1", "value-2"],
                        },
                    }
                ]
            }
        ),
        (
            # documentation example
            IO_INPUT,
            {
                "id": "test",
                "minOccurs": 0,  # same as previous
                "maxOccurs": 4,  # explicitly specified should not change anything
                "schema": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["value-1", "value-2"]
                    }
                }
            },
            {
                "id": "test",
                "type": [
                    "null",
                    {
                        "type": "array",
                        "items": {
                            "type": "enum",
                            "symbols": ["value-1", "value-2"],
                        },
                    }
                ]
            }
        )
    ]
)
def test_any2cwl_io_enum_convert(io_select, test_io, expect):
    cwl_io, _ = any2cwl_io(test_io, io_select)  # type: ignore
    assert cwl_io == expect


@pytest.mark.parametrize(
    ["test_io", "test_input", "expect_valid"],
    [
        (
            {
                "type": "int",
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=False)},
            },
            1,
            True,
        ),
        (
            {
                "type": "int",
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=False)},
            },
            [1],
            False,
        ),
        (
            {
                "type": "int",
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=False)},
            },
            ["1"],
            False,
        ),
        (
            {
                "type": {"type": "array", "items": "int"},
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=False, allow_array=True)},
            },
            [1],
            True,
        ),
        (
            {
                "type": {"type": "array", "items": "int"},
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=False, allow_array=True)},
            },
            1,
            False,
        ),
        (
            {
                "type": {"type": "array", "items": "int"},
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=False, allow_array=True)},
            },
            ["1"],
            False,
        ),
        (
            {
                "type": ["null", "int", {"type": "array", "items": "int"}],
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=True)},
            },
            None,
            True,
        ),
        (
            {
                "type": ["null", "int", {"type": "array", "items": "int"}],
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=True)},
            },
            1,
            True,
        ),
        (
            {
                "type": ["null", "int", {"type": "array", "items": "int"}],
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=True)},
            },
            [1],
            True,
        ),
        (
            {
                "type": ["null", "int", {"type": "array", "items": "int"}],
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=True)},
            },
            [0],
            False,
        ),
        (
            {
                "type": ["null", "int", {"type": "array", "items": "int"}],
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=True)},
            },
            [1, 4],
            False,
        ),
        (
            {
                "type": ["null", "int", {"type": "array", "items": "int"}],
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=True)},
            },
            [1, 2.3],
            False,
        ),
        (
            {
                "type": ["null", "int", {"type": "array", "items": "int"}],
                "inputBinding": {"valueFrom": _get_cwl_js_value_from([1, 2, 3], allow_unique=True, allow_array=True)},
            },
            0,
            False,
        ),
    ]
)
def test_any2cwl_io_enum_validate(test_io, test_input, expect_valid):
    cwl = {
        "cwlVersion": "v1.2",
        "class": "CommandLineTool",
        "baseCommand": "echo",
        "requirements": {
            "InlineJavascriptRequirement": {}
        },
        "inputs": {
            "input": test_io,
        },
        "outputs": {
            "output": "stdout",
        }
    }
    factory = CWLFactory()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as tmp_file:
        json.dump(cwl, tmp_file)
        tmp_file.flush()
        tool = factory.make(f"file://{tmp_file.name}")
    inputs = {"input": test_input}
    if expect_valid:
        tool(**inputs)
    else:
        with pytest.raises(WorkflowException):
            tool(**inputs)


@pytest.mark.parametrize(
    ["test_io", "expect"],
    [
        (
            {
                "literalDataDomains": [
                    {"default": True, "dataType": {"name": "integer"}, "valueDefinition": [1, 2, 3]}
                ],
                "any_value": False,
                "min_occurs": 1,
                "max_occurs": 1,
            },
            {
                "type": "integer",
                "enum": [1, 2, 3],
            },
        ),
        (
            {
                "literalDataDomains": [
                    {"default": True, "dataType": {"name": "integer"}, "valueDefinition": [1, 2, 3]}
                ],
                "any_value": False,
                "min_occurs": 0,
                "max_occurs": 2,
            },
            {
                "type": "array",
                "items": {
                    "type": "integer",
                    "enum": [1, 2, 3],
                },
                "minItems": 0,
                "maxItems": 2,
            },
        )
    ]
)
def test_json2oas_io(test_io, expect):
    copy_io = deepcopy(test_io)  # can get modified by function
    assert json2oas_io(test_io) == expect, f"Failed for [{copy_io}]"


@pytest.mark.parametrize("expect, test_io", [
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
])
def test_json2wps_datatype(expect, test_io):
    copy_io = deepcopy(test_io)  # can get modified by function
    assert json2wps_datatype(test_io) == expect, f"Failed for [{copy_io}]"


@pytest.mark.parametrize("values, expect", [
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
])
def test_json2wps_allowed_values(values, expect):
    result = json2wps_allowed_values(values)
    assert result == expect


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
    wps_io = cwl2wps_io(io_info, IO_INPUT)
    assert isinstance(wps_io, LiteralInput)
    assert wps_io.min_occurs == 0
    assert wps_io.max_occurs == PACKAGE_ARRAY_MAX_SIZE
    assert wps_io.data_type == "string"
    assert wps_io.allowed_values == [AllowedValue(value=val) for val in allowed_values]


@pytest.mark.parametrize("test_type", [
    ["string", "int"],
    [
        "int",
        {"type": "array", "items": "string"},
    ],
    [
        {"type": "enum", "symbols": ["1", "2"]},  # symbols as literal strings != int literal
        "null",
        "int"
    ],
    [
        "null",
        {"type": "enum", "symbols": ["1", "2"]},  # symbols as literal strings != int items
        {"type": "array", "items": "int"}
    ]
])
def test_cwl2wps_io_raise_mixed_types(test_type):
    io_info = {"name": "test", "type": test_type}
    with pytest.raises(PackageTypeError):
        cwl2wps_io(io_info, IO_INPUT)


@pytest.mark.parametrize(
    ["io_default", "io_expect", "is_erroneous"],
    [
        (
            {"name": "data", "type": "string", "default": ["test"]},
            "test",
            True,
        ),
        (
            {"name": "data", "type": "integer", "default": [1]},
            1,
            True,
        ),
        (
            {"name": "data", "type": "float", "default": [3.1416]},
            3.1416,
            True,
        ),
        (
            {"name": "data", "type": "boolean", "default": [True]},
            True,
            True,
        ),
        (
            # empty considered as "null default"
            {"name": "data", "type": "integer", "default": []},
            None,
            True,
        ),
        (
            # explicitly "null default"
            {"name": "data", "type": "integer", "default": [None]},
            None,
            True,
        ),
        (
            # only 1 array element allowed for silent handling
            {"name": "data", "type": "integer", "default": [1, 2, 3]},
            PackageTypeError,
            True,
        ),
        (
            # don't allow nested lists, even if literal inside
            # assume it is too much "lists" involved, and the intention is most probably wrong at this point
            {"name": "data", "type": "integer", "default": [[1]]},
            PackageTypeError,
            True,
        ),
        (
            # don't allow non-literals within list, even if single element
            {"name": "data", "type": "integer", "default": [{}]},
            PackageTypeError,
            True,
        ),
        (
            # sanity check valid case
            {"name": "data", "type": "string", "default": "test"},
            "test",
            False,
        ),
        (
            # sanity check valid case
            {"name": "data", "type": "float", "default": 3.1416},
            3.1416,
            False,
        )
    ]
)
def test_cwl2wps_io_literal_handle_erroneous_defaults(io_default, io_expect, is_erroneous, caplog):
    """
    Given a remote :term:`OAP` process description with an erroneous ``default``, ensure parsing can mitigate silently.
    """

    if inspect.isclass(io_expect) and issubclass(io_expect, Exception):
        with pytest.raises(io_expect):
            cwl2wps_io(io_default, IO_INPUT)
    else:
        with caplog.at_level(logging.WARNING):
            result = cwl2wps_io(io_default, IO_INPUT)
            assert result.data == io_expect
        assert not is_erroneous or (is_erroneous and "detected badly formed 'default'" in caplog.text.lower())


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
    wps_io = cwl2wps_io(cwl_io_record, IO_OUTPUT)
    assert isinstance(wps_io, ComplexOutput)
    assert len(wps_io.supported_formats) == 1
    assert isinstance(wps_io.supported_formats[0], Format)
    assert wps_io.supported_formats[0].mime_type == ContentType.APP_JSON


@pytest.mark.parametrize(
    ["test_formats", "expected_types"],
    [
        (
            "${ return \"iana:application/json\"; }",
            [DEFAULT_FORMAT.mime_type],
        ),
        (
            [
                "${ return \"iana:application/json\"; }",
                "iana:application/json"
            ],
            [ContentType.APP_JSON],
        ),
        (
            [
                "${ return \"iana:application/json\"; }",
                "https://www.iana.org/assignments/media-types/application/json",
            ],
            [ContentType.APP_JSON],
        ),
        (
            [
                "${ return \"iana:application/geo+json\"; }",
                "https://geojson.org/schema/FeatureCollection.json",
            ],
            [ContentType.APP_GEOJSON],
        ),
        (
            [
                "${ return \"iana:application/geo+json\"; }",
                "https://example.com/unknown/reference.abc",
                "https://example.com/unresolved",
            ],
            [ContentType.TEXT_PLAIN, ContentType.TEXT_PLAIN],
        ),
        (
            [
                "https://example.com/unknown/reference.abc",
                "${ return \"iana:application/geo+json\"; }",
                "https://example.com/unique/resolved.xsd",
                "https://example.com/unresolved",
            ],
            [ContentType.TEXT_PLAIN, ContentType.APP_XML, ContentType.TEXT_PLAIN],
        ),
    ]
)
def test_cwl2wps_io_expression_format(test_formats, expected_types):
    input_def = {
        "name": "data",
        "type": "File",
        "format": test_formats,
    }
    input_wps = cwl2wps_io(input_def, IO_INPUT)
    media_types = [fmt.mime_type for fmt in input_wps.supported_formats]
    assert media_types == expected_types


@pytest.mark.parametrize(
    ["io_type", "io_info"],
    [
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
    ]
)
def test_get_io_type_category(io_type, io_info):
    assert get_io_type_category(io_info) == io_type, f"Testing: {io_info}"


@pytest.mark.parametrize(
    ["io_info", "io_def"],
    [
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
    ]
)
def test_get_cwl_io_type(io_info, io_def):
    io_def.name = io_info["name"] = "test"
    io_res = get_cwl_io_type(io_info)
    assert io_res == io_def


@pytest.mark.parametrize(
    ["io_info", "io_def"],
    [
        (
            {
                "name": "test",
                "type": "org.w3id.cwl.cwl.File",
                "format": "https://www.iana.org/assignments/media-types/application/json",
                "location": "/tmp/random.json",
            },
            CWLIODefinition(name="test", type="File")
        )
    ]
)
def test_get_cwl_io_type_unmodified(io_info, io_def):
    """
    Ensure that the input I/O details do not cause a side effect modification of the data when parsing the definition.

    When :func:`get_cwl_io_type` was called with a definition containing ``type: org.w3id.cwl.cwl.File``, the resulting
    parsing caused the input information to be overriden by ``type: File``. Although they are essentially equivalent
    once resolved, this modification performed before :mod:`cwltool` had the time to parse the definition made it
    incorrectly resolve ``class: File``, which in turn, caused :class:`cwltool.pathmapper.PathMapper` to be missing
    the mapped ``location`` of provided inputs, leading to full :term:`CWL` execution failure.

    .. seealso::
        - https://github.com/crim-ca/weaver/pull/546
    """
    io_copy = deepcopy(io_info)
    io_res = get_cwl_io_type(io_info)
    assert io_res == io_def
    assert io_info == io_copy, "Argument I/O information should not be modified from parsing."


def test_parse_cwl_array_type_explicit_invalid_item():
    io_info = {
        "name": "test",
        "type": {
            "type": "array",
            "items": "unknown-type-item"
        }
    }
    with pytest.raises(PackageTypeError):
        parse_cwl_array_type(io_info)


def test_parse_cwl_array_type_shorthand_invalid_item():
    """
    In case of shorthand syntax, because type is only a string, it shouldn't raise.

    Type is returned as is and value validation is left to later calls.
    """
    io_info = {
        "name": "test",
        "type": "unknown[]"
    }
    try:
        res = parse_cwl_array_type(io_info)
        assert res.array is False
        assert res.enum is False
        assert res.type == "unknown[]"
        assert res.mode == MODE.NONE
        assert res.symbols == AnyValue
    except PackageTypeError:
        pytest.fail("should not raise an error in this case")


def test_parse_cwl_array_type_not_array():
    io_info = {
        "name": "test",
        "type": "float",
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is False
    assert res.type == "float"
    assert res.mode == MODE.NONE
    assert res.symbols == AnyValue


def test_parse_cwl_array_type_simple_enum():
    io_info = {
        "name": "test",
        "type": "enum",
        "symbols": ["a", "b", "c"]
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is False
    assert res.enum is True
    assert res.type == "string"
    assert res.mode == MODE.SIMPLE
    assert res.symbols == ["a", "b", "c"]


def test_parse_cwl_array_type_explicit_base():
    io_info = {
        "name": "test",
        "type": {
            "type": "array",
            "items": "string"
        }
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is True
    assert res.enum is False
    assert res.type == "string"
    assert res.mode == MODE.NONE
    assert res.symbols == AnyValue


def test_parse_cwl_array_type_explicit_enum():
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
    res = parse_cwl_array_type(io_info)
    assert res.array is True
    assert res.enum is True
    assert res.type == "string"
    assert res.mode == MODE.SIMPLE
    assert res.symbols == ["a", "b", "c"]


def test_parse_cwl_array_type_shorthand_base():
    io_info = {
        "name": "test",
        "type": "string[]",
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is True
    assert res.enum is False
    assert res.type == "string"
    assert res.mode == MODE.NONE
    assert res.symbols == AnyValue


def test_parse_cwl_array_type_shorthand_enum():
    io_info = {
        "name": "test",
        "type": "enum[]",
        "symbols": ["a", "b", "c"]
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is True
    assert res.enum is True
    assert res.type == "string"
    assert res.mode == MODE.SIMPLE
    assert res.symbols == ["a", "b", "c"]


def test_parse_cwl_array_type_explicit_optional_not_array():
    io_info = {
        "name": "test",
        "type": ["null", "float"],
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is False
    assert res.enum is False
    assert res.type == "float"
    assert res.mode == MODE.NONE
    assert res.symbols == AnyValue


def test_parse_cwl_array_type_explicit_optional_simple_enum():
    io_info = {
        "name": "test",
        "type": ["null", "enum"],
        "symbols": ["a", "b", "c"]
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is False
    assert res.enum is False
    assert res.type == "enum"
    assert res.mode == MODE.NONE
    assert res.symbols == AnyValue


def test_parse_cwl_array_type_explicit_optional_explicit_base():
    io_info = {
        "name": "test",
        "type": [
            "null",
            {"type": "array", "items": "string"}
        ]
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is True
    assert res.enum is False
    assert res.type == "string"
    assert res.mode == MODE.NONE
    assert res.symbols == AnyValue


def test_parse_cwl_array_type_explicit_optional_explicit_enum():
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
    res = parse_cwl_array_type(io_info)
    assert res.array is True
    assert res.enum is True
    assert res.type == "string"
    assert res.mode == MODE.SIMPLE
    assert res.symbols == ["a", "b", "c"]


def test_parse_cwl_array_type_explicit_optional_shorthand_base():
    io_info = {
        "name": "test",
        "type": ["null", "string[]"]
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is True
    assert res.enum is False
    assert res.type == "string"
    assert res.mode == MODE.NONE
    assert res.symbols == AnyValue


def test_parse_cwl_array_type_explicit_optional_shorthand_enum():
    io_info = {
        "name": "test",
        "type": ["null", "enum[]"],
        "symbols": ["a", "b", "c"]
    }
    res = parse_cwl_array_type(io_info)
    assert res.array is True
    assert res.enum is True
    assert res.type == "string"
    assert res.mode == MODE.SIMPLE
    assert res.symbols == ["a", "b", "c"]


def test_parse_cwl_enum_type_string():
    io_info = {
        "name": "test",
        "type": {
            "type": "enum",
            "symbols": ["a", "b", "c"]
        }
    }
    res = parse_cwl_enum_type(io_info)
    assert res.array is False
    assert res.enum is True
    assert res.type == "string"
    assert res.mode == MODE.SIMPLE
    assert res.symbols == ["a", "b", "c"]


def test_parse_cwl_enum_type_float():
    io_info = {
        "name": "test",
        "type": {
            "type": "enum",
            "symbols": [1.9, 2.8, 3.7]
        }
    }
    res = parse_cwl_enum_type(io_info)
    assert res.array is False
    assert res.enum is True
    assert res.type == "float"
    assert res.mode == MODE.SIMPLE
    assert res.symbols == [1.9, 2.8, 3.7]


def test_parse_cwl_enum_type_int():
    io_info = {
        "name": "test",
        "type": {
            "type": "enum",
            "symbols": [1, 2, 3]
        }
    }
    res = parse_cwl_enum_type(io_info)
    assert res.array is False
    assert res.enum is True
    assert res.type == "int"
    assert res.mode == MODE.SIMPLE
    assert res.symbols == [1, 2, 3]


def test_is_cwl_complex_type_guaranteed_file():
    io_info = {
        "name": "test",
        "type": "File"
    }
    assert is_cwl_complex_type(io_info)


def test_is_cwl_complex_type_potential_file():
    io_info = {
        "name": "test",
        "type": ["null", "File"]
    }
    assert is_cwl_complex_type(io_info)


def test_is_cwl_complex_type_file_array():
    io_info = {
        "name": "test",
        "type": {"type": "array", "items": "File"}
    }
    assert is_cwl_complex_type(io_info)


def test_is_cwl_complex_type_none_one_or_many_files():
    io_info = {
        "name": "test",
        "type": [
            "null",
            "File",
            {"type": "array", "items": "File"}
        ]
    }
    assert is_cwl_complex_type(io_info)


@pytest.mark.parametrize("test_type", [
    "int",
    "string",
    "float",
    ["null", "string"],
    {"type": "enum", "symbols": [1, 2]},
    {"type": "enum", "symbols": ["A", "B"]},
    {"type": "array", "items": "string"},
    {"type": "array", "items": "int"},
    ["null", {"type": "array", "items": "string"}],
])
def test_is_cwl_complex_type_not_files(test_type):
    io_info = {"name": "test", "type": test_type}
    assert not is_cwl_complex_type(io_info)


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


def assert_formats_equal_any_order(result_formats, expect_formats):
    # type: (List[Format], List[Format]) -> None
    assert_equal_any_order(result_formats, expect_formats,
                           comparer=lambda res, exp: res.json == exp.json,
                           formatter=lambda fmt: str(fmt.json))


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


@pytest.mark.parametrize(
    ["values", "expect"],
    [
        (
            {"test": {"class": "File", "path": "https://example.com/random.txt"}},
            {"test": {"href": "https://example.com/random.txt"}}
        ),
        (
            {
                "test": {
                    "class": "File",
                    "path": "https://example.com/random.nc",
                    "format": get_cwl_file_format(ContentType.APP_NETCDF, make_reference=True),
                }
            },
            {
                "test": {
                    "href": "https://example.com/random.nc",
                    "type": ContentType.APP_NETCDF,
                    "format": {
                        "mediaType": ContentType.APP_NETCDF,
                    }
                }
            }
        ),
        (
            {
                "test": {
                    "class": "File",
                    "path": "https://example.com/random.bin",
                    "format": get_cwl_file_format(ContentType.APP_OCTET_STREAM, make_reference=True),
                    "encoding": ContentEncoding.BASE64,
                }
            },
            {
                "test": {
                    "href": "https://example.com/random.bin",
                    "type": ContentType.APP_OCTET_STREAM,
                    "format": {
                        "mediaType": ContentType.APP_OCTET_STREAM,
                        "encoding": ContentEncoding.BASE64,
                    }
                }
            }
        ),
        (
            {
                "test": {
                    "class": "File",
                    "path": "https://example.com/random.zip",
                    # ZIP 'Format' object itself defines 'encoding'
                    "format": get_cwl_file_format(ContentType.APP_ZIP, make_reference=True),
                }
            },
            {
                "test": {
                    "href": "https://example.com/random.zip",
                    "type": ContentType.APP_ZIP,
                    "format": {
                        "mediaType": ContentType.APP_ZIP,
                        "encoding": ContentEncoding.BASE64,
                    }
                }
            }
        ),
    ],
)
def test_cwl2json_input_values_cwl_format(values, expect):
    result = cwl2json_input_values(values, ProcessSchema.OGC)
    assert result == expect


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
        "test4": {"href": "/tmp/random.txt"},  # nosec: B108
        "test5": [{"value": "val1"}, {"value": "val2"}],
        "test6": [{"value": 1}, {"value": 2}],
        "test7": [{"value": 1.23}, {"value": 4.56}],
        "test8": [{"href": "/tmp/other.txt"}]  # nosec: B108
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
        {"id": "test12", "href": "/data/file1.txt", "format": {"mediaType": "text/plain"}},
        {"id": "test12", "href": "/data/file2.txt", "format": {"mediaType": "text/plain"}},
        {"id": "test12", "href": "/data/file3.txt", "format": {"mediaType": "text/plain"}},
        {"id": "test13", "value": "short"},
        {"id": "test13", "value": "long"},
        {"id": "test13", "value": "more"},
        {"id": "test14", "value": ["val1", "val2", "val3"]},
        {"id": "test15", "href": "https://www.somewebsite.com/dir1/", "type": "application/directory"},
        {"id": "test15", "href": "https://www.somewebsite.com/dir2/", "type": "application/directory"},
        {"id": "test15", "href": "https://www.somewebsite.com/dir3/", "type": "application/directory"},
        {"id": "test16", "value": 1},
        {"id": "test16", "value": ["val1", "val2", "val3"]},
        {"id": "test16", "value": "short"},
        {"id": "test16", "href": "https://www.somewebsite.com/dir1/", "type": "application/directory"}
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
        ],
        "test12": [
            {"href": "/data/file1.txt", "format": {"mediaType": "text/plain"}},
            {"href": "/data/file2.txt", "format": {"mediaType": "text/plain"}},
            {"href": "/data/file3.txt", "format": {"mediaType": "text/plain"}}
        ],
        "test13": [
            "short",
            "long",
            "more"
        ],
        "test14": [
            "val1",
            "val2",
            "val3",
        ],
        "test15": [
            {"href": "https://www.somewebsite.com/dir1/", "type": "application/directory"},
            {"href": "https://www.somewebsite.com/dir2/", "type": "application/directory"},
            {"href": "https://www.somewebsite.com/dir3/", "type": "application/directory"}
        ],
        "test16": [
            1,
            ["val1", "val2", "val3"],
            "short",
            {"href": "https://www.somewebsite.com/dir1/",
             "type": "application/directory"}
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
        ],
        "test12": [
            {"href": "/data/file1.txt", "format": {"mediaType": "text/plain"}},
            {"href": "/data/file2.txt", "format": {"mediaType": "text/plain"}},
            {"href": "/data/file3.txt", "format": {"mediaType": "text/plain"}}
        ],
        "test13": [
            "short",
            "long",
            "more"
        ],
        "test14": [
            {"href": "https://www.somewebsite.com/dir1/", "type": "application/directory"},
            {"href": "https://www.somewebsite.com/dir2/", "type": "application/directory"},
            {"href": "https://www.somewebsite.com/dir3/", "type": "application/directory"}
        ],
        "test15": [
            1,
            ["val1", "val2", "val3"],
            "short",
            {"href": "https://www.somewebsite.com/dir1/",
             "type": "application/directory"}
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
        {"id": "test12", "href": "/data/file1.txt", "format": {"mediaType": "text/plain"}},
        {"id": "test12", "href": "/data/file2.txt", "format": {"mediaType": "text/plain"}},
        {"id": "test12", "href": "/data/file3.txt", "format": {"mediaType": "text/plain"}},
        {"id": "test13", "value": "short"},
        {"id": "test13", "value": "long"},
        {"id": "test13", "value": "more"},
        {"id": "test14", "href": "https://www.somewebsite.com/dir1/", "type": "application/directory"},
        {"id": "test14", "href": "https://www.somewebsite.com/dir2/", "type": "application/directory"},
        {"id": "test14", "href": "https://www.somewebsite.com/dir3/", "type": "application/directory"},
        {"id": "test15", "value": 1},
        {"id": "test15", "value": ["val1", "val2", "val3"]},
        {"id": "test15", "value": "short"},
        {"id": "test15", "href": "https://www.somewebsite.com/dir1/", "type": "application/directory"}
    ]
    assert convert_input_values_schema(inputs_ogc, ProcessSchema.OGC) == inputs_ogc
    assert convert_input_values_schema(inputs_ogc, ProcessSchema.OLD) == inputs_old


@pytest.mark.xfail(reason="Expected to fail as conversion is probably not standard compliant")
def test_convert_input_values_schema_from_old_xfail():
    inputs_old = [
        {
            "id": "test1",
            "href": ["https://www.somewebsite.com/dir1/",
                     "https://www.somewebsite.com/dir2/",
                     "https://www.somewebsite.com/dir3/"],
            "type": "application/directory"
        }
    ]

    inputs_ogc = {
        "test1": {"href": ["https://www.somewebsite.com/dir1/",
                           "https://www.somewebsite.com/dir2/",
                           "https://www.somewebsite.com/dir3/"],
                  "type": "application/directory"}
    }

    assert convert_input_values_schema(inputs_old, ProcessSchema.OLD) == inputs_old
    assert convert_input_values_schema(inputs_old, ProcessSchema.OGC) == inputs_ogc


@pytest.mark.xfail(reason="Expected to fail as conversion is probably not standard compliant")
def test_convert_input_values_schema_from_ogc_xfail():
    inputs_ogc = {
        "test1": {"href": ["https://www.somewebsite.com/dir1/",
                           "https://www.somewebsite.com/dir2/",
                           "https://www.somewebsite.com/dir3/"],
                  "type": "application/directory"}
    }

    inputs_old = [
        {
            "id": "test1",
            "href": ["https://www.somewebsite.com/dir1/",
                     "https://www.somewebsite.com/dir2/",
                     "https://www.somewebsite.com/dir3/"],
            "type": "application/directory"
        }
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
        {"id": "test8", "href": "/tmp/other.txt"},  # nosec: B108
        {"id": "test9", "value": "short"},
        {"id": "test10", "value": "long"},
        {"id": "test11", "href": "/tmp/file.json", "format": {  # nosec: B108
            "mediaType": ContentType.APP_JSON, "schema": "http://schema.org/random.json"
        }},
        {"id": "test12", "href": "/tmp/other.xml", "format": {  # nosec: B108
            "mediaType": ContentType.TEXT_XML, "schema": "http://schema.org/random.xml"
        }},
        {"id": "test13", "href": "/tmp/one.json", "format": {"mediaType": ContentType.APP_JSON}},  # nosec: B108
        {"id": "test13", "href": "/tmp/two.xml", "format": {"mediaType": ContentType.TEXT_XML}},   # nosec: B108
    ]
    result = repr2json_input_values(values)
    assert result == expect


@pytest.mark.parametrize(
    ["name", "expect"],
    [
        ("test", "test"),
        (CWL_REQUIREMENT_SECRETS, CWL_REQUIREMENT_SECRETS),
        (f"{CWL_NAMESPACE_CWLTOOL_URL}Secrets", CWL_REQUIREMENT_SECRETS),
        ("file:///tmp/random/package#message", "message"),
        (f"file:///tmp/random/{CWL_REQUIREMENT_APP_WPS1}", CWL_REQUIREMENT_APP_WPS1),
    ]
)
def test_resolve_cwl_namespaced_name(name, expect):
    result = resolve_cwl_namespaced_name(name)
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
            "output": {
                "type": "File", "format": "ogc:geotiff",
                "outputBinding": {
                    "glob": "*.tiff"  # "output/*.tiff" only during Workflow step execution
                }
            },
        },
        "$namespaces": cwl_ns
    }
    assert info != body
    body["executionUnit"] = [{"unit": cwl}]
    body["deploymentProfile"] = "http://www.opengis.net/profiles/eoc/ogcapiApplication"
    assert info == body, "Process information should be updated with minimal details since no CWL detected in input."


@pytest.mark.parametrize(
    ["input_str", "input_int", "input_float", "input_time"],
    [
        # OpenAPI schema references
        (
            {"schema": {"type": "string", "enum": ["a", "b", "c"]}},
            {"schema": {"type": "integer", "enum": [1, 2, 3]}},
            {"schema": {"type": "number", "format": "float", "enum": [1.2, 3.4]}},
            {"schema": {"type": "string", "format": "time", "enum": ["12:00", "24:00"]}},
        ),
        # OGC-API input definitions
        (
            {"data_type": "string", "allowed_values": ["a", "b", "c"]},
            {"data_type": "integer", "allowed_values": [1, 2, 3]},
            {"data_type": "float", "allowed_values": [1.2, 3.4]},
            {"data_type": "string", "allowed_values": ["12:00", "24:00"]},
        ),
    ]
)
def test_ogcapi2cwl_process_cwl_enum_updated(input_str, input_int, input_float, input_time):
    """
    Test that a :term:`CWL` with pseudo-``enum`` type has the necessary :term:`CWL` requirements to perform validation.

    .. seealso::
        - :func:`test_any2cwl_io_enum_convert`
        - :func:`test_any2cwl_io_enum_validate`
        - :func:`weaver.processes.convert._convert_cwl_io_enum`
        - :func:`weaver.processes.convert._get_cwl_js_value_from`
        - :func:`weaver.processes.convert._patch_cwl_enum_js_requirement`
    """
    href = "https://remote-server.com/processes/test-process"
    body = {
        "inputs": {
            "enum-str": input_str,
            "enum-int": input_int,
            "enum-float": input_float,
            "enum-time": input_time,
        },
        "outputs": {
            "output": {"schema": {"type": "string", "contentMediaType": ContentType.TEXT_PLAIN}},
        }
    }
    cwl, info = ogcapi2cwl_process(body, href)
    assert info is not body, "copy should be created, not inplace modifications"
    assert cwl["requirements"] == {CWL_REQUIREMENT_INLINE_JAVASCRIPT: {}}
    assert cwl["hints"] == {CWL_REQUIREMENT_APP_OGC_API: {"process": href}}

    assert cwl["inputs"]["enum-str"]["type"] == {"type": "enum", "symbols": ["a", "b", "c"]}
    assert "inputBinding" not in cwl["inputs"]["enum-str"]

    assert cwl["inputs"]["enum-int"]["type"] == "int"
    assert "symbols" not in cwl["inputs"]["enum-int"]
    cwl_value_from = cwl["inputs"]["enum-int"]["inputBinding"]["valueFrom"].strip()
    assert cwl_value_from.startswith("${") and cwl_value_from.endswith("}")
    assert "[1, 2, 3]" in cwl_value_from
    assert "values.includes(self)" in cwl_value_from
    assert "self.every(item => values.includes(item))" not in cwl_value_from

    assert cwl["inputs"]["enum-float"]["type"] == "float"
    assert "symbols" not in cwl["inputs"]["enum-float"]
    cwl_value_from = cwl["inputs"]["enum-float"]["inputBinding"]["valueFrom"].strip()
    assert cwl_value_from.startswith("${") and cwl_value_from.endswith("}")
    assert "[1.2, 3.4]" in cwl_value_from
    assert "values.includes(self)" in cwl_value_from
    assert "self.every(item => values.includes(item))" not in cwl_value_from

    assert cwl["inputs"]["enum-time"] == {"type": {"type": "enum", "symbols": ["#12:00", "#24:00"]}}
    assert "inputBinding" not in cwl["inputs"]["enum-time"]


@pytest.mark.parametrize(
    ["cwl_io", "wps_io_expected"],
    [
        (
            {
                "name": "test",
                "type": "enum",
                "symbols": ["#12:00", "#24:00"],
            },
            {
                "id": "test",
                "allowed_values": ["12:00", "24:00"],
            }
        ),
        (
            {
                "name": "test",
                "type": {
                    "type": "enum",
                    "symbols": ["#12:00", "#24:00"],
                }
            },
            {
                "id": "test",
                "allowed_values": ["12:00", "24:00"],
            }
        ),
        (
            {
                "name": "test",
                "type": {
                    "type": "array",
                    "items": {
                        "type": "enum",
                        "symbols": ["#12:00", "#24:00"],
                    }
                }
            },
            {
                "id": "test",
                "allowed_values": ["12:00", "24:00"],
                "min_occurs": 1,
            }
        ),
        (
            {
                "name": "test",
                "type": [
                    "null",
                    {
                        "type": "array",
                        "items": {
                            "type": "enum",
                            "symbols": ["#12:00", "#24:00"],
                        }
                    }
                ]
            },
            {
                "id": "test",
                "allowed_values": ["12:00", "24:00"],
                "min_occurs": 1,
            }
        )
    ]
)
def test_patched_cwl_enum_colon_back_conversion(cwl_io, wps_io_expected):
    """
    Given a :term:`CWL` ``enum`` that contains ``:`` characters patched with prefixed ``#`` test the inverse conversion.
    """
    wps_io = cwl2wps_io(cwl_io, IO_INPUT)
    wps_allow = [allow.value for allow in wps_io.allowed_values]
    assert wps_allow == ["12:00", "24:00"]


@mocked_remote_server_requests_wps1([
    resources.TEST_REMOTE_SERVER_URL,
    resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
    [resources.WPS_LITERAL_ENUM_IO_XML]
])
def test_xml_wps2cwl_enum_updated():
    """
    Test that a :term:`CWL` with pseudo-``Enum`` type has the necessary :term:`CWL` requirements to perform validation.

    .. seealso::
        - :func:`test_any2cwl_io_enum_convert`
        - :func:`test_any2cwl_io_enum_validate`
    """
    prov = resources.TEST_REMOTE_SERVER_URL
    href = f"{prov}?service=WPS&version=1.0.0&request=DescribeProcess&identifier={resources.WPS_LITERAL_ENUM_IO_ID}"
    body = resources.load_resource("wps_literal_enum_io.xml")
    resp = MockedResponse()
    resp.url = href
    resp.content = body
    cwl, _ = xml_wps2cwl(resp, {})  # type: ignore
    cwl_inputs = {cwl_io["id"]: cwl_io for cwl_io in cwl["inputs"]}

    assert cwl["requirements"] == {CWL_REQUIREMENT_INLINE_JAVASCRIPT: {}}
    assert cwl["hints"] == {CWL_REQUIREMENT_APP_WPS1: {"provider": prov, "process": resources.WPS_LITERAL_ENUM_IO_ID}}

    assert cwl_inputs["enum-str"]["type"] == [
        "null",
        {"type": "enum", "symbols": ["A", "B", "C"]}
    ]
    assert "inputBinding" not in cwl_inputs["enum-str"]

    assert cwl_inputs["enum-array-str"]["type"] == {
        "type": "array",
        "items": {"type": "enum", "symbols": ["A", "B", "C"]}
    }
    assert "inputBinding" not in cwl_inputs["enum-array-str"]

    assert cwl_inputs["enum-int"]["type"] == ["null", "int"]
    assert "symbols" not in cwl_inputs["enum-int"]
    cwl_value_from = cwl_inputs["enum-int"]["inputBinding"]["valueFrom"].strip()
    assert cwl_value_from.startswith("${") and cwl_value_from.endswith("}")
    assert "[1, 2, 3]" in cwl_value_from
    assert "values.includes(self)" in cwl_value_from
    assert "self.every(item => values.includes(item))" not in cwl_value_from

    assert cwl_inputs["enum-array-int"]["type"] == {"type": "array", "items": "int"}
    assert "symbols" not in cwl_inputs["enum-array-int"]
    cwl_value_from = cwl_inputs["enum-array-int"]["inputBinding"]["valueFrom"].strip()
    assert cwl_value_from.startswith("${") and cwl_value_from.endswith("}")
    assert "[1, 2, 3]" in cwl_value_from
    assert "values.includes(self)" not in cwl_value_from
    assert "self.every(item => values.includes(item))" in cwl_value_from

    assert cwl_inputs["enum-float"]["type"] == "float"
    assert "symbols" not in cwl_inputs["enum-float"]
    cwl_value_from = cwl_inputs["enum-float"]["inputBinding"]["valueFrom"].strip()
    assert cwl_value_from.startswith("${") and cwl_value_from.endswith("}")
    assert "[1.2, 3.4, 5.6]" in cwl_value_from
    assert "values.includes(self)" in cwl_value_from
    assert "self.every(item => values.includes(item))" not in cwl_value_from

    assert cwl_inputs["enum-array-float"]["type"] == ["null", "float", {"type": "array", "items": "float"}]
    assert "symbols" not in cwl_inputs["enum-array-float"]
    cwl_value_from = cwl_inputs["enum-array-float"]["inputBinding"]["valueFrom"].strip()
    assert cwl_value_from.startswith("${") and cwl_value_from.endswith("}")
    assert "[1.2, 3.4, 5.6]" in cwl_value_from
    assert "values.includes(self)" in cwl_value_from
    assert "self.every(item => values.includes(item))" in cwl_value_from


@pytest.mark.parametrize(
    ["io_schema", "io_expected"],
    [
        (
            {
                "type": "object",
                "required": ["measurement", "uom"],
                "properties": {
                    "measurement": {"type": "number"},
                    "uom": {"type": "string"},  # generic representation, will not convert units
                    "reference": {"type": "string", "format": "uri"},
                }
            },
            {
                "data_type": "float",
                "type": "literal",
            }
        ),
        (
            {
                "type": "object",
                "required": ["measurement", "uom"],
                "properties": {
                    "measurement": {"type": "number"},
                    "uom": {
                        "type": "string",
                        "default": "m",
                    },
                    "reference": {"type": "string", "format": "uri"},
                }
            },
            {
                "data_type": "float",
                "type": "literal",
                "uom": {"uom": "m", "reference": ""}
            }
        ),
        (
            {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    "required": ["measurement", "uom"],
                    "properties": {
                        "measurement": {"type": "number"},
                        "uom": {"type": "string"},  # generic representation, will not convert units
                        "reference": {"type": "string", "format": "uri"},
                    }
                }
            },
            {
                "data_type": "float",
                "type": "literal",
                "minOccurs": 2,
            }
        ),
        (
            {
                "type": "object",
                "required": ["measurement", "uom"],
                "properties": {
                    "measurement": {"type": "number"},
                    "uom": {"type": "string", "const": "m"},  # specific unit, auto-convert unit/values
                    "reference": {"type": "string", "format": "uri"},
                }
            },
            {
                "data_type": "float",
                "type": "literal",
                "uoms": [{"uom": "m", "reference": ""}],
            }
        ),
        (
            {
                "type": "array",
                "minItems": 2,
                "items": {
                    "type": "object",
                    "required": ["measurement", "uom"],
                    "properties": {
                        "measurement": {"type": "number"},
                        "uom": {"type": "string", "enum": ["s", "h"]},  # specific unit, auto-convert unit/values
                        "reference": {"type": "string", "format": "uri"},
                    }
                }
            },
            {
                "data_type": "float",
                "type": "literal",
                "uoms": [{"uom": "s", "reference": ""}, {"uom": "h", "reference": ""}],
                "minOccurs": 2,
            }
        ),
        (
            {
                "type": "object",
                "required": ["measurement", "uom"],
                "properties": {
                    "measurement": {"type": "number"},
                    "uom": {
                        "type": "string",
                        "enum": ["random"],  # unknown unit
                    },
                }
            },
            pint.PintError,
        ),
        (
            {
                "type": "object",
                "required": ["measurement", "uom"],
                "properties": {
                    "measurement": {"type": "number"},
                    "uom": {
                        "type": "string",
                        "enum": [],  # bad
                    },
                }
            },
            ValueError,
        ),
        (
            {
                "type": "object",
                "required": ["measurement", "uom"],
                "properties": {
                    "measurement": {"type": "number"},
                    "uom": {
                        "type": "string",
                        "enum": ["m"],
                    },
                    "reference": {
                        "type": "string",
                        "enum": ["", "", ""],  # bad, must match UoM amount
                    },
                }
            },
            ValueError,
        )
    ]
)
def test_oas2json_io_convert_literal_uom_definition(io_schema, io_expected):
    try:
        io_result = oas2json_io(io_schema)
    except Exception as exc:
        if isinstance(io_expected, type) and issubclass(io_expected, Exception):
            assert isinstance(exc, io_expected)
        else:
            pytest.fail(f"Exception not expected: [{exc}]")
    else:
        if isinstance(io_expected, type) and issubclass(io_expected, Exception):
            pytest.fail(f"Expected [{io_expected}] did not raise.")
        assert io_result == io_expected


@pytest.mark.parametrize(
    ["uoms", "expect"],
    [
        (
            [UOM("m"), {"uom": "km"}, {"uom": "ft"}],
            [UOM("m"), UOM("km"), UOM("ft")],
        ),
        (
            [UOM("m"), None],
            null,
        ),
        (
            [UOM("m"), {}],
            null,
        ),
        (
            [UOM("m"), "random"],
            null,
        ),
        (
            [],
            null,
        ),
        (
            {},
            null,
        ),
    ]
)
def test_json2wps_supported_uoms(uoms, expect):
    data = {"uoms": uoms}
    result = json2wps_supported_uoms(data)
    assert result == expect


@pytest.mark.parametrize(
    ["ows_io", "json_io"],
    [
        (
            {
                "identifier": "test",
                "type": "float",
                "data_type": "float",
                "uoms": [{"uom": "m", "reference": ""}, {"uom": "ft", "reference": ""}],
                "uom": {"uom": "m", "reference": "urn:ogc:def:uom:OGC:1.0:metre"},
            },
            {
                "id": "test",
                "literalDataDomains": [
                    {
                        "default": True,
                        "valueDefinition": {"anyValue": False},
                        "dataType": {"name": "float"},
                        "UOMs": {
                            "default": {"uom": "m", "reference": "urn:ogc:def:uom:OGC:1.0:metre"},
                            "supported": [{"uom": "m", "reference": ""}, {"uom": "ft", "reference": ""}],
                        },
                    }
                ],
            },
        )
    ]
)
def test_ows2json_io_convert_literal_uom(ows_io, json_io):
    result = ows2json_io(ows_io)  # type: ignore
    for key in ows_io:  # avoid copying everything to make test definitions easier
        result.pop(key, None)
    assert result == json_io


def test_ows_wps_json_default_complex_format():
    xml_io = xml_util.parse(resources.WPS_COMPLEX_OPTIONAL_IO_XML).xpath("//DataInputs/Input")[0]
    ows_io = OWSInput(xml_io)
    res_io = ows2json_io(ows_io)
    assert res_io == {
        "id": "test",
        "title": "test",
        "min_occurs": 0,
        "max_occurs": 100,
        "any_value": False,
        "type": WPS_COMPLEX_DATA,
        "data_type": WPS_COMPLEX_DATA,
        "data_format": {
            "mimeType": ContentType.APP_NETCDF,
            "encoding": "base64",
            "maximumMegabytes": 200,
            "schema": None,
            "default": True,
        },
        "formats": [
            {
                "mimeType": ContentType.APP_NETCDF,
                "encoding": "base64",
                "maximumMegabytes": 200,
                "schema": None,
                "default": True,
            },
            {
                "mimeType": ContentType.APP_JSON,
                "encoding": None,
                "maximumMegabytes": 200,
                "schema": None,
                "default": False,
            },
        ],
    }

    wps_io = json2wps_io(res_io, "input")
    assert wps_io.identifier == "test"
    assert wps_io.title == "test"
    assert wps_io.min_occurs == 0
    assert wps_io.max_occurs == 100
    assert wps_io.data_format == Format(ContentType.APP_NETCDF, encoding="base64")
    assert all(wps_fmt == val_fmt for wps_fmt, val_fmt in zip(
        wps_io.supported_formats,
        [
            Format(ContentType.APP_NETCDF, encoding="base64"),
            Format(ContentType.APP_JSON),
        ],
    ))

    # ensure no defaults applied
    assert wps_io.data is None
    assert wps_io._default is None

    res_io = wps2json_io(wps_io)
    assert res_io == {
        "id": "test",
        "title": "test",
        "description": "",
        "keywords": [],
        "metadata": [],
        "translations": None,
        "asreference": False,
        "workdir": None,
        "minOccurs": "0",
        "maxOccurs": "100",
        "mode": MODE.NONE,
        "type": WPS_COMPLEX,
        "data_format": {"mime_type": ContentType.APP_NETCDF, "encoding": "base64", "schema": "", "extension": ""},
        "formats": [
            {"mediaType": ContentType.APP_NETCDF, "encoding": "base64", "schema": "", "extension": "", "default": True},
            {"mediaType": ContentType.APP_JSON, "encoding": "", "schema": "", "extension": "", "default": False}
        ],
        # from default data_format
        "mimetype": ContentType.APP_NETCDF,
        "encoding": "base64",
    }


@pytest.mark.parametrize(
    ["value", "dtype", "ctype", "expect"],
    [
        # note: OWSLib encodes literal data as array of string since parsed from XML
        (
            [123456],
            "integer",
            None,
            {"data": 123456, "dataType": "integer"},
        ),
        (
            [MockBboxElementXML([1, 2, 3, 4], Crs("EPSG:4326"))],  # auto-resolve axis order YX
            WPS_BOUNDINGBOX_DATA,
            None,
            {
                "dataType": WPS_BOUNDINGBOX_DATA,
                "data": {
                    "crs": "urn:ogc:def:crs:EPSG::4326",
                    "bbox": [2., 1., 4., 3.],
                    "format": OGC_API_BBOX_FORMAT,
                    "schema": OGC_API_BBOX_SCHEMA,
                }
            },
        ),
        (
            [MockBboxElementXML([1, 2, 3, 4], Crs("CRS:84"))],  # auto-resolve axis order XY
            WPS_BOUNDINGBOX_DATA,
            None,
            {
                "dataType": WPS_BOUNDINGBOX_DATA,
                "data": {
                    "crs": "urn:ogc:def:crs:CRS::84",
                    "bbox": [1., 2., 3., 4.],
                }
            },
        ),
        (
            [MockBboxElementXML([1, 2, 3, 4], Crs("custom", axisorder="xy"))],
            WPS_BOUNDINGBOX_DATA,
            None,
            {"dataType": WPS_BOUNDINGBOX_DATA, "data": {"crs": "urn:ogc:def:crs:::-1", "bbox": [1., 2., 3., 4.]}},
        ),
        (
            ["random"],
            WPS_COMPLEX_DATA,
            ContentType.TEXT_PLAIN,
            {"data": None, "dataType": WPS_COMPLEX_DATA, "mimeType": ContentType.TEXT_PLAIN},
        ),
        (
            [[1, 2, 3]],
            WPS_COMPLEX_DATA,
            ContentType.APP_JSON,
            {"data": [1, 2, 3], "dataType": WPS_COMPLEX_DATA, "mimeType": ContentType.APP_JSON},
        ),
        (
            [[{"data": 123}, {"xyz": "ok"}]],
            WPS_COMPLEX_DATA,
            ContentType.APP_JSON,
            {"data": [{"data": 123}, {"xyz": "ok"}], "dataType": WPS_COMPLEX_DATA, "mimeType": ContentType.APP_JSON},
        ),
    ]
)
def test_ows2json_output_data(value, dtype, ctype, expect):
    output = OWSOutput(MockElementXML({}))  # skip parsing from XML, inject corresponding results directly
    output.identifier = "test"
    output.title = "TEST"
    output.dataType = dtype
    output.data = value
    if ctype:
        output.mimeType = ctype
    result = ows2json_output_data(output, None, {})  # type: ignore
    expect.update({"identifier": "test", "title": "TEST"})
    assert result == expect


@pytest.mark.parametrize(
    ["value", "uom", "to", "expected"],
    [
        (9.81, "m/s²", "km/min²", 35.316)
    ]
)
def test_convert_value_units_literal_uom(value, uom, to, expected):
    assert convert_value_units(value, uom, to) == expected
