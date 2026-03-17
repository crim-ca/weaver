"""
Unit tests for utility methods of :mod:`weaver.processes.execute`.

For more in-depth execution tests, see ``tests.functional``.
"""
import base64
import dataclasses
import json
import urllib.parse
import uuid
from typing import TYPE_CHECKING, List, cast

import mock
import pytest
from owslib.wps import BoundingBoxDataInput, ComplexDataInput, Input, Process
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotImplemented

from tests.utils import MockedRequest
from weaver.datatype import Job
from weaver.formats import ContentEncoding, ContentType
from weaver.processes.constants import WPS_BOUNDINGBOX_DATA, WPS_COMPLEX_DATA, WPS_LITERAL, WPS_CategoryType
from weaver.processes.execution import (
    parse_kvp_inputs_outputs,
    parse_wps_inputs,
    parse_kvp_qualified_param,
    submit_job,
    submit_job_from_kvp
)

if TYPE_CHECKING:
    from weaver.processes.convert import OWS_Input_Type
    from weaver.typedefs import JSON


@dataclasses.dataclass
class MockInputDefinition:
    # pylint: disable=C0103  # must use the names employed by OWSLib, even if not standard snake case
    # override Input to skip XML parsing
    identifier: str = "test"
    dataType: WPS_CategoryType = None


class MockProcess:
    # pylint: disable=C0103  # must use the names employed by OWSLib, even if not standard snake case
    # override Process to skip XML parsing
    def __init__(self, inputs: List[Input]) -> None:
        self.identifier = "test"
        self.dataInputs = inputs


@mock.patch(
    # avoid error on database connection not established
    "weaver.processes.execution.log_and_save_update_status_handler",
    lambda *_, **__: lambda *_a, **__kw: None,
)
@pytest.mark.parametrize(
    ["input_data", "input_definition", "expect_input"],
    [
        (
            {"value": None},
            MockInputDefinition(dataType=WPS_LITERAL),
            None,
        ),
        (
            {"value": 1},
            MockInputDefinition(dataType=WPS_LITERAL),
            "1",
        ),
        (
            {"bbox": [1, 2, 3, 4], "crs": "urn:ogc:def:crs:EPSG::4326"},
            MockInputDefinition(dataType=WPS_BOUNDINGBOX_DATA),
            BoundingBoxDataInput(
                [1, 2, 3, 4],
                crs="urn:ogc:def:crs:EPSG::4326",
                dimensions=2,
            )
        ),
        (
            {"href": "https://test.com/some-file.json", "mediaType": ContentType.APP_JSON},
            MockInputDefinition(dataType=WPS_COMPLEX_DATA),
            ComplexDataInput(
                "https://test.com/some-file.json",
                mimeType=ContentType.APP_JSON,
                encoding=None,
                schema=None,
            ),
        ),
        (
            {
                "href": "https://test.com/some-img.tif",
                "mediaType": ContentType.IMAGE_GEOTIFF,
                "encoding": ContentEncoding.BASE64,
            },
            MockInputDefinition(dataType=WPS_COMPLEX_DATA),
            ComplexDataInput(
                "https://test.com/some-img.tif",
                mimeType=ContentType.IMAGE_GEOTIFF,
                encoding=ContentEncoding.BASE64,
                schema=None,
            ),
        ),
    ]
)
def test_parse_wps_inputs(input_data, input_definition, expect_input):
    # type: (JSON, MockInputDefinition, OWS_Input_Type) -> None
    input_def = cast(Input, input_definition)
    proc = cast(Process, MockProcess([input_def]))
    job = Job(task_id=uuid.uuid4())
    input_data.update({"id": input_def.identifier})
    job.inputs = [input_data]
    result_inputs = parse_wps_inputs(proc, job)
    if expect_input is None:
        assert result_inputs == []  # pylint: disable=C1803  # not check only if empty, we want to check the type also!
    else:
        result_input = result_inputs[0][1]
        if not isinstance(expect_input, str):
            assert isinstance(result_input, type(expect_input))
            fields = list(filter(
                lambda attr: not attr.startswith("__") and not callable(getattr(expect_input, attr)),
                dir(expect_input))
            )
            assert len(fields)
            for field in fields:
                expect_field = getattr(expect_input, field)
                result_field = getattr(result_input, field)
                assert expect_field == result_field, f"Field [{field}] did not match"
        else:
            assert result_input == expect_input


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_simple_literals():
    """
    Test parsing simple literal values from KVP.
    """
    params = {
        "stringInput": ["test value"],
        "intInput": ["42"],
        "floatInput": ["3.14"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 3
    assert result["inputs"]["stringInput"] == {"value": "test value"}
    assert result["inputs"]["intInput"] == {"value": 42}
    assert result["inputs"]["floatInput"] == {"value": 3.14}
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_by_reference():
    """
    Test parsing input by reference using ``href`` and ``type`` qualifiers.
    """
    params = {
        "fileInput[href]": ["http://example.com/file.txt"],
        "fileInput[type]": [ContentType.TEXT_PLAIN],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert "fileInput" in result["inputs"]
    assert result["inputs"]["fileInput"]["href"] == "http://example.com/file.txt"
    assert result["inputs"]["fileInput"]["type"] == ContentType.TEXT_PLAIN
    assert not response_params


@pytest.mark.kvp
@pytest.mark.parametrize(
    ["value", "expect"],
    [
        (["1,2,3,4,5"], [1, 2, 3, 4, 5]),
        (["1.23,3.45"], [1.23, 3.45]),
        (["1,2,3,4,5."], [1.0, 2.0, 3.0, 4.0, 5.0]),  # auto convert all if any is float
        (["%201,2%20"], [1, 2]),
        (["%20abc,def%20"], [" abc", "def "]),
    ]
)
def test_parse_kvp_inputs_outputs_array_encoding_preserved(value, expect):
    """
    Test parsing array values from KVP.
    """
    params = {"arrayInput": value}
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert "arrayInput" in result["inputs"]
    assert result["inputs"]["arrayInput"]["value"] == expect
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_bbox():
    """
    Test parsing bounding box from KVP.
    """
    params = {
        "area": ["5.8,47.2,15.1,55.1"],
        "area[crs]": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert "area" in result["inputs"]
    assert result["inputs"]["area"]["bbox"] == [5.8, 47.2, 15.1, 55.1]
    assert result["inputs"]["area"]["crs"] == "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_with_outputs():
    """
    Test parsing output specifications from KVP.
    """
    params = {
        "input1": ["value1"],
        "output1[include]": ["true"],
        "output2[include]": ["true"],
        "output2[mediaType]": [ContentType.APP_JSON],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert "outputs" in result
    assert len(result["inputs"]) == 1
    assert len(result["outputs"]) == 2

    assert "output1" in result["outputs"]
    assert "output2" in result["outputs"]
    assert "format" in result["outputs"]["output2"]
    assert result["outputs"]["output2"]["format"]["mediaType"] == ContentType.APP_JSON
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_url_encoded_json():
    """
    Test parsing URL-encoded JSON values from KVP.
    """
    json_value = '{"key1": "value1", "key2": 123}'
    params = {
        "complexInput": [urllib.parse.quote(json_value)],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert "complexInput" in result["inputs"]
    assert isinstance(result["inputs"]["complexInput"]["value"], dict)
    assert result["inputs"]["complexInput"]["value"]["key1"] == "value1"
    assert result["inputs"]["complexInput"]["value"]["key2"] == 123
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_reserved_params():
    """
    Test that reserved parameters are skipped during KVP parsing.
    """
    params = {
        "input1": ["value1"],
        "f": ["json"],
        "response": ["document"],
        "response[prefer]": ["respond-async"],
        "data": ["test"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 2
    assert "input1" in result["inputs"]
    assert "data" in result["inputs"]

    # Validate reserved parameters are in response_params
    assert "response" in response_params
    assert response_params["response"][None] == "document"
    assert response_params["response"]["prefer"] == "respond-async"
    assert "f" in response_params
    assert "prefer" not in response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_mixed_inputs_outputs():
    """
    Test parsing a mix of inputs and outputs.
    """
    params = {
        "stringInput": ["test"],
        "numberInput": ["42"],
        "fileInput[href]": ["http://example.com/file.txt"],
        "output1[include]": ["true"],
        "output2[include]": ["true"],
        "output2[mediaType]": [ContentType.IMAGE_GEOTIFF],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert "outputs" in result
    assert len(result["inputs"]) == 3
    assert len(result["outputs"]) == 2

    assert "stringInput" in result["inputs"]
    assert "numberInput" in result["inputs"]
    assert "fileInput" in result["inputs"]

    assert "output1" in result["outputs"]
    assert "output2" in result["outputs"]
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_binary_with_value_qualifier():
    """
    Test parsing base64-encoded binary input with ``value`` qualifier.

    Format qualifiers for inputs should be at top level, not nested under ``format``.
    """
    binary_data = b"Hello, World!"
    encoded_data = base64.b64encode(binary_data).decode("ascii")

    params = {
        "binaryInput[value]": [encoded_data],
        "binaryInput[mediaType]": [ContentType.TEXT_PLAIN],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert "binaryInput" in result["inputs"]
    assert result["inputs"]["binaryInput"]["value"] == encoded_data
    assert "format" not in result["inputs"]["binaryInput"]
    assert result["inputs"]["binaryInput"]["mediaType"] == ContentType.TEXT_PLAIN
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_schema_qualifier():
    """
    Test parsing ``schema`` qualifier for inputs and outputs.

    For inputs, format qualifiers should be at top level.
    For outputs, format qualifiers should be nested under ``format``.
    """
    schema_url = "http://example.com/schema.json"
    schema_obj = '{"type": "object", "properties": {"name": {"type": "string"}}}'

    params = {
        "input1[schema]": [schema_url],
        "output1[include]": ["true"],
        "output1[schema]": [urllib.parse.quote(schema_obj)],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert "outputs" in result
    assert "input1" in result["inputs"]
    assert "format" not in result["inputs"]["input1"]
    assert result["inputs"]["input1"]["schema"] == schema_url
    assert "output1" in result["outputs"]
    assert "format" in result["outputs"]["output1"]
    assert isinstance(result["outputs"]["output1"]["format"]["schema"], dict)
    assert result["outputs"]["output1"]["format"]["schema"]["type"] == "object"
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_encoding_qualifier():
    """
    Test parsing ``encoding`` qualifier for outputs.
    """
    params = {
        "input1": ["test"],
        "output1[include]": ["true"],
        "output1[mediaType]": [ContentType.APP_JSON],
        "output1[encoding]": ["gzip"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "outputs" in result
    assert len(result["outputs"]) == 1
    assert "output1" in result["outputs"]
    assert result["outputs"]["output1"]["format"]["mediaType"] == ContentType.APP_JSON
    assert result["outputs"]["output1"]["format"]["encoding"] == "gzip"
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_response_format_alias():
    """
    Test that ``response[format]`` is accepted as alias for ``response[f]``.
    """
    params = {
        "input1": ["test"],
        "response[format]": [ContentType.APP_JSON],
        "response[prefer]": ["respond-async"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    response_dict = response_params.get("response", {})
    assert "format" in response_dict or "f" in response_dict
    assert response_dict.get("prefer") == "respond-async"


@pytest.mark.kvp
@pytest.mark.parametrize(
    ["prefer_value", "expected_contains"],
    [
        ("respond-async;return=minimal", ["return=minimal"]),
        ("wait=30;handling=lenient", ["wait=30", "handling=lenient"]),
        ("respond-async;return=representation;wait=10", ["return=representation", "wait=10"]),
    ]
)
def test_parse_kvp_inputs_outputs_response_prefer_with_nested_equals(prefer_value, expected_contains):
    """
    Test that ``response[prefer]`` with nested ``=`` characters is parsed correctly.

    The ``Prefer`` header can contain values like ``"respond-async;return=minimal"`` where
    the nested ``=`` should be preserved as part of the value, not treated as a KVP separator.
    """
    params = {
        "input1": ["test value"],
        "response[prefer]": [prefer_value],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert "input1" in result["inputs"]
    assert result["inputs"]["input1"]["value"] == "test value"

    response_dict = response_params.get("response", {})
    assert "prefer" in response_dict
    assert response_dict["prefer"] == prefer_value
    for expected in expected_contains:
        assert expected in response_dict["prefer"]


@pytest.mark.kvp
@pytest.mark.parametrize(
    ["schema", "expect"],
    [
        (
            "https://example.com/test.json",
            "https://example.com/test.json",
        ),
        (
            """{"$ref": "https://example.com/test.json"}""",
            {"$ref": "https://example.com/test.json"},
        ),
        (
            """
            {
                "type": "object",
                "properties": {"test": {"type": "string"}}
            }
            """,
            {
                "type": "object",
                "properties": {"test": {"type": "string"}}
            },
        ),
        (
            urllib.parse.quote(json.dumps({
                "type": "object",
                "properties": {"test": {"type": "string"}}
            })),
            {
                "type": "object",
                "properties": {"test": {"type": "string"}}
            },
        )
    ]
)
def test_parse_kvp_inputs_outputs_qualified_value_with_schema(schema, expect):
    """
    Test parsing input with ``value`` qualifier and format qualifiers.

    Validates that ``input[value]=data&input[mediaType]=text/plain`` produces
    an input with both value and format qualifiers at top level (not under ``format``).
    """
    value = """{"test": "data"}"""
    params = {
        "my_input[value]": [value],
        "my_input[schema]": [schema],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert "my_input" in result["inputs"]
    input_data = result["inputs"]["my_input"]
    assert input_data["value"] == value
    for qual in ["format", "mediaType", "encoding"]:
        assert qual not in input_data
    assert input_data["schema"] == expect
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_qualified_value_with_format():
    """
    Test parsing input with ``value`` qualifier and format qualifiers.

    Validates that ``input[value]=data&input[mediaType]=text/plain`` produces
    an input with both value and format qualifiers at top level (not under ``format``).
    """
    params = {
        "my_input[value]": ["test data"],
        "my_input[mediaType]": [ContentType.TEXT_PLAIN],
        "my_input[encoding]": [ContentEncoding.BASE64],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1

    assert "my_input" in result["inputs"]
    input_data = result["inputs"]["my_input"]
    assert input_data["value"] == "test data"
    assert "format" not in input_data
    assert input_data["mediaType"] == ContentType.TEXT_PLAIN
    assert input_data["encoding"] == ContentEncoding.BASE64
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_qualified_param_unknown_ignored():
    params = {
        "input1": "test",
        "input1[unknown]": "whatever",
    }
    result, response_params = parse_kvp_inputs_outputs(params)
    assert result == {
        "inputs": {
            "input1": {"value": "test"}
        }
    }
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_output_with_include_and_format():
    """
    Test that outputs require ``include=true`` and get format structure.

    Validates that ``output[include]=true&output[mediaType]=...`` produces
    an output with format but no value.
    """
    params = {
        "result[include]": ["true"],
        "result[mediaType]": [ContentType.APP_JSON],
        "result[encoding]": ["gzip"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "outputs" in result
    assert len(result["outputs"]) == 1

    assert "result" in result["outputs"]
    output_data = result["outputs"]["result"]
    # Outputs should NOT have value
    assert "value" not in output_data
    assert "format" in output_data
    assert output_data["format"]["mediaType"] == ContentType.APP_JSON
    assert output_data["format"]["encoding"] == "gzip"
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_include_determines_classification():
    """
    Test that ``include`` qualifier determines input vs output classification.

    Parameters with ``include=true`` become outputs, others become inputs.
    For inputs, format qualifiers are at top level.
    For outputs, format qualifiers are nested under ``format``.
    """
    params = {
        # Input - has format but no include
        "data[mediaType]": ["text/csv"],
        # Output - has include=true
        "result[include]": ["true"],
        "result[mediaType]": [ContentType.APP_JSON],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    # data should be input (no include) - format at top level
    assert "inputs" in result
    assert "data" in result["inputs"]
    data_input = result["inputs"]["data"]
    assert "format" not in data_input
    assert data_input["mediaType"] == "text/csv"

    # result should be output (has include=true) - format nested under 'format'
    assert "outputs" in result
    assert "result" in result["outputs"]
    result_output = result["outputs"]["result"]
    assert "format" in result_output
    assert result_output["format"]["mediaType"] == ContentType.APP_JSON
    assert "value" not in result_output
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_with_profile():
    """
    Test parsing input and output with profile qualifier.

    For inputs, format qualifiers should be at top level.
    For outputs, format qualifiers should be nested under ``format``.
    """
    params = {
        "features[value]": ['{"type": "FeatureCollection"}'],
        "features[mediaType]": [ContentType.APP_GEOJSON],
        "features[profile]": ["http://www.opengis.net/def/format/ogcapi-processes/0/geojson-geometry"],
        "output[include]": ["true"],
        "output[mediaType]": [ContentType.APP_JSON],
        "output[profile]": ["http://www.opengis.net/def/format/ogcapi-processes/0/stac-collection"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    # Check input with profile - format qualifiers at top level
    assert "inputs" in result
    assert "features" in result["inputs"]
    features_input = result["inputs"]["features"]
    assert "format" not in features_input
    assert features_input["mediaType"] == ContentType.APP_GEOJSON
    assert features_input["profile"] == "http://www.opengis.net/def/format/ogcapi-processes/0/geojson-geometry"

    # Check output with profile - format qualifiers nested under 'format'
    assert "outputs" in result
    assert "output" in result["outputs"]
    output_result = result["outputs"]["output"]
    assert "format" in output_result
    assert output_result["format"]["mediaType"] == ContentType.APP_JSON
    assert output_result["format"]["profile"] == "http://www.opengis.net/def/format/ogcapi-processes/0/stac-collection"
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_response_profile():
    """
    Test parsing ``response[profile]`` parameter.
    """
    params = {
        "input1": ["value1"],
        "response[profile]": ["http://www.opengis.net/def/format/ogcapi-processes/0/stac"],
        "response[f]": [ContentType.APP_JSON],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1

    # Check response parameters from nested dict
    response_dict = response_params.get("response", {})
    assert "profile" in response_dict
    assert response_dict["profile"] == "http://www.opengis.net/def/format/ogcapi-processes/0/stac"
    assert "f" in response_dict
    assert response_dict["f"] == ContentType.APP_JSON


@pytest.mark.kvp
@pytest.mark.parametrize(
    "format_value",
    [
        "json",
        "xml",
        ContentType.APP_JSON,
    ]
)
def test_parse_kvp_inputs_outputs_response_format_short_names(format_value):
    """
    Test parsing ``response[f]`` with short format names.
    """
    params = {
        "input1": ["value1"],
        "response[f]": [format_value],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    response_dict = response_params.get("response", {})
    assert "f" in response_dict
    assert response_dict["f"] == format_value


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_standalone_profile():
    """
    Test parsing standalone ``profile`` parameter (without response qualifier).
    """
    params = {
        "input1": ["value1"],
        "profile": ["ogc"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert "profile" in response_params
    assert response_params["profile"] == "ogc"


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_response_collection():
    """
    Test parsing ``response=collection`` parameter.
    """
    params = {
        "input1": ["value1"],
        "response": ["collection"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert "response" in response_params
    response_dict = response_params["response"]
    assert isinstance(response_dict, dict)
    assert None in response_dict
    assert response_dict[None] == "collection"


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_both_f_and_format():
    """
    Test that ``response[f]`` takes precedence over ``response[format]`` when both are provided.
    """
    params = {
        "input1": ["value1"],
        "response[f]": ["json"],
        "response[format]": ["xml"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    response_dict = response_params.get("response", {})
    assert "f" in response_dict
    assert "format" in response_dict
    assert response_dict["f"] == "json"
    assert response_dict["format"] == "xml"


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_profile_vs_response_profile():
    """
    Test that standalone ``profile`` parameter is parsed.
    """
    params = {
        "input1": ["value1"],
        "profile": ["ogc"],
        "response[f]": ["json"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert "profile" in response_params
    assert response_params["profile"] == "ogc"
    response_dict = response_params.get("response", {})
    assert "f" in response_dict
    assert response_dict["f"] == "json"


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_case_sensitivity():
    """
    Test that parameter names are case-sensitive (not lowercased for input/output IDs).
    """
    params = {
        "MyInput": ["value1"],
        "myInput": ["value2"],
        "MYINPUT": ["value3"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 3
    assert "MyInput" in result["inputs"]
    assert "myInput" in result["inputs"]
    assert "MYINPUT" in result["inputs"]
    assert not response_params


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_reserved_params_case_insensitive():
    """
    Test that reserved parameters (f, response, prefer, profile) are case-insensitive.
    """
    params = {
        "input1": ["value1"],
        "F": ["json"],
        "RESPONSE[prefer]": ["respond-async"],
        "PROFILE": ["ogc"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1

    # Validate reserved parameters are case-insensitive
    assert "f" in response_params
    assert "response" in response_params
    assert "profile" in response_params


@pytest.mark.kvp
@pytest.mark.parametrize(
    "invalid_params",
    [
        {"input1": "[value1,value2"},   # missing ]
        {"input1": "{value1,1,2,3,4"},  # missing }
        {"input1": "value1,value2]"},   # missing {
        {"input1": "value1,1,2,3,4}"},  # missing [
        {"input1": "{value1,value2}"},  # not JSON object
        {
            "input1": "1,2,3,a",        # not bbox coordinates
            "input1[crs]": "OGC:CRS84",
        },
        {
            "input1": "1,2,3",          # missing bbox coordinate
            "input1[crs]": "OGC:CRS84",
        },
        {
            "input1": "[1,2,3,4]",      # invalid array coordinates
            "input1[crs]": "OGC:CRS84",
        },
        {
            "input1[value]": """{"test":"value"}""",
            "input1[schema]": """{"invalid-json"}""",
        },
        {
            "input1[value]": """{"test":"value"}""",
            "input1[schema]": "[1,2,3,4]",  # valid JSON, but not object
        }
    ]
)
def test_parse_kvp_inputs_outputs_invalid_raised(invalid_params):
    with pytest.raises(ValueError):
        parse_kvp_inputs_outputs(invalid_params)


@pytest.mark.kvp
def test_submit_job_from_kvp_invalid():
    """
    Raised :class:`ValueError` should be caught and result in :class:`pyramid.httpexceptions.HTTPBadRequest`.

    .. seealso::
        :func:`test_parse_kvp_inputs_outputs_invalid_raised`
    """
    req = MockedRequest()
    req.params = {"input1": "{value1,value2}"}
    with pytest.raises(HTTPBadRequest) as exc:
        submit_job_from_kvp(req, None)  # type: ignore
    body = exc.value.json
    assert body["type"] == "InvalidParameterValue"
    assert body["title"] == "Invalid KVP parameters"


@pytest.mark.kvp
def test_submit_job_from_kvp():
    """
    Tests all variants of :term:`KVP` inputs/outputs/response parameters and qualifiers into expected POST request.
    """
    req = MockedRequest()
    req.params = {
        # Simple literal input
        "input1": "value1",
        # Numeric literal input
        "input2": "42",
        # Complex input with qualifiers
        "input3[href]": "http://example.com/data.json",
        "input3[type]": "application/json",
        # Output with qualifiers
        "output1[include]": "true",
        "output1[mediaType]": "application/json",
        # Response parameters
        "response": "collection",
        "response[f]": "json",
        "response[format]": "xml",
        "response[prefer]": "respond-async",
    }
    # Headers that should be overridden by KVP parameters
    req.headers = {
        "Accept": "application/xml",
        "Prefer": "wait=30",
    }
    with mock.patch("weaver.processes.execution.submit_job", return_value=None):
        submit_job_from_kvp(req, None)  # type: ignore
    data = cast(bytes, req.body).decode("utf-8")
    body = json.loads(data)

    # Check inputs
    assert "inputs" in body
    assert len(body["inputs"]) == 3
    assert "input1" in body["inputs"]
    assert body["inputs"]["input1"]["value"] == "value1"
    assert "input2" in body["inputs"]
    assert body["inputs"]["input2"]["value"] == 42
    assert "input3" in body["inputs"]
    assert body["inputs"]["input3"]["href"] == "http://example.com/data.json"
    assert body["inputs"]["input3"]["type"] == "application/json"

    # Check outputs
    assert "outputs" in body
    assert len(body["outputs"]) == 1
    assert "output1" in body["outputs"]
    assert "format" in body["outputs"]["output1"]
    assert body["outputs"]["output1"]["format"] == {"mediaType": "application/json"}

    # Check response parameter in body
    assert "response" in body
    assert body["response"] == "collection"

    # Validate headers (KVP overrides original headers)
    # response[f] takes precedence over response[format]
    assert ContentType.APP_JSON in req.headers["Accept"]
    assert req.headers["Prefer"] == "respond-async", "response[prefer] overrides original Prefer header"
    assert req.headers["Content-Type"] == ContentType.APP_JSON


@pytest.mark.kvp
def test_kvp_complex_profile_combinations():
    """
    Test async execution with ``profile`` and ``response[profile]`` handling.

    Profile parameters behaviour:
    - Async execution: ``profile`` applies to Job Status response (immediate HTTP 201)
    - Async execution: ``response[profile]`` applies to Job Result response (final results)
    - Input/output profiles are independent of execution mode
    """
    req = MockedRequest()
    req.params = {
        # Input with profile qualifier
        "input[href]": "http://example.com/data.json",
        "input[type]": "application/geo+json",
        "input[profile]": "http://www.opengis.net/def/format/ogcapi-processes/0/geojson-geometry",
        # Output with profile qualifier
        "output[include]": "true",
        "output[mediaType]": "application/geo+json",
        "output[profile]": "http://www.opengis.net/def/format/ogcapi-processes/0/geojson-feature-collection",
        # Response parameters
        "response": "collection",
        "response[prefer]": "respond-async",
        "response[f]": "json",
        # Job Status profile (immediate response)
        "profile": "ogc",
        # Job Result profile (final results)
        "response[profile]": "http://www.opengis.net/def/format/ogcapi-processes/0/stac",
    }
    req.headers = {}
    with mock.patch("weaver.processes.execution.submit_job", return_value=None):
        submit_job_from_kvp(req, None)  # type: ignore
    data = cast(bytes, req.body).decode("utf-8")
    body = json.loads(data)

    # Validate input profile (content profile for the input data)
    assert "inputs" in body
    assert "input" in body["inputs"]
    input_obj = body["inputs"]["input"]
    assert input_obj["profile"] == "http://www.opengis.net/def/format/ogcapi-processes/0/geojson-geometry"

    # Validate output profile (content profile for the output data)
    assert "outputs" in body
    assert "output" in body["outputs"]
    output_obj = body["outputs"]["output"]
    assert "format" in output_obj
    expected_profile = "http://www.opengis.net/def/format/ogcapi-processes/0/geojson-feature-collection"
    assert output_obj["format"]["profile"] == expected_profile

    # Validate response=collection in body
    assert "response" in body
    assert body["response"] == "collection"

    # Validate response[profile] in body (applies to final Job Result)
    assert "profile" in body
    assert body["profile"] == "http://www.opengis.net/def/format/ogcapi-processes/0/stac"

    # Validate Accept-Profile header (applies to immediate Job Status)
    assert "Accept-Profile" in req.headers
    assert req.headers["Accept-Profile"] == "ogc"

    # Validate Accept header from response[f]
    assert "Accept" in req.headers
    assert ContentType.APP_JSON in req.headers["Accept"]

    # Validate Prefer header
    assert "Prefer" in req.headers
    assert req.headers["Prefer"] == "respond-async"


@pytest.mark.parametrize(
    ["prefer_mode", "top_profile", "response_profile", "expected_header_profile", "expected_body_profile"],
    [
        # Synchronous execution: both profile and response[profile] are equivalent, apply to Accept-Profile header
        ("wait", "ogc", None, "ogc", None),
        ("wait", None, "stac", "stac", None),
        ("wait", "ogc", "stac", "stac", None),  # response[profile] takes precedence in sync
        # Asynchronous execution: profile -> Accept-Profile, response[profile] -> body
        ("respond-async", "ogc", None, "ogc", None),
        ("respond-async", None, "stac", None, "stac"),
        ("respond-async", "ogc", "stac", "ogc", "stac"),  # both used independently
    ]
)
def test_kvp_profile_resolution_sync_async(
    prefer_mode,
    top_profile,
    response_profile,
    expected_header_profile,
    expected_body_profile
):
    """
    Validate profile and response[profile] resolution based on execution mode (sync vs async).

    Per OGC API - Processes spec and [#kvpProfile] warning in docs:
    - Synchronous (Prefer: wait): profile and response[profile] are equivalent, both apply to Accept-Profile header
    - Asynchronous (Prefer: respond-async):
      - profile applies to Job Status response (Accept-Profile header for immediate 201)
      - response[profile] applies to Job Result response (stored in body for final results)
    """
    req = MockedRequest()
    req.params = {"prefer": prefer_mode}
    if top_profile:
        req.params["profile"] = top_profile
    if response_profile:
        req.params["response[profile]"] = response_profile
    req.headers = {}

    with mock.patch("weaver.processes.execution.submit_job", return_value=None):
        submit_job_from_kvp(req, None)  # type: ignore

    data = cast(bytes, req.body).decode("utf-8")
    body = json.loads(data)

    if expected_header_profile:
        assert "Accept-Profile" in req.headers, (
            f"Expected Accept-Profile header for mode={prefer_mode}, "
            f"profile={top_profile}, response[profile]={response_profile}"
        )
        assert req.headers["Accept-Profile"] == expected_header_profile
    else:
        assert "Accept-Profile" not in req.headers, (
            f"Unexpected Accept-Profile header for mode={prefer_mode}, "
            f"profile={top_profile}, response[profile]={response_profile}"
        )

    if expected_body_profile:
        assert "profile" in body, (
            f"Expected profile in body for mode={prefer_mode}, "
            f"profile={top_profile}, response[profile]={response_profile}"
        )
        assert body["profile"] == expected_body_profile
    else:
        assert "profile" not in body, (
            f"Unexpected profile in body for mode={prefer_mode}, "
            f"profile={top_profile}, response[profile]={response_profile}"
        )


@pytest.mark.parametrize(
    ["param_name", "qualifier_name", "expected_profile"],
    [
        # Case-insensitive reserved parameters
        ("profile", None, "test-profile"),
        ("Profile", None, "test-profile"),
        ("PROFILE", None, "test-profile"),
        # Case-insensitive qualifiers
        ("response[profile]", None, "test-profile"),
        ("response[Profile]", None, "test-profile"),
        ("response[PROFILE]", None, "test-profile"),
        ("Response[profile]", None, "test-profile"),
        ("RESPONSE[PROFILE]", None, "test-profile"),
    ]
)
def test_kvp_profile_case_insensitive(param_name, qualifier_name, expected_profile):
    """
    Validate case-insensitive handling of profile parameters.

    Per processes.rst documentation:
    - Reserved parameters (profile, response, etc.) are case-insensitive
    - Qualifiers ([profile], [f], etc.) are case-insensitive
    """
    req = MockedRequest()
    req.params = {
        "prefer": "wait",
        param_name: expected_profile,
    }
    req.headers = {}

    with mock.patch("weaver.processes.execution.submit_job", return_value=None):
        submit_job_from_kvp(req, None)  # type: ignore

    assert "Accept-Profile" in req.headers
    assert req.headers["Accept-Profile"] == expected_profile


@pytest.mark.parametrize(
    ["kvp_params", "expected_body", "expected_headers"],
    [
        # Simple input parameter
        (
            {"input1": "value1"},
            {"inputs": {"input1": {"value": "value1"}}},
            {},
        ),
        # Input with href
        (
            {"input1[href]": "http://example.com/data.json"},
            {"inputs": {"input1": {"href": "http://example.com/data.json"}}},
            {},
        ),
        # Response parameter goes to body
        (
            {"response": "document"},
            {"response": "document"},
            {},
        ),
        # Format parameter (f) goes to Accept header
        (
            {"f": "json"},
            {},
            {"Accept": ContentType.APP_JSON},
        ),
        # Prefer parameter goes to Prefer header
        (
            {"prefer": "respond-async"},
            {},
            {"Prefer": "respond-async"},
        ),
        # Profile parameter goes to Accept-Profile header (sync mode with explicit wait)
        (
            {"prefer": "wait", "profile": "ogc"},
            {},
            {"Prefer": "wait", "Accept-Profile": "ogc"},
        ),
        # Multiple inputs
        (
            {"input1": "value1", "input2": "value2"},
            {"inputs": {"input1": {"value": "value1"}, "input2": {"value": "value2"}}},
            {},
        ),
        # Input with format qualifiers
        (
            {
                "input1[href]": "http://example.com/data.json",
                "input1[mediaType]": "application/geo+json",
                "input1[schema]": "http://example.com/schema.json",
            },
            {
                "inputs": {
                    "input1": {
                        "href": "http://example.com/data.json",
                        "mediaType": "application/geo+json",
                        "schema": "http://example.com/schema.json",
                    }
                }
            },
            {},
        ),
        # Output with format qualifiers
        (
            {
                "output1[include]": "true",
                "output1[mediaType]": "application/json",
                "output1[profile]": "http://www.opengis.net/def/format/ogcapi-processes/0/geojson",
            },
            {
                "outputs": {
                    "output1": {
                        "format": {
                            "mediaType": "application/json",
                            "profile": "http://www.opengis.net/def/format/ogcapi-processes/0/geojson",
                        }
                    }
                }
            },
            {},
        ),
        # Response with qualifiers
        (
            {"response[f]": "json", "response[prefer]": "wait"},
            {},
            {"Accept": ContentType.APP_JSON, "Prefer": "wait"},
        ),
    ]
)
def test_kvp_parameter_resolution(kvp_params, expected_body, expected_headers):
    """
    Validate KVP parameters are correctly resolved to JSON body, headers, and queries.

    Tests the conversion of KVP query parameters to their corresponding request elements:
    - Input/output parameters -> JSON body
    - Format (f), prefer, profile -> HTTP headers
    - Response parameter -> JSON body
    """
    req = MockedRequest()
    req.params = kvp_params
    req.headers = {}

    with mock.patch("weaver.processes.execution.submit_job", return_value=None):
        submit_job_from_kvp(req, None)  # type: ignore

    data = cast(bytes, req.body).decode("utf-8")
    body = json.loads(data)

    for key, value in expected_body.items():
        assert key in body, f"Expected '{key}' in body"
        if isinstance(value, dict) and key in ("inputs", "outputs"):
            # Handle mapping form: {"inputs": {"id": {...}}}
            assert isinstance(body[key], dict), f"Expected '{key}' to be a dict"
            assert len(body[key]) == len(value), f"Expected {len(value)} items in '{key}', got {len(body[key])}"
            for item_id, item_value in value.items():
                assert item_id in body[key], f"Expected '{item_id}' in '{key}'"
                for k, v in item_value.items():
                    assert body[key][item_id].get(k) == v, (
                        f"Expected '{k}' to be '{v}' in '{key}[{item_id}]', got '{body[key][item_id].get(k)}'"
                    )
        else:
            assert body[key] == value, f"Expected '{key}' to be '{value}', got '{body[key]}'"

    for header, value in expected_headers.items():
        assert header in req.headers, f"Expected '{header}' in headers"
        if header == "Accept":
            assert value in req.headers[header], f"Expected '{value}' in '{header}' header"
        else:
            assert req.headers[header] == value, f"Expected '{header}' to be '{value}', got '{req.headers[header]}'"


@pytest.mark.parametrize(
    ["kvp_params", "initial_headers", "expected_header", "expected_value"],
    [
        # KVP f overrides Accept header
        (
            {"f": "json"},
            {"Accept": "text/html"},
            "Accept",
            ContentType.APP_JSON,
        ),
        # KVP prefer overrides Prefer header
        (
            {"prefer": "respond-async"},
            {"Prefer": "wait"},
            "Prefer",
            "respond-async",
        ),
        # KVP profile overrides Accept-Profile header
        (
            {"prefer": "wait", "profile": "ogc"},
            {"Accept-Profile": "stac"},
            "Accept-Profile",
            "ogc",
        ),
        # KVP response[f] overrides Accept header
        (
            {"response[f]": "json"},
            {"Accept": "text/html"},
            "Accept",
            ContentType.APP_JSON,
        ),
        # KVP response[prefer] overrides Prefer header
        (
            {"response[prefer]": "wait"},
            {"Prefer": "respond-async"},
            "Prefer",
            "wait",
        ),
    ]
)
def test_kvp_overrides_headers(kvp_params, initial_headers, expected_header, expected_value):
    """
    Validate that KVP parameters override existing headers.

    Per submit_job_from_kvp documentation:
    Any time a KVP parameter is detected and matches an existing header,
    it will override that header and takes precedence to obtain the original
    intent of the user request.
    """
    req = MockedRequest()
    req.params = kvp_params
    req.headers = dict(initial_headers)

    with mock.patch("weaver.processes.execution.submit_job", return_value=None):
        submit_job_from_kvp(req, None)  # type: ignore

    assert expected_header in req.headers
    if expected_header == "Accept":
        assert expected_value in req.headers[expected_header]
    else:
        assert req.headers[expected_header] == expected_value


@pytest.mark.parametrize(
    ["f_param", "format_param", "expected_accept"],
    [
        # Only f parameter
        ("json", None, ContentType.APP_JSON),
        # Only format parameter
        (None, "json", ContentType.APP_JSON),
        # Both provided: f takes precedence
        ("json", "xml", ContentType.APP_JSON),
        ("xml", "json", "text/xml"),  # xml maps to text/xml, not application/xml
    ]
)
def test_kvp_format_precedence(f_param, format_param, expected_accept):
    """
    Validate that 'response[f]' parameter takes precedence over 'response[format]' parameter.

    When both are provided, 'f' is prioritized and 'format' is ignored.
    """
    req = MockedRequest()
    req.params = {}
    if f_param:
        req.params["response[f]"] = f_param
    if format_param:
        req.params["response[format]"] = format_param
    req.headers = {}

    with mock.patch("weaver.processes.execution.submit_job", return_value=None):
        submit_job_from_kvp(req, None)  # type: ignore

    assert "Accept" in req.headers
    assert expected_accept in req.headers["Accept"]


# FIXME: remove when collection output supported (https://github.com/crim-ca/weaver/issues/683)
def test_kvp_response_collection_validation():
    """
    Validate that 'response=collection' raises HTTPNotImplemented.

    The parameter is properly transferred to the body, but submit_job validates
    it and raises an error since this feature is not yet implemented.
    Related: https://github.com/crim-ca/weaver/issues/683
    """
    req = MockedRequest()
    req.params = {"response": "collection"}
    req.headers = {}

    # Mock the body validation to return a simple body
    with mock.patch("weaver.processes.execution.validate_job_json", return_value={"response": "collection"}):
        with mock.patch("weaver.processes.execution.get_wps_output_context"):
            with pytest.raises(HTTPNotImplemented) as exc_info:
                submit_job(req, None)  # type: ignore

    error_json = exc_info.value.json
    assert "response=collection" in error_json.get("detail", "").lower()
    assert "not yet supported" in error_json.get("detail", "").lower()


# FIXME: remove when collection output supported (https://github.com/crim-ca/weaver/issues/683)
def test_kvp_response_collection_in_submission():
    """
    Validate that response=collection from KVP is transferred to body and validated.

    Ensures the complete flow: KVP -> body conversion -> validation -> error
    """
    req = MockedRequest()
    req.params = {
        "response": "collection",
        "input1": "test-value",
    }
    req.headers = {}

    # The KVP submission should convert params to body, then submit_job should validate
    with mock.patch("weaver.processes.execution.validate_job_json") as mock_validate_json:
        with mock.patch("weaver.processes.execution.get_wps_output_context"):
            # Capture what body is generated
            def capture_body(request):
                data = cast("bytes", request.body).decode("utf-8")
                return json.loads(data)

            mock_validate_json.side_effect = capture_body

            with pytest.raises(HTTPNotImplemented) as exc_info:
                submit_job_from_kvp(req, None)  # type: ignore

    error_json = exc_info.value.json
    assert "response=collection" in error_json.get("detail", "").lower()
