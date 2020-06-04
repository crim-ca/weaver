import tempfile
from collections import OrderedDict
from copy import deepcopy

import pytest
from pytest import fail
from pywps.app import WPSRequest
from pywps.inout.formats import Format
from pywps.inout.literaltypes import AnyValue
from pywps.validator.mode import MODE

from weaver.datatype import Process
from weaver.exceptions import PackageTypeError
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_NETCDF, CONTENT_TYPE_APP_XML, CONTENT_TYPE_TEXT_PLAIN
from weaver.processes.constants import WPS_LITERAL
from weaver.processes.wps_package import _are_different_and_set  # noqa: W0212
from weaver.processes.wps_package import _get_package_ordered_io  # noqa: W0212
from weaver.processes.wps_package import _is_cwl_array_type  # noqa: W0212
from weaver.processes.wps_package import _is_cwl_enum_type  # noqa: W0212
from weaver.processes.wps_package import _json2wps_datatype  # noqa: W0212
from weaver.processes.wps_package import _merge_io_formats  # noqa: W0212
from weaver.processes.wps_package import DEFAULT_FORMAT, WpsPackage
from weaver.utils import null


class ObjectWithEqProperty(object):
    """Dummy object for some test evaluations."""
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


def test_get_package_ordered_io_with_builtin_dict_and_hints():
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
    result = _get_package_ordered_io(test_inputs, test_wps_hints)
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


def test_get_package_ordered_io_with_ordered_dict():
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
    result = _get_package_ordered_io(test_inputs)
    assert isinstance(result, list) and len(result) == len(expected_result)
    assert result == expected_result


def test_get_package_ordered_io_with_list():
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
    result = _get_package_ordered_io(deepcopy(expected_result))
    assert isinstance(result, list) and len(result) == len(expected_result)
    assert result == expected_result


def test_json2wps_datatype():
    # pylint: disable=C0326,bad-whitespace
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


def test_is_cwl_array_type_explicit_optional_not_array():
    io_info = {
        "name": "test",
        "type": ["null", "float"],
    }
    res = _is_cwl_array_type(io_info)
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
    res = _is_cwl_array_type(io_info)
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
    res = _is_cwl_array_type(io_info)
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
    res = _is_cwl_array_type(io_info)
    assert res[0] is True
    assert res[1] == "string"
    assert res[2] == MODE.SIMPLE
    assert res[3] == ["a", "b", "c"]


def test_is_cwl_array_type_explicit_optional_shorthand_base():
    io_info = {
        "name": "test",
        "type": ["null", "string[]"]
    }
    res = _is_cwl_array_type(io_info)
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
    assert not format_expect, "Not all expected formats matched {}".format([fmt.json for fmt in format_expect])


def test_merge_io_formats_no_wps():
    wps_fmt = []
    cwl_fmt = [DEFAULT_FORMAT]
    res_fmt = _merge_io_formats(wps_fmt, cwl_fmt)
    assert isinstance(res_fmt, list)
    assert len(res_fmt) == 1
    assert res_fmt[0] is DEFAULT_FORMAT


def test_merge_io_formats_with_wps_and_default_cwl():
    wps_fmt = [Format(CONTENT_TYPE_APP_NETCDF)]
    cwl_fmt = [DEFAULT_FORMAT]
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


def test_stdout_stderr_logging_for_commandline_tool_success():
    """
    Execute a process and assert that stdout is correctly logged to log file.
    """
    process = Process({
        "title": "test-stdout-stderr",
        "id": "test-stdout-stderr",
        "package": {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": "echo",
            "inputs": {
                "message": {
                    "type": "string",
                    "inputBinding": {
                        "position": 1
                    }
                }
            },
            "outputs": {

            }
        }
    })

    payload = process
    package = process["package"]
    title = process["title"]
    identifier = process["id"]

    # WPSPackage._handle()
    log_file = tempfile.NamedTemporaryFile()
    status_location = log_file.name
    workdir = tempfile.TemporaryDirectory()

    class TestWpsPackage(WpsPackage):
        @property
        def status_location(self):
            return status_location

    wps_package_instance = TestWpsPackage(identifier=identifier, title=title, payload=payload, package=package)
    wps_package_instance.set_workdir(workdir.name)

    # WPSRequest mock
    wps_request = WPSRequest()
    wps_request.json = {
        "identifier": "test-stdout-stderr",
        "operation": "execute",
        "version": "1.0.0",
        "language": "null",
        "identifiers": "null",
        "store_execute": "true",
        "status": "true",
        "lineage": "true",
        "raw": "false",
        "inputs": {
            "message": [
                 {
                    "identifier": "message",
                    "title": "A dummy message",
                    "type": "literal",
                    "data_type": "string",
                    "data": "Dummy message",
                    "allowed_values": [

                    ],
                 }
            ]
        },
        "outputs": {

        }
    }

    # ExecuteResponse mock
    wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()

    wps_package_instance._handler(wps_request, wps_response)

    # log assertions
    with open(status_location + ".log", "r") as file:
        log_data = file.read()
        assert "Dummy message" in log_data


def test_stdout_stderr_logging_for_commandline_tool_failure():
    """
    Execute a process and assert that stderr is correctly logged to log file.
    """
    process = Process({
        "title": "test-stdout-stderr",
        "id": "test-stdout-stderr",
        "package": {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": "not_existing_command",
            "inputs": {
                "message": {
                    "type": "string",
                    "inputBinding": {
                        "position": 1
                    }
                }
            },
            "outputs": {

            }
        }
    })

    payload = process
    package = process["package"]
    title = process["title"]
    identifier = process["id"]

    # WPSPackage._handle()
    log_file = tempfile.NamedTemporaryFile()
    status_location = log_file.name
    workdir = tempfile.TemporaryDirectory()

    class TestWpsPackage(WpsPackage):
        @property
        def status_location(self):
            return status_location

    wps_package_instance = TestWpsPackage(identifier=identifier, title=title, payload=payload, package=package)
    wps_package_instance.set_workdir(workdir.name)

    # WPSRequest mock
    wps_request = WPSRequest()
    wps_request.json = {
        "identifier": "test-stdout-stderr",
        "operation": "execute",
        "version": "1.0.0",
        "language": "null",
        "identifiers": "null",
        "store_execute": "true",
        "status": "true",
        "lineage": "true",
        "raw": "false",
        "inputs": {
            "message": [
                 {
                    "identifier": "message",
                    "title": "A dummy message",
                    "type": "literal",
                    "data_type": "string",
                    "data": "Dummy message",
                    "allowed_values": [

                    ],
                 }
            ]
        },
        "outputs": {

        }
    }

    # ExecuteResponse mock
    wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()

    from weaver.exceptions import PackageExecutionError

    try:
        wps_package_instance._handler(wps_request, wps_response)
    except PackageExecutionError as exception:
        assert "Completed permanentFail" in exception.args[0]
    else:
        fail("\"wps_package._handler()\" was expected to throw \"PackageExecutionError\" exception")