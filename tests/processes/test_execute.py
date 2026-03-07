"""
Unit tests for utility methods of :mod:`weaver.processes.execute`.

For more in-depth execution tests, see ``tests.functional``.
"""
import base64
import dataclasses
import urllib.parse
import uuid
from typing import TYPE_CHECKING, List, cast

import mock
import pytest
from owslib.wps import BoundingBoxDataInput, ComplexDataInput, Input, Process

from weaver.datatype import Job
from weaver.formats import ContentEncoding, ContentType
from weaver.processes.constants import WPS_BOUNDINGBOX_DATA, WPS_COMPLEX_DATA, WPS_LITERAL, WPS_CategoryType
from weaver.processes.execution import parse_kvp_inputs_outputs, parse_wps_inputs

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
    inputs = {inp["id"]: inp["value"] for inp in result["inputs"]}
    assert inputs["stringInput"] == "test value"
    assert inputs["intInput"] == 42
    assert inputs["floatInput"] == 3.14
    assert response_params == {}


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
    assert result["inputs"][0]["id"] == "fileInput"
    assert result["inputs"][0]["href"] == "http://example.com/file.txt"
    assert result["inputs"][0]["type"] == ContentType.TEXT_PLAIN


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_array():
    """
    Test parsing array values from KVP.
    """
    params = {
        "arrayInput": ["1,2,3,4,5"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert result["inputs"][0]["id"] == "arrayInput"
    assert result["inputs"][0]["value"] == [1.0, 2.0, 3.0, 4.0, 5.0]


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_bbox():
    """
    Test parsing bounding box from KVP.
    """
    params = {
        "bbox": ["5.8,47.2,15.1,55.1"],
        "bbox[crs]": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert result["inputs"][0]["id"] == "bbox"
    assert "bbox" in result["inputs"][0]
    assert result["inputs"][0]["bbox"] == [5.8, 47.2, 15.1, 55.1]
    assert result["inputs"][0]["crs"] == "http://www.opengis.net/def/crs/OGC/1.3/CRS84"


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

    outputs = {out["id"]: out for out in result["outputs"]}
    assert "output1" in outputs
    assert "output2" in outputs
    assert "format" in outputs["output2"]
    assert outputs["output2"]["format"]["mediaType"] == ContentType.APP_JSON


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
    assert result["inputs"][0]["id"] == "complexInput"
    assert isinstance(result["inputs"][0]["value"], dict)
    assert result["inputs"][0]["value"]["key1"] == "value1"
    assert result["inputs"][0]["value"]["key2"] == 123


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_reserved_params():
    """
    Test that reserved parameters are skipped during KVP parsing.
    """
    params = {
        "input1": ["value1"],
        "f": ["json"],
        "response": ["document"],
        "prefer": ["respond-async"],
        "tags": ["test"],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1
    assert result["inputs"][0]["id"] == "input1"


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_mixed_inputs_outputs():
    """Test parsing a mix of inputs and outputs."""
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

    input_ids = {inp["id"] for inp in result["inputs"]}
    assert "stringInput" in input_ids
    assert "numberInput" in input_ids
    assert "fileInput" in input_ids

    output_ids = {out["id"] for out in result["outputs"]}
    assert "output1" in output_ids
    assert "output2" in output_ids


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
    assert result["inputs"][0]["id"] == "binaryInput"
    assert result["inputs"][0]["value"] == encoded_data
    assert "format" not in result["inputs"][0]
    assert result["inputs"][0]["mediaType"] == ContentType.TEXT_PLAIN


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
    assert "format" not in result["inputs"][0]
    assert result["inputs"][0]["schema"] == schema_url
    assert "format" in result["outputs"][0]
    assert isinstance(result["outputs"][0]["format"]["schema"], dict)
    assert result["outputs"][0]["format"]["schema"]["type"] == "object"


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
    assert result["outputs"][0]["format"]["mediaType"] == ContentType.APP_JSON
    assert result["outputs"][0]["format"]["encoding"] == "gzip"


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
    assert "format" in response_params or "f" in response_params
    assert response_params["prefer"] == "respond-async"


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
    assert result["inputs"][0]["id"] == "input1"
    assert result["inputs"][0]["value"] == "test value"

    assert "prefer" in response_params
    assert response_params["prefer"] == prefer_value
    for expected in expected_contains:
        assert expected in response_params["prefer"]


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

    input_data = result["inputs"][0]
    assert input_data["id"] == "my_input"
    assert input_data["value"] == "test data"
    assert "format" not in input_data
    assert input_data["mediaType"] == ContentType.TEXT_PLAIN
    assert input_data["encoding"] == ContentEncoding.BASE64


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

    output_data = result["outputs"][0]
    assert output_data["id"] == "result"
    # Outputs should NOT have value
    assert "value" not in output_data
    assert "format" in output_data
    assert output_data["format"]["mediaType"] == ContentType.APP_JSON
    assert output_data["format"]["encoding"] == "gzip"


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_include_determines_classification():
    """
    Test that ``include`` qualifier determines input vs output classification.

    Parameters with ``include=true`` become outputs, others become inputs.
    For inputs, format qualifiers are at top level.
    For outputs, format qualifiers are nested under 'format'.
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
    assert any(i["id"] == "data" for i in result["inputs"])
    data_input = next(i for i in result["inputs"] if i["id"] == "data")
    assert "format" not in data_input
    assert data_input["mediaType"] == "text/csv"

    # result should be output (has include=true) - format nested under 'format'
    assert "outputs" in result
    assert any(o["id"] == "result" for o in result["outputs"])
    result_output = next(o for o in result["outputs"] if o["id"] == "result")
    assert "format" in result_output
    assert result_output["format"]["mediaType"] == ContentType.APP_JSON
    assert "value" not in result_output


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_with_profile():
    """
    Test parsing input and output with profile qualifier.

    For inputs, format qualifiers should be at top level.
    For outputs, format qualifiers should be nested under 'format'.
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
    features_input = next((i for i in result["inputs"] if i["id"] == "features"), None)
    assert features_input is not None
    assert "format" not in features_input
    assert features_input["mediaType"] == ContentType.APP_GEOJSON
    assert features_input["profile"] == "http://www.opengis.net/def/format/ogcapi-processes/0/geojson-geometry"

    # Check output with profile - format qualifiers nested under 'format'
    assert "outputs" in result
    output_result = next((o for o in result["outputs"] if o["id"] == "output"), None)
    assert output_result is not None
    assert "format" in output_result
    assert output_result["format"]["mediaType"] == ContentType.APP_JSON
    assert output_result["format"]["profile"] == "http://www.opengis.net/def/format/ogcapi-processes/0/stac-collection"


@pytest.mark.kvp
def test_parse_kvp_inputs_outputs_response_profile():
    """
    Test parsing response[profile] parameter.
    """
    params = {
        "input1": ["value1"],
        "response[profile]": ["http://www.opengis.net/def/format/ogcapi-processes/0/stac"],
        "response[f]": [ContentType.APP_JSON],
    }
    result, response_params = parse_kvp_inputs_outputs(params)

    assert "inputs" in result
    assert len(result["inputs"]) == 1

    # Check response parameters
    assert "profile" in response_params
    assert response_params["profile"] == "http://www.opengis.net/def/format/ogcapi-processes/0/stac"
    assert "f" in response_params
    assert response_params["f"] == ContentType.APP_JSON


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
    assert "f" in response_params
    assert response_params["f"] == format_value

