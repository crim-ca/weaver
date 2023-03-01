"""
Unit test for :mod:`weaver.cli` utilities.
"""
import base64
import inspect
import json
import tempfile
import uuid
from contextlib import ExitStack
from urllib.parse import quote

import mock
import pytest
import yaml
from webtest import TestRequest as WebTestRequest  # avoid pytest collect warning

from tests.utils import MockedResponse, run_command
from weaver.cli import (
    BasicAuthHandler,
    BearerAuthHandler,
    CookieAuthHandler,
    OperationResult,
    WeaverClient,
    main as weaver_cli
)
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

    with mock.patch("weaver.cli.WeaverClient._upload_files", side_effect=parsed_inputs):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as input_json:
            json.dump({"inputs": {"input1": "data"}}, input_json)
            input_json.flush()
            input_json.seek(0)
            result = WeaverClient().execute("fake_process", inputs=input_json.name, url="http://fake.domain.com")
    assert result is mock_result
    assert len(inputs) == 1
    assert inputs[0] == {"input1": "data"}


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

    with mock.patch("weaver.cli.WeaverClient._upload_files", side_effect=parsed_inputs):
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
    with mock.patch("weaver.cli.WeaverClient._upload_files", side_effect=parsed_inputs):
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


def mocked_auth_response(token_name, token_value, *_, **__):
    resp = MockedResponse()
    resp.json_body = {token_name: token_value}
    resp.headers = {"Content-Type": ContentType.APP_JSON}
    return resp


def test_auth_handler_basic():
    req = WebTestRequest({})
    auth = BasicAuthHandler(username="test", password=str(uuid.uuid4()))
    resp = auth(req)  # type: ignore
    assert "Authorization" in resp.headers and len(resp.headers["Authorization"])
    assert resp.headers["Authorization"].startswith("Basic")


def test_auth_handler_bearer():
    req = WebTestRequest({})
    auth = BearerAuthHandler(identity=str(uuid.uuid4()))
    token = str(uuid.uuid4())
    with mock.patch(
        "requests.Session.request",
        side_effect=lambda *_, **__: mocked_auth_response("access_token", token)
    ):
        resp = auth(req)  # type: ignore
    assert "Authorization" in resp.headers and len(resp.headers["Authorization"])
    assert resp.headers["Authorization"].startswith("Bearer") and resp.headers["Authorization"].endswith(token)


def test_auth_handler_cookie():
    req = WebTestRequest({})
    auth = CookieAuthHandler(identity=str(uuid.uuid4()))
    token = str(uuid.uuid4())
    with mock.patch(
        "requests.Session.request",
        side_effect=lambda *_, **__: mocked_auth_response("access_token", token)
    ):
        resp = auth(req)  # type: ignore
    assert "Authorization" not in resp.headers
    assert "Cookie" in resp.headers and len(resp.headers["Cookie"])
    assert resp.headers["Cookie"] == token


@pytest.mark.cli
def test_href_inputs_not_uploaded_to_vault():
    mock_result = OperationResult(False, code=500)

    def mock_upload(_href, *_, **__):
        return mock_result

    inputs = {"file": {"href": "https://fake.domain.com/fakefile.zip"}}
    with mock.patch("weaver.cli.WeaverClient.upload", side_effect=mock_upload):
        result = WeaverClient()._upload_files(inputs=inputs)
    assert result is not mock_result, "WeaverCLient.upload should not be called since reference is not local"
    assert result == (inputs, {})


@pytest.mark.cli
def test_file_inputs_uploaded_to_vault():
    fake_href = "https://some-host.com/some-file.zip"
    fake_id = "fake_id"
    fake_token = "fake_token"

    output_body = {"file_href": fake_href, "file_id": fake_id, "access_token": fake_token}
    expected_output = (
        {
            "file": {
                "format": {
                    "mediaType": ContentType.APP_ZIP
                },
                "href": fake_href
            }
        },
        {
            "X-Auth-Vault": f"token {fake_token}; id={fake_id}"
        }
    )

    mock_result = OperationResult(True, code=200, body=output_body)

    def mock_upload(_href, *_, **__):
        return mock_result

    with tempfile.NamedTemporaryFile(mode="w", suffix=".zip") as input_file:
        inputs = {"file": {"href": input_file.name}}
        with mock.patch("weaver.cli.WeaverClient.upload", side_effect=mock_upload):
            result = WeaverClient()._upload_files(inputs=inputs)
    assert result == expected_output


@pytest.mark.cli
def test_file_inputs_not_uploaded_to_vault():
    mock_result = OperationResult(False, code=500)  # Simulate a problem with vault upload

    def mock_upload(_href, *_, **__):
        return mock_result

    with tempfile.NamedTemporaryFile(mode="w", suffix=".zip") as input_file:
        inputs = {"file": {"href": input_file.name}}
        with mock.patch("weaver.cli.WeaverClient.upload", side_effect=mock_upload):
            result = WeaverClient()._upload_files(inputs=inputs)
    assert result is mock_result, "WeaverCLient.upload is expected to be called and should return a failed result."
