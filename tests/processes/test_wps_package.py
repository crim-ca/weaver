# noinspection PyProtectedMember
from weaver.processes.wps_package import _json2wps_datatype, WPS_LITERAL
from copy import deepcopy


def test_json2wps_datatype():
    test_cases = [
        ("float",   {"type": WPS_LITERAL, "data_type": "float"}),
        ("integer", {"type": WPS_LITERAL, "data_type": "integer"}),
        ("integer", {"type": WPS_LITERAL, "data_type": "int"}),
        ("boolean", {"type": WPS_LITERAL, "data_type": "boolean"}),
        ("boolean", {"type": WPS_LITERAL, "data_type": "bool"}),
        ("string",  {"type": WPS_LITERAL, "data_type": "string"}),
        ("float",   {"type": WPS_LITERAL, "default": 1.0}),
        ("integer", {"type": WPS_LITERAL, "default": 1}),
        ("boolean", {"type": WPS_LITERAL, "default": True}),
        ("string",  {"type": WPS_LITERAL, "default": "1"}),
        ("float",   {"type": WPS_LITERAL, "supported_values": [1.0, 2.0]}),
        ("integer", {"type": WPS_LITERAL, "supported_values": [1, 2]}),
        ("boolean", {"type": WPS_LITERAL, "supported_values": [True, False]}),
        ("string",  {"type": WPS_LITERAL, "supported_values": ["yes", "no"]}),
        ("float",   {"data_type": "float"}),
        ("integer", {"data_type": "integer"}),
        ("integer", {"data_type": "int"}),
        ("boolean", {"data_type": "boolean"}),
        ("boolean", {"data_type": "bool"}),
        ("string",  {"data_type": "string"}),
    ]

    for expect, test_io in test_cases:
        copy_io = deepcopy(test_io)  # can get modified by function
        assert _json2wps_datatype(test_io) == expect, "Failed for [{}]".format(copy_io)
