"""
Unit test for :mod:`weaver.cli` utilities.
"""
import base64
import inspect
import json
import tempfile
from contextlib import ExitStack
from urllib.parse import quote

import mock
import pytest
import yaml

from tests.utils import run_command
from weaver.cli import OperationResult, WeaverClient, main as weaver_cli
from weaver.formats import ContentType


@pytest.mark.cli
def test_operation_result_repr():
    result = OperationResult(True, code=200, message="This is a test.", body={"field": "data", "list": [1, 2, 3]})
    assert repr(result) == inspect.cleandoc("""
        OperationResult(success=True, code=200, message="This is a test.")
        {
          "field": "data",
          "list": [
            1,
            2,
            3
          ]
        }
    """)


@pytest.mark.cli
def test_cli_url_required_in_client_or_param():
    with pytest.raises(ValueError):
        WeaverClient().execute("")
    try:
        with mock.patch("weaver.cli.WeaverClient._parse_inputs", return_value=OperationResult()):
            WeaverClient(url="http://fake.domain.com").execute("")
            WeaverClient().execute("", url="http://fake.domain.com")
    except ValueError:
        pytest.fail()


@pytest.mark.cli
def test_parse_inputs_from_file():
    inputs = []
    mock_result = OperationResult(False, code=500)

    def parsed_inputs(_inputs, *_, **__):
        inputs.append(_inputs)
        return mock_result

    with mock.patch("weaver.cli.WeaverClient._update_files", side_effect=parsed_inputs):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as input_json:
            json.dump({"inputs": {"input1": "data"}}, input_json)
            input_json.flush()
            input_json.seek(0)
            result = WeaverClient().execute("fake_process", input_json.name, url="http://fake.domain.com")
    assert result is mock_result
    assert len(inputs) == 1
    assert inputs[0] == {"input1": {"value": "data"}}


@pytest.mark.cli
def test_parse_inputs_with_media_type():
    inputs = []
    mock_result = OperationResult(True, code=500)

    def parsed_inputs(_inputs, *_, **__):
        inputs.append(_inputs)
        return mock_result

    # catch and ignore returned error since we generate it
    # voluntarily with following mock to stop processing
    def no_error_cli(*args):
        weaver_cli(*args)
        return 0

    with mock.patch("weaver.cli.WeaverClient._update_files", side_effect=parsed_inputs):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml") as input_yaml:
            yaml.safe_dump({"info": {"data": "yaml"}}, input_yaml)
            input_yaml.flush()
            input_yaml.seek(0)

            run_command([
                # weaver
                "execute",
                # different media-type than YAML on purpose to ensure parsing uses provided value, and not extension
                "-I", f"input:File={input_yaml.name}@mediaType={ContentType.APP_CWL}",
                "-p", "fake_process",
                "-u", "http://fake.domain.com",
                "-q",  # since CLI fails purposely, avoid logging errors which would be confusing if debugging logs
            ], entrypoint=no_error_cli)

    assert len(inputs) == 1
    assert inputs[0] == {
        "input": {
            "href": input_yaml.name,  # normally, local file would be uploaded to vault, but we skipped it with mock
            "format": {"mediaType": ContentType.APP_CWL}
        }
    }

    inputs.clear()
    schema_json = "http://schema.org/random.json"
    schema_xml = "http://schema.org/other.xml"
    with mock.patch("weaver.cli.WeaverClient._update_files", side_effect=parsed_inputs):
        with ExitStack() as stack:
            input_yaml = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=".yml"))
            yaml.safe_dump({"info": {"data": "yaml"}}, input_yaml)
            input_yaml.flush()
            input_yaml.seek(0)
            input_json = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=".json"))
            json.dump({"info": {"data": "json"}}, input_json)
            input_json.flush()
            input_json.seek(0)
            input_xml = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=".xml"))
            input_xml.write("<xml>data</xml>")
            input_xml.flush()
            input_xml.seek(0)
            input_tif = stack.enter_context(tempfile.NamedTemporaryFile(mode="wb", suffix=".tif"))
            input_tif.write(base64.b64encode("012345".encode("utf-8")))
            input_tif.flush()
            input_tif.seek(0)
            ctype_tif = ContentType.IMAGE_GEOTIFF  # must be URL-encoded to avoid parsing issue with separators
            assert " " in ctype_tif and ";" in ctype_tif  # just safeguard in case it is changed at some point
            ctype_tif_escaped = quote(ctype_tif)
            assert " " not in ctype_tif_escaped and ";" not in ctype_tif_escaped

            run_command([
                # weaver
                "execute",
                "-I", f"other:File={input_xml.name}@mediaType={ContentType.TEXT_XML}@schema={schema_xml}",
                "-I", f"input:File={input_yaml.name}@mediaType={ContentType.APP_YAML}@schema={schema_json}",
                "-I", f"input:File={input_json.name}@type={ContentType.APP_JSON}@rel=schema",
                "-I", f"other:File={input_tif.name}@mediaType={ctype_tif_escaped}@encoding=base64@rel=image",
                "-p", "fake_process",
                "-u", "http://fake.domain.com",
                "-q",  # since CLI fails purposely, avoid logging errors which would be confusing if debugging logs
            ], entrypoint=no_error_cli)

    assert len(inputs) == 1
    assert inputs[0] == {
        "input": [
            {
                "href": input_yaml.name,
                "format": {"mediaType": ContentType.APP_YAML, "schema": schema_json}
            },
            {
                "href": input_json.name,
                "type": ContentType.APP_JSON,  # valid alternate OGC representation of format/mediaType object
                "rel": "schema"  # known field in this case, ensure schema value is not confused with parameter keys
            }
        ],
        "other": [
            {
                "href": input_xml.name,
                "format": {"mediaType": ContentType.TEXT_XML, "schema": schema_xml}
            },
            {
                "href": input_tif.name,
                "format": {"mediaType": ContentType.IMAGE_GEOTIFF,  # must be unescaped
                           "encoding": "base64"},
                "rel": "image",  # irrelevant for real input in this case, but validate parameters are all propagated
            }
        ]
    }
