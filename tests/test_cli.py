"""
Unit test for :mod:`weaver.cli` utilities.
"""
import argparse
import base64
import contextlib
import inspect
import json
import os
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
    SubscriberAction,
    WeaverClient,
    main as weaver_cli
)
from weaver.formats import ContentEncoding, ContentType


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
            WeaverClient(url="https://fake.domain.com").execute("")
            WeaverClient().execute("", url="https://fake.domain.com")
    except ValueError:
        pytest.fail()


@pytest.mark.cli
def test_cli_url_override_by_operation():
    with mock.patch("weaver.cli.WeaverClient._parse_inputs", return_value=OperationResult()):
        client = WeaverClient(url="https://fake.domain.com")
        real_get_url = WeaverClient._get_url
        returned_url = []

        def mock_get_url(_url):
            _url = real_get_url(client, _url)
            returned_url.append(_url)
            return _url

        with mock.patch("weaver.cli.WeaverClient._get_url", side_effect=mock_get_url) as mocked:
            client.execute(url="https://other.domain.com", process_id="random")
        assert mocked.call_args.args[0] == "https://other.domain.com"
        assert returned_url[0] == "https://other.domain.com"


@pytest.mark.cli
def test_parse_inputs_from_file():
    inputs = []
    mock_result = OperationResult(False, code=500)

    def parsed_inputs(_inputs, *_, **__):
        inputs.append(_inputs)
        return mock_result

    # use '_upload_files' to early-stop the operation, since it is the step right after parsing inputs
    with mock.patch("weaver.cli.WeaverClient._upload_files", side_effect=parsed_inputs):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as input_json:
            json.dump({"inputs": {"input1": "data"}}, input_json)
            input_json.flush()
            input_json.seek(0)
            result = WeaverClient().execute("fake_process", inputs=input_json.name, url="https://fake.domain.com")
    assert result is mock_result
    assert len(inputs) == 1
    assert inputs[0] == {"input1": "data"}


@pytest.mark.cli
@pytest.mark.parametrize(
    ["data_inputs", "expect_inputs"],
    [
        (
            # CWL definition with an input named 'inputs' not to be confused with OGC execution body
            {
                "inputs": {
                    "class": "File",
                    "path": "https://fake.domain.com/some-file.txt",
                },
            },
            {
                "inputs": {
                    "href": "https://fake.domain.com/some-file.txt",
                },
            }
        ),
        (
            # OGC execution body with explicit 'inputs' to be interpreted as is
            {
                "inputs": {
                    "in-1": {"value": "data"},
                    "in-2": {"href": "https://fake.domain.com/some-file.json", "type": "application/json"},
                },
            },
            {
                "in-1": {"value": "data"},
                "in-2": {"href": "https://fake.domain.com/some-file.json", "type": "application/json"},
            }
        ),
        (
            # OGC execution mapping that must not be confused as a CWL mapping
            {
                "in-1": {"value": "data"},
                "in-2": {"href": "https://fake.domain.com/some-file.json", "type": "application/json"},
            },
            {
                "in-1": {"value": "data"},
                "in-2": {"href": "https://fake.domain.com/some-file.json", "type": "application/json"},
            }
        )
    ]
)
def test_parse_inputs(data_inputs, expect_inputs):
    inputs = []
    mock_result = OperationResult(False, code=500)

    def parsed_inputs(_inputs, *_, **__):
        inputs.append(_inputs)
        return mock_result

    # use '_upload_files' to early-stop the operation, since it is the step right after parsing inputs
    with mock.patch("weaver.cli.WeaverClient._upload_files", side_effect=parsed_inputs):
        result = WeaverClient().execute("fake_process", inputs=data_inputs, url="https://fake.domain.com")
    assert result is mock_result
    assert len(inputs) == 1
    assert inputs[0] == expect_inputs


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

    # use '_upload_files' to early-stop the operation, since it is the step right after parsing inputs
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
                "-u", "https://fake.domain.com",
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
    schema_json = "https://schema.org/random.json"
    schema_xml = "https://schema.org/other.xml"
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
                "-u", "https://fake.domain.com",
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


def test_auth_handler_bearer_explicit_token():
    req = WebTestRequest({})
    token = str(uuid.uuid4())
    auth = BearerAuthHandler(token=token)
    with mock.patch("requests.Session.request") as mock_request:
        resp = auth(req)  # type: ignore
        mock_request.assert_not_called()
    assert "Authorization" in resp.headers and len(resp.headers["Authorization"])
    assert resp.headers["Authorization"].startswith("Bearer") and resp.headers["Authorization"].endswith(token)


def test_auth_handler_bearer_explicit_token_matches_request_token():
    req_explicit_token = WebTestRequest({})
    req_request_token = WebTestRequest({})
    token = str(uuid.uuid4())
    auth_explicit_token = BearerAuthHandler(token=token)
    auth_request_token = BearerAuthHandler(identity=str(uuid.uuid4()))
    with mock.patch(
        "requests.Session.request",
        side_effect=lambda *_, **__: mocked_auth_response("access_token", token)
    ) as mock_request:
        resp_explicit_token = auth_explicit_token(req_explicit_token)  # type: ignore
        mock_request.assert_not_called()
        resp_request_token = auth_request_token(req_request_token)  # type: ignore
    assert "Authorization" in resp_explicit_token.headers and len(resp_explicit_token.headers["Authorization"])
    assert "Authorization" in resp_request_token.headers and len(resp_request_token.headers["Authorization"])
    assert resp_explicit_token.headers["Authorization"] == resp_request_token.headers["Authorization"]


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


def test_auth_handler_cookie_explicit_token_string():
    req = WebTestRequest({})
    token = str(uuid.uuid4())
    auth = CookieAuthHandler(token=token)
    with mock.patch("requests.Session.request") as mock_request:
        resp = auth(req)  # type: ignore
        mock_request.assert_not_called()
    assert "Authorization" not in resp.headers
    assert "Cookie" in resp.headers and len(resp.headers["Cookie"])
    assert resp.headers["Cookie"] == token


def test_auth_handler_cookie_explicit_token_mapping_single():
    req = WebTestRequest({})
    cookie_key = "auth_example"
    cookie_value = str(uuid.uuid4())
    token = {cookie_key: cookie_value}
    auth = CookieAuthHandler(token=token)
    with mock.patch("requests.Session.request") as mock_request:
        resp = auth(req)  # type: ignore
        mock_request.assert_not_called()
    assert "Authorization" not in resp.headers
    assert "Cookie" in resp.headers and len(resp.headers["Cookie"])
    assert resp.headers["Cookie"] == f"{cookie_key}={cookie_value}"


def test_auth_handler_cookie_explicit_token_mapping_multi():
    req = WebTestRequest({})
    token = {"auth_example": str(uuid.uuid4()), "auth_example2": str(uuid.uuid4())}
    auth = CookieAuthHandler(token=token)
    with mock.patch("requests.Session.request") as mock_request:
        resp = auth(req)  # type: ignore
        mock_request.assert_not_called()
    assert "Authorization" not in resp.headers
    assert "Cookie" in resp.headers and len(resp.headers["Cookie"])
    assert f"auth_example={token['auth_example']}" in resp.headers["Cookie"].split("; ")
    assert f"auth_example2={token['auth_example2']}" in resp.headers["Cookie"].split("; ")


def test_auth_handler_cookie_explicit_token_matches_request_token():
    req_explicit_token = WebTestRequest({})
    req_request_token = WebTestRequest({})
    token = str(uuid.uuid4())
    auth_explicit_token = CookieAuthHandler(token=token)
    auth_request_token = CookieAuthHandler(identity=str(uuid.uuid4()))
    with mock.patch(
        "requests.Session.request",
        side_effect=lambda *_, **__: mocked_auth_response("access_token", token)
    ) as mock_request:
        resp_explicit_token = auth_explicit_token(req_explicit_token)  # type: ignore
        mock_request.assert_not_called()
        resp_request_token = auth_request_token(req_request_token)  # type: ignore
    assert "Cookie" in resp_explicit_token.headers and len(resp_explicit_token.headers["Cookie"])
    assert "Cookie" in resp_request_token.headers and len(resp_request_token.headers["Cookie"])
    assert resp_explicit_token.headers["Cookie"] == resp_request_token.headers["Cookie"]


def test_upload_file_not_found():
    with tempfile.NamedTemporaryFile() as tmp_file_deleted:
        pass   # delete on close
    result = WeaverClient().upload(tmp_file_deleted.name)
    assert not result.success
    assert "does not exist" in result.message


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
@pytest.mark.parametrize(
    ["test_file_name", "expect_file_format"],
    [
        ("some-file.zip", {"mediaType": ContentType.APP_ZIP, "encoding": ContentEncoding.BASE64}),
        ("some-text.txt", {"mediaType": ContentType.TEXT_PLAIN}),
        ("some-data.json", {"mediaType": ContentType.APP_JSON}),
    ]
)
def test_file_inputs_uploaded_to_vault(test_file_name, expect_file_format):
    fake_href = f"https://some-host.com/{test_file_name}"
    fake_id = "fake_id"
    fake_token = "fake_token"

    output_body = {"file_href": fake_href, "file_id": fake_id, "access_token": fake_token}
    expected_output = (
        {
            "file": {
                "format": expect_file_format,
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

    with tempfile.NamedTemporaryFile(mode="w", suffix=os.path.splitext(test_file_name)[-1]) as input_file:
        inputs = {"file": {"href": input_file.name}}
        with mock.patch("weaver.cli.WeaverClient.upload", side_effect=mock_upload):
            result = WeaverClient()._upload_files(inputs=inputs)
    assert result == expected_output


@pytest.mark.cli
def test_file_inputs_array_uploaded_to_vault():
    fake_href1 = "https://some-host.com/file1.json"
    fake_href2 = "https://some-host.com/file2.zip"
    fake_id = "fake_id"
    fake_token = "fake_token"

    expected_output = (
        {
            "file": [
                {
                    "href": fake_href1,
                    "format": {"mediaType": ContentType.APP_JSON},
                },
                {
                    "href": fake_href2,
                    "format": {
                        "mediaType": ContentType.APP_ZIP,
                        "encoding": ContentEncoding.BASE64,
                    },
                }
            ]
        },
        {
            "X-Auth-Vault": f"token {fake_token}; id={fake_id}"
        }
    )

    def mock_upload(_href, *_, **__):
        fake_href = fake_href1 if _href.endswith(".json") else fake_href2
        output_body = {"file_href": fake_href, "file_id": fake_id, "access_token": fake_token}
        mock_result = OperationResult(True, code=200, body=output_body)
        return mock_result

    with contextlib.ExitStack() as stack:
        input1 = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=os.path.splitext(fake_href1)[-1]))
        input2 = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=os.path.splitext(fake_href2)[-1]))
        inputs = {
            "file": [
                {"href": input1.name},
                {"href": input2.name}
            ]
        }
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


@pytest.mark.parametrize(
    ["expect_error", "subscriber_option", "subscriber_dest", "subscriber_value", "subscriber_result"],
    [
        (
            None,
            "--subscriber-email",
            "subscriber.email",
            "test@email.com",
            {"subscriber": {"email": "test@email.com"}},
        ),
        (
            None,
            "--subscriber-callback",
            "subscriber.callback",
            "https://some-server.com/path",
            {"subscriber": {"callback": "https://some-server.com/path"}}
        ),
        (
            None,
            "--random-option",
            "subscriber.email",
            "test@email.com",
            {"subscriber": {"email": "test@email.com"}},
        ),
        (
            None,
            "--random-option",
            "subscriber.callback",
            "https://some-server.com/path",
            {"subscriber": {"callback": "https://some-server.com/path"}}
        ),
        (
            argparse.ArgumentError,
            "--subscriber-email",
            "subscriber.email",
            "https://some-server.com/path",
            None
        ),
        (
            argparse.ArgumentError,
            "--subscriber-callback",
            "subscriber.callback",
            "test@email.com",
            None,
        ),
        (
            argparse.ArgumentError,
            "--subscriber-email",
            "subscriber.email",
            "random",
            None
        ),
        (
            argparse.ArgumentError,
            "--subscriber-callback",
            "subscriber.callback",
            "random",
            None
        ),
        (
            NotImplementedError,
            "--subscriber-unknown",
            "subscriber.unknown",
            "test@email.com",
            None
        ),
        (
            NotImplementedError,
            "--subscriber-unknown",
            "subscriber.unknown",
            "https://some-server.com/path",
            None
        ),
    ]
)
def test_subscriber_parsing(expect_error, subscriber_option, subscriber_dest, subscriber_value, subscriber_result):
    ns = argparse.Namespace()
    try:
        action = SubscriberAction(["-sXX", subscriber_option], dest=subscriber_dest)
        action(argparse.ArgumentParser(), ns, subscriber_value)
    except Exception as exc:
        assert expect_error is not None, f"Test was not expected to fail, but raised {exc!s}."
        assert isinstance(exc, expect_error), f"Test expected to raise {expect_error}, but raised {exc!s} instead."
    else:
        assert expect_error is None, f"Test was expected to fail with {expect_error}, but did not raise"
        assert dict(**vars(ns)) == subscriber_result  # pylint: disable=R1735


@pytest.mark.cli
def test_cli_version_non_weaver():
    """
    Tests that the ``version`` operation is handled gracefully for a server not supporting it (Weaver-specific).
    """
    with mock.patch("requests.Session.request", return_value=MockedResponse(body="", status="404 Not Found")):
        with mock.patch("weaver.cli.WeaverClient._request", return_value=OperationResult(success=False, code=404)):
            result = WeaverClient(url="https://fake.domain.com").version()
    assert result.code == 404
    assert "Failed to obtain server version." in result.message
