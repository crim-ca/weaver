"""
Unit test for :mod:`weaver.cli` utilities.
"""
import argparse
import base64
import contextlib
import copy
import inspect
import itertools
import json
import os
import tempfile
import uuid
from contextlib import ExitStack
from typing import TYPE_CHECKING
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
from weaver.exceptions import AuthenticationError
from weaver.formats import ContentEncoding, ContentType, get_cwl_file_format

if TYPE_CHECKING:
    from typing import List, Optional, Tuple, Union

    from weaver.typedefs import ExecutionResults


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
@pytest.mark.parametrize(
    ["init_url", "oper_url", "proc_id", "prov_id", "expect_base_url", "expect_proc_url"],
    [
        # With operation URL override
        (
            "https://init-url.example.com",
            "https://oper-url.example.com",
            "test-process",
            None,
            "https://oper-url.example.com",
            "https://oper-url.example.com/processes/test-process",
        ),
        (
            "https://init-url.example.com",
            "https://oper-url.example.com",
            "test-process",
            None,
            "https://oper-url.example.com",
            "https://oper-url.example.com/processes/test-process",
        ),
        (
            "https://init-url.example.com",
            "https://oper-url.example.com/processes",
            "test-process",
            None,
            "https://oper-url.example.com",
            "https://oper-url.example.com/processes/test-process",
        ),
        (
            "https://init-url.example.com",
            "https://oper-url.example.com/processes",
            "test-process",
            "test-provider",
            "https://oper-url.example.com",
            "https://oper-url.example.com/providers/test-provider/processes/test-process",
        ),
        (
            "https://init-url.example.com",
            "https://oper-url.example.com/processes/test-process",
            "test-process",
            "test-provider",
            "https://oper-url.example.com",
            "https://oper-url.example.com/providers/test-provider/processes/test-process",
        ),
        (
            "https://init-url.example.com/jobs",
            "https://oper-url.example.com/processes/test-process",
            "test-process",
            "test-provider",
            "https://oper-url.example.com",
            "https://oper-url.example.com/providers/test-provider/processes/test-process",
        ),
        (
            "https://init-url.example.com/providers/test-provider",
            "https://oper-url.example.com/processes/test-process",
            "test-process",
            "test-provider",
            "https://oper-url.example.com",
            "https://oper-url.example.com/providers/test-provider/processes/test-process",
        ),
        (
            "https://init-url.example.com/providers/test-provider/processes/test-process",
            "https://oper-url.example.com/processes/test-process/processes/test-process",
            "test-process",
            "test-provider",
            "https://oper-url.example.com",
            "https://oper-url.example.com/providers/test-provider/processes/test-process",
        ),
        # Without operation URL (only init URL)
        (
            "https://init-url.example.com",
            None,
            "test-process",
            None,
            "https://init-url.example.com",
            "https://init-url.example.com/processes/test-process",
        ),
        (
            "https://init-url.example.com/processes",
            None,
            "test-process",
            None,
            "https://init-url.example.com",
            "https://init-url.example.com/processes/test-process",
        ),
        (
            "https://init-url.example.com/processes/test-process",
            None,
            "test-process",
            None,
            "https://init-url.example.com",
            "https://init-url.example.com/processes/test-process",
        ),
        (
            "https://init-url.example.com/",  # final slash imported, should be removed
            None,
            "test-process",
            None,
            "https://init-url.example.com",
            "https://init-url.example.com/processes/test-process",
        ),
        (
            "https://init-url.example.com/",  # final slash imported, should be removed
            None,
            "test-process",
            "test-provider",
            "https://init-url.example.com",
            "https://init-url.example.com/providers/test-provider/processes/test-process",
        ),
        (
            "https://init-url.example.com/jobs/",  # final slash imported, should be removed
            None,
            "test-process",
            "test-provider",
            "https://init-url.example.com",
            "https://init-url.example.com/providers/test-provider/processes/test-process",
        ),
        (
            "https://init-url.example.com/jobs",  # no final slash variant
            None,
            "test-process",
            "test-provider",
            "https://init-url.example.com",
            "https://init-url.example.com/providers/test-provider/processes/test-process",
        ),
        (
            f"https://init-url.example.com/jobs/{uuid.uuid4()}",
            None,
            "test-process",
            "test-provider",
            "https://init-url.example.com",
            "https://init-url.example.com/providers/test-provider/processes/test-process",
        ),
        (
            "https://init-url.example.com/providers/test-provider",
            None,
            "test-process",
            "test-provider",
            "https://init-url.example.com",
            "https://init-url.example.com/providers/test-provider/processes/test-process",
        ),
        (
            "https://init-url.example.com/providers/test-provider/processes/test-process",
            None,
            "test-process",
            "test-provider",
            "https://init-url.example.com",
            "https://init-url.example.com/providers/test-provider/processes/test-process",
        ),
    ]
)
def test_cli_url_resolve_process(init_url, oper_url, proc_id, prov_id, expect_base_url, expect_proc_url):
    client = WeaverClient(url=init_url)
    result = client._get_url(url=oper_url)
    assert result == expect_base_url
    result = client._get_process_url(url=oper_url, process_id=proc_id, provider_id=prov_id)
    assert result == expect_proc_url


@pytest.mark.cli
@pytest.mark.parametrize("url", ["'localhost:4001'", "\"localhost:4001\""])
def test_cli_url_handle_quotes(url):
    client = WeaverClient(url)
    assert client._url == "http://localhost:4001"


@pytest.mark.cli
@pytest.mark.parametrize(
    ["parameters", "expect_settings"],
    [
        # provided with specific 'request_' prefixed options
        (
            {"request_timeout": 10, "ignored": True},
            {
                "weaver.request_options": {
                    "requests": [
                        {
                            "url": "http://localhost:4001/*",
                            "method": "*",
                            "timeout": 10,
                        }
                    ]
                }
            }
        ),
        # provided with specific 'request_' prefixed options, including special HTTP method/URL
        (
            {"request_timeout": 10, "ignored": True, "request_method": "GET,POST", "request_url": "http://*"},
            {
                "weaver.request_options": {
                    "requests": [
                        {
                            "url": "http://*",
                            "method": "GET,POST",
                            "timeout": 10,
                        }
                    ]
                }
            }
        ),
        # provided with predefined 'request_options'
        (
            {"request_options": {"timeout": 10}},
            {
                "weaver.request_options": {
                    "requests": [
                        {
                            "url": "http://localhost:4001/*",
                            "method": "*",
                            "timeout": 10,
                        }
                    ]
                }
            }
        ),
        # provided with predefined 'request_options' with extra definitions
        (
            {"request_options": {"timeout": 10, "method": "GET"}},
            {
                "weaver.request_options": {
                    "requests": [
                        {
                            "url": "http://localhost:4001/*",
                            "method": "GET",
                            "timeout": 10,
                        }
                    ]
                }
            }
        ),
        # provided with predefined 'request_options' with alternate URL
        (
            {"request_options": {"timeout": 10, "url": ["http://other.com/*", "https://*"]}},
            {
                "weaver.request_options": {
                    "requests": [
                        {
                            "url": ["http://other.com/*", "https://*"],
                            "method": "*",
                            "timeout": 10,
                        }
                    ]
                }
            }
        ),
        # provided with explicit settings structure
        (
            {
                "weaver.request_options": {
                    "requests": [
                        {
                            "url": "http://localhost:4001/*",
                            "method": "*",
                            "timeout": 10,
                        }
                    ]
                }
            },
            {
                "weaver.request_options": {
                    "requests": [
                        {
                            "url": "http://localhost:4001/*",
                            "method": "*",
                            "timeout": 10,
                        }
                    ]
                }
            }
        )
    ]
)
def test_cli_request_options_setup(parameters, expect_settings):
    client = WeaverClient("http://localhost:4001", **parameters)
    assert client._settings == expect_settings


def test_cli_request_options_parsing():
    with mock.patch(
        "weaver.cli.WeaverClient._request",
        side_effect=lambda *_, **__: MockedResponse(json={}),
    ) as mocked_oper:
        run_command([
            # weaver
            "info",
            # request options
            "--request-timeout", "15",  # backward support / existing option before '--request-option'
            "--request-option", "method=GET,POST",
            "--request-option", "url=http://*",
            "--request-option", "cache_enabled=false",
            # operation URL
            "-u", "https://fake.domain.com",
            "-q",  # avoid logging info which would be confusing if debugging logs
        ], entrypoint=weaver_cli)

    mocked_oper.assert_called_once()
    mocked_oper.assert_called_with(
        "GET",
        "https://fake.domain.com",
        auth=None,
        headers={"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON},
        x_headers=None,
        request_timeout=15,
        request_retries=None,
        settings={"weaver.request_options": {
            "requests": [{"method": "GET,POST", "url": "http://*", "cache_enabled": "false"}]}
        }
    )


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
def test_parse_inputs_from_file_relative_paths():
    """
    Validate relative file resolutions from execution input file.

    When a 'inputs' file is provided for execution, and contains relative local paths, they should consider the relative
    location of the file prior to the :term:`CLI` ``PWD``. This common pattern allows the inputs file definition and all
    its contained references to remain consistent when moved together between locations without hard-coded paths.

    This handling is performed during the '_upload_files' step since only this operation needs to resolve a local path.
    Therefore, we mock the actual 'upload' operation to avoid the request and validate the path resolution worked.
    If it didn't work, an error would have been raised before (file not found), or it would not be mapped to a vault
    in the case of non-local (file://) reference.
    """
    local_inputs = []  # to be filled by mock on vault uploads (therefore local file resolved)

    def mock_describe(*_, **__):
        return OperationResult(False, code=500)

    def mock_upload(href, *_, **__):
        local_inputs.append(href)
        f_id = str(uuid.uuid4())
        body = {"file_href": f"vault://{f_id}", "file_id": f_id, "access_token": f_id}
        return OperationResult(True, code=200, body=body)

    cwd = os.getcwd()
    try:
        with ExitStack() as stack:
            # use 'describe' to early-stop the operation, since it is the step right after parsing and upload of inputs
            stack.enter_context(mock.patch("weaver.cli.WeaverClient.describe", side_effect=mock_describe))
            stack.enter_context(mock.patch("weaver.cli.WeaverClient.upload", side_effect=mock_upload))
            tmp_dir1 = stack.enter_context(tempfile.TemporaryDirectory())
            tmp_dir2 = stack.enter_context(tempfile.TemporaryDirectory())
            os.chdir(tmp_dir2)  # ensure that PWD-based relative path resolution still works after job-file path

            path1 = "./local-file.txt"
            file1 = os.path.abspath(os.path.join(tmp_dir1, path1))
            path2 = "./nested/local-file.txt"
            file2 = os.path.abspath(os.path.join(tmp_dir1, path2))
            path3 = "./other-file.txt"
            file3 = os.path.abspath(os.path.join(tmp_dir1, path3))
            path4 = "./other-dir-file.txt"
            file4 = os.path.abspath(os.path.join(tmp_dir2, path4))
            for file in [file1, file2, file3, file4]:
                os.makedirs(os.path.dirname(file), exist_ok=True)
                with open(file, mode="w", encoding="utf-8") as f:
                    f.write("test")

            cwl_inputs = {
                "input1": "data",  # not affected since not a file reference
                "input2": {"class": "File", "path": "https://fake.domain.com/some-file.txt"},  # ignore not local file
                "input3": {"class": "File", "path": path1},
                "input4": [
                    {"class": "File", "path": path2},
                    {"class": "File", "path": f"file://{file3}"},  # ensure absolute path still resolves
                ],
                "input5": {"class": "File", "path": path4},  # relative to PWD
            }
            cwl_inputs_path = os.path.join(tmp_dir1, "inputs.json")
            with open(cwl_inputs_path, mode="w", encoding="utf-8") as cwl_inputs_file:
                json.dump(cwl_inputs, cwl_inputs_file)

            result = WeaverClient().execute("fake_process", inputs=cwl_inputs_path, url="https://fake.domain.com")
    finally:
        os.chdir(cwd)
    assert result.code == 500, "expected early-stop of execution operation"
    assert len(local_inputs) == 4
    assert local_inputs == [file1, file2, file3, file4], "expected local paths to be resolved"


@pytest.mark.cli
@pytest.mark.parametrize(
    ["as_cli_list", "input_structure", "file_refs"],
    itertools.product(
        # Because the CLI uses 'nargs' to collect potentially multiple '-I' options it can result into a list of path
        # More than one path is not allowed (see 'test_parse_inputs_multiple_files_rejected'), but the single-item list
        # must still be handled. These using both invocation cases as the CLI (embedded list) vs WeaverClient (direct).
        [False, True],
        # Test both cases where multiple inputs have a single File, or a single input has multiple File[] references
        ["single", "array"],
        # Path combinations
        [
            # simple relative paths
            [
                "./file1.txt",
                "./file2.txt",
                "./nested/file3.txt",
            ],
            # complex nested navigation
            [
                "./file1.txt",
                "./nested/deep/level/../../file3.txt",
                "./nested/deep/level/file2.txt",
            ],
            # file references starting with "../../" (files outside input file directory)
            [
                "../../outside/file1.txt",
                "./local.txt",
                "../../outside/nested/file2.txt",
            ],
            # Mixed: simple, nested navigation, and parent directory references
            [
                "./simple.txt",
                "../sibling/file.txt",
                "./nested/../other.txt",
            ],
            # file:// URI references (absolute paths)
            [
                "file://",  # placeholders, will be replaced with absolute paths
                "file://",
                "file://",
            ],
        ]
    )
)
def test_parse_inputs_relative_paths_extended_resolutions(as_cli_list, input_structure, file_refs):
    """
    Validate extended scenarios for relative file resolutions from execution input file.

    This test extends :func:`test_parse_inputs_from_file_relative_paths` to cover various combinations:
    - Simple relative paths (e.g., "./file.txt", "./nested/file.txt")
    - Complex nested navigation (e.g., "./nested/deep/level/../../file.txt")
    - Parent directory references starting with "../../" to test files outside input file directory
    - Single file references vs array of file references (i.e.: mapping to ``File`` vs ``File[]`` CWL types)
    - Explicit URI references ``file://`` with absolute paths

    The test validates that the CLI properly resolves relative paths regardless of these combinations,
    ensuring that file references embedded within the provided "inputs file" are primarily resolved relative
    those file's location, rather than the current working directory of the :term:`CLI` command.
    """
    local_inputs = []

    def mock_describe(*_, **__):
        return OperationResult(False, code=500)

    def mock_upload(href, *_, **__):
        local_inputs.append(href)
        f_id = str(uuid.uuid4())
        body = {"file_href": f"vault://{f_id}", "file_id": f_id, "access_token": f_id}
        return OperationResult(True, code=200, body=body)

    cwd = os.getcwd()
    try:
        with ExitStack() as stack:
            stack.enter_context(mock.patch("weaver.cli.WeaverClient.describe", side_effect=mock_describe))
            stack.enter_context(mock.patch("weaver.cli.WeaverClient.upload", side_effect=mock_upload))
            tmp_base = stack.enter_context(tempfile.TemporaryDirectory())
            tmp_pwd = stack.enter_context(tempfile.TemporaryDirectory())
            os.chdir(tmp_pwd)

            # Create inputs file in a nested directory to allow "../../" references
            inputs_dir = os.path.join(tmp_base, "inputs", "nested")
            os.makedirs(inputs_dir, exist_ok=True)

            # Create files based on the relative paths specified in file_refs
            created_files = []
            resolved_paths = []
            use_file_uri = all(ref.startswith("file://") for ref in file_refs)

            for idx, rel_path in enumerate(file_refs):
                if use_file_uri:
                    # Special case: create simple files and use absolute paths
                    file_name = f"file{idx + 1}.txt"
                    file_path = os.path.join(tmp_base, file_name)
                else:
                    # Resolve the relative path from the inputs directory
                    # Use os.path.normpath to resolve all "." and ".." components
                    file_path = os.path.normpath(os.path.join(inputs_dir, rel_path))

                    # Also ensure all intermediate directories in the non-normalized path exist
                    # This is needed because os.path.isfile() checks intermediate dirs even when normalizing
                    non_normalized_path = os.path.join(inputs_dir, rel_path)
                    intermediate_dir = os.path.dirname(non_normalized_path)
                    if intermediate_dir:
                        os.makedirs(intermediate_dir, exist_ok=True)

                # Ensure parent directory of the final normalized file path exists
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, mode="w", encoding="utf-8") as f:
                    f.write("test")

                created_files.append(file_path)
                resolved_paths.append(os.path.abspath(file_path))

            # Build CWL inputs structure
            if use_file_uri:
                # Use absolute file:// URIs
                paths_to_use = [f"file://{abs_path}" for abs_path in resolved_paths]
            else:
                # Use the relative paths as specified
                paths_to_use = file_refs

            if input_structure == "array":
                cwl_inputs = {
                    "input1": "data",
                    "input2": [{"class": "File", "path": path} for path in paths_to_use]
                }
            else:
                cwl_inputs = {"input1": "data"}
                for idx, path in enumerate(paths_to_use, start=2):
                    cwl_inputs[f"input{idx}"] = {"class": "File", "path": path}

            inputs_path = os.path.join(inputs_dir, "inputs.json")
            with open(inputs_path, mode="w", encoding="utf-8") as f:
                json.dump(cwl_inputs, f)
            inputs_path = [inputs_path] if as_cli_list else inputs_path

            result = WeaverClient().execute(
                "fake_process",
                inputs=inputs_path,
                url="https://fake.domain.com"
            )
    finally:
        os.chdir(cwd)

    # Verify all files were resolved correctly
    assert result.code == 500, f"expected early-stop of execution operation, got {result.code}: {result.message}"
    assert len(local_inputs) == len(file_refs), (
        f"expected {len(file_refs)} local file uploads, got {len(local_inputs)}"
    )
    expected_files = set(resolved_paths)
    assert set(local_inputs) == expected_files, (
        f"expected files {expected_files}, got {set(local_inputs)}"
    )


@pytest.mark.cli
def test_parse_inputs_multiple_files_rejected():
    """
    Validate that multiple input files (e.g., multiple ``-I inputs.json``) are properly rejected.

    When multiple input JSON/YAML files are provided via multiple ``-I`` options, the CLI should detect
    this case and provide a clear error message, rather than treating the file paths as literal input
    values or causing a confusing error later in the process.
    """
    cwd = os.getcwd()
    try:
        with ExitStack() as stack:
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            os.chdir(tmp_dir)

            # Create two separate input files
            inputs1 = {
                "input1": {"class": "File", "path": "./file1.txt"},
            }
            inputs2 = {
                "input2": {"class": "File", "path": "./file2.txt"},
            }

            inputs_path1 = os.path.join(tmp_dir, "inputs1.json")
            inputs_path2 = os.path.join(tmp_dir, "inputs2.json")

            with open(inputs_path1, mode="w", encoding="utf-8") as f:
                json.dump(inputs1, f)
            with open(inputs_path2, mode="w", encoding="utf-8") as f:
                json.dump(inputs2, f)

            # Simulate multiple -I options as they would be processed by argparse
            # Each -I creates a sublist, resulting in a 2D list that gets flattened
            multiple_inputs = [[inputs_path1], [inputs_path2]]

            result = WeaverClient().execute(
                "fake_process",
                inputs=multiple_inputs,
                url="https://fake.domain.com"
            )
    finally:
        os.chdir(cwd)

    # Verify that the operation fails with a clear error message
    assert not result.success, "expected operation to fail when multiple input files are provided"
    assert result.message is not None, "expected error message to be provided"
    assert "multiple" in result.message.lower() or "more than one" in result.message.lower(), (
        f"expected error message to mention 'multiple' or 'more than one' files, got: {result.message}"
    )


@pytest.mark.cli
@pytest.mark.parametrize(
    ["missing_files", "ignore_errors", "expect_success"],
    [
        # No missing files - should always succeed
        ([], False, True),
        ([], True, True),
        # One missing file without ignore flag - should fail
        (["./missing.txt"], False, False),
        # One missing file with ignore flag - should succeed (file skipped with warning)
        (["./missing.txt"], True, True),
        # Multiple missing files without ignore flag - should fail with all files listed
        (["./missing1.txt", "./missing2.txt", "./nested/missing3.txt"], False, False),
        # Multiple missing files with ignore flag - should succeed (all skipped with warnings)
        (["./missing1.txt", "./missing2.txt", "./nested/missing3.txt"], True, True),
        # Mix of existing and missing files without ignore flag - should fail
        (["./exists.txt", "./missing.txt"], False, False),
        # Mix of existing and missing files with ignore flag - should succeed (missing skipped)
        (["./exists.txt", "./missing.txt"], True, True),
    ]
)
def test_parse_inputs_missing_files_handling(missing_files, ignore_errors, expect_success):
    """
    Validate that missing local file references are handled correctly based on ``--inputs-ignore-errors`` flag.

    When ``inputs_ignore_errors=False`` (default):
    - Missing files should cause a failure with a clear error message without moving on to the execution
    - All missing files should be listed in the error message (not just the first one that fails resolution)

    When ``inputs_ignore_errors=True``:
    - Missing files should be skipped with a warning
    - Execution should proceed with the remaining valid inputs
    """
    local_inputs = []

    def mock_describe(*_, **__):
        return OperationResult(False, code=500)

    def mock_upload(href, *_, **__):
        local_inputs.append(href)
        f_id = str(uuid.uuid4())
        body = {"file_href": f"vault://{f_id}", "file_id": f_id, "access_token": f_id}
        return OperationResult(True, code=200, body=body)

    cwd = os.getcwd()
    try:
        with ExitStack() as stack:
            stack.enter_context(mock.patch("weaver.cli.WeaverClient.describe", side_effect=mock_describe))
            stack.enter_context(mock.patch("weaver.cli.WeaverClient.upload", side_effect=mock_upload))
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            os.chdir(tmp_dir)

            # Create the inputs file
            cwl_inputs = {"input1": "data"}
            existing_files = []

            # Add file references - some will exist, some won't based on the test case
            input_idx = 2
            for file_path in missing_files:
                # Determine if this should be an existing file (for mixed scenarios)
                is_existing = file_path == "./exists.txt"

                if is_existing:
                    # Create the file
                    full_path = os.path.join(tmp_dir, file_path.lstrip("./"))
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, mode="w", encoding="utf-8") as f:
                        f.write("test")
                    existing_files.append(os.path.abspath(full_path))

                # Add to inputs (whether file exists or not)
                cwl_inputs[f"input{input_idx}"] = {"class": "File", "path": file_path}
                input_idx += 1

            inputs_path = os.path.join(tmp_dir, "inputs.json")
            with open(inputs_path, mode="w", encoding="utf-8") as f:
                json.dump(cwl_inputs, f)

            result = WeaverClient().execute(
                "fake_process",
                inputs=inputs_path,
                url="https://fake.domain.com",
                inputs_ignore_errors=ignore_errors
            )
    finally:
        os.chdir(cwd)

    # Validate results based on expected outcome
    if expect_success:
        # When ignore_errors=True or no missing files, operation should succeed (or fail at describe step)
        # The describe mock returns 500, so we expect that as the error code
        assert result.code == 500, f"expected early-stop at describe with code 500, got {result.code}: {result.message}"

        # Verify only existing files were uploaded
        assert len(local_inputs) == len(existing_files), (
            f"expected {len(existing_files)} file uploads, got {len(local_inputs)}"
        )
    else:
        # When ignore_errors=False and there are missing files, should fail before describe
        assert not result.success, "expected operation to fail due to missing files"
        assert result.code == 404, f"expected 404 Not Found error code, got {result.code}"

        # Verify error message mentions missing files
        msg_lower = result.message.lower()
        assert (
            "missing" in msg_lower or "not found" in msg_lower or "not all files could be resolved" in msg_lower
        ), f"expected error message to mention missing files, got: {result.message}"

        # Verify ALL missing files are listed in the error message
        actual_missing = [f for f in missing_files if f != "./exists.txt"]
        for missing_file in actual_missing:
            assert missing_file in result.message, (
                f"expected missing file '{missing_file}' to be mentioned in error message, got: {result.message}"
            )


@pytest.mark.cli
@pytest.mark.format
@pytest.mark.parametrize(
    ["data_inputs", "expect_inputs"],
    [
        (
            # CWL definition with an input literal
            {
                "in": 1,
            },
            {
                "in": 1,
            }
        ),
        (
            # CWL definition with an input array of literals
            {
                "in": [1, 2, 3],
            },
            {
                "in": [1, 2, 3],
            }
        ),
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
            # CWL definition with media-type format of the file
            {
                "in": {
                    "class": "File",
                    "path": "https://fake.domain.com/netcdf.nc",
                    "format": get_cwl_file_format(ContentType.APP_NETCDF, make_reference=True),
                },
            },
            {
                "in": {
                    "href": "https://fake.domain.com/netcdf.nc",
                    "type": ContentType.APP_NETCDF,
                    "format": {"mediaType": ContentType.APP_NETCDF, "encoding": ContentEncoding.BASE64},
                },
            }
        ),
        (
            # CWL definition with array of files
            {
                "in": [
                    {
                        "class": "File",
                        "path": "https://fake.domain.com/netcdf-1.nc",
                        "format": get_cwl_file_format(ContentType.APP_NETCDF, make_reference=True),
                    },

                    {
                        "class": "File",
                        "path": "https://fake.domain.com/netcdf-2.nc",
                        "format": get_cwl_file_format(ContentType.APP_NETCDF, make_reference=True),
                    }
                ],
            },
            {
                "in": [
                    {
                        "href": "https://fake.domain.com/netcdf-1.nc",
                        "type": ContentType.APP_NETCDF,
                        "format": {"mediaType": ContentType.APP_NETCDF, "encoding": ContentEncoding.BASE64},
                    },
                    {
                        "href": "https://fake.domain.com/netcdf-2.nc",
                        "type": ContentType.APP_NETCDF,
                        "format": {"mediaType": ContentType.APP_NETCDF, "encoding": ContentEncoding.BASE64},
                    },
                ]
            }
        ),
        (
            # CWL remote directory reference
            {
                "in-dir": {
                    "class": "Directory",
                    "path": "https://fake.domain.com/test/",
                },
            },
            {
                "in-dir": {
                    "href": "https://fake.domain.com/test/",
                    "type": ContentType.APP_DIR,
                },
            }
        ),
        (
            # OGC remote directory reference with explicit 'type' field
            {
                "in-dir": {
                    "href": "https://fake.domain.com/test/",
                    "type": ContentType.APP_DIR
                },
            },
            {
                "in-dir": {
                    "href": "https://fake.domain.com/test/",
                    "type": ContentType.APP_DIR,
                },
            }
        ),
        (
            # OGC remote "directory" reference with '/' suffix
            {
                "in-dir": {
                    "href": "https://fake.domain.com/test/",
                },
            },
            {
                "in-dir": {
                    "href": "https://fake.domain.com/test/",
                    # NOTE: 'type' not injected for backward compatibility of servers using it as API request endpoint
                },
            }
        ),
        (
            # OGC execution body with explicit 'inputs' to be interpreted as is
            {
                "inputs": {
                    "in-1": {"value": "data"},
                    "in-2": {"href": "https://fake.domain.com/some-file.json", "type": ContentType.APP_JSON},
                },
            },
            {
                "in-1": {"value": "data"},
                "in-2": {"href": "https://fake.domain.com/some-file.json", "type": ContentType.APP_JSON},
            }
        ),
        (
            # OGC execution mapping that must not be confused as a CWL mapping
            {
                "in-1": {"value": "data"},
                "in-2": {"href": "https://fake.domain.com/some-file.json", "type": ContentType.APP_JSON},
            },
            {
                "in-1": {"value": "data"},
                "in-2": {"href": "https://fake.domain.com/some-file.json", "type": ContentType.APP_JSON},
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
@pytest.mark.parametrize("inputs_value", [
    {"href": "../some-local-dir/"},
    {"href": "../some-local-dir/", "type": ContentType.APP_DIR},
    {"href": "file:///tmp/some-local-dir/"},
    {"path": "../some-local-dir/", "class": "Directory"},
    {"path": "file:///tmp/some-local-dir/", "class": "Directory"},
])
def test_parse_inputs_unsupported_directory_upload(inputs_value):
    inputs = {"test": inputs_value}
    result = WeaverClient(url="https://fake.domain.com")._prepare_inputs(inputs=inputs)
    assert result.success is False
    assert result.code == 501
    assert "Cannot upload local directory" in result.message


@pytest.mark.cli
@pytest.mark.format
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


@pytest.mark.cli
def test_auth_handler_basic():
    req = WebTestRequest({})
    auth = BasicAuthHandler(username="test", password=str(uuid.uuid4()))
    resp = auth(req)  # type: ignore
    assert "Authorization" in resp.headers and len(resp.headers["Authorization"])
    assert resp.headers["Authorization"].startswith("Basic")


@pytest.mark.cli
def test_auth_handler_bearer():
    req = WebTestRequest({})
    auth = BearerAuthHandler(identity=str(uuid.uuid4()), url="https://example.com")
    token = str(uuid.uuid4())
    with mock.patch(
        "requests.Session.request",
        side_effect=lambda *_, **__: mocked_auth_response("access_token", token)
    ):
        resp = auth(req)  # type: ignore
    assert "Authorization" in resp.headers and len(resp.headers["Authorization"])
    assert resp.headers["Authorization"].startswith("Bearer") and resp.headers["Authorization"].endswith(token)


@pytest.mark.cli
def test_auth_handler_bearer_explicit_token():
    req = WebTestRequest({})
    token = str(uuid.uuid4())
    auth = BearerAuthHandler(token=token)
    with mock.patch("requests.Session.request") as mock_request:
        resp = auth(req)  # type: ignore
        mock_request.assert_not_called()
    assert "Authorization" in resp.headers and len(resp.headers["Authorization"])
    assert resp.headers["Authorization"].startswith("Bearer") and resp.headers["Authorization"].endswith(token)


@pytest.mark.cli
def test_auth_handler_bearer_explicit_token_matches_request_token():
    req_explicit_token = WebTestRequest({})
    req_request_token = WebTestRequest({})
    token = str(uuid.uuid4())
    auth_explicit_token = BearerAuthHandler(token=token)
    auth_request_token = BearerAuthHandler(identity=str(uuid.uuid4()), url="https://example.com")
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


@pytest.mark.cli
def test_auth_handler_cookie():
    req = WebTestRequest({})
    auth = CookieAuthHandler(identity=str(uuid.uuid4()), url="https://example.com")
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


@pytest.mark.cli
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


@pytest.mark.cli
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


@pytest.mark.cli
def test_auth_handler_cookie_explicit_token_matches_request_token():
    req_explicit_token = WebTestRequest({})
    req_request_token = WebTestRequest({})
    token = str(uuid.uuid4())
    auth_explicit_token = CookieAuthHandler(token=token)
    auth_request_token = CookieAuthHandler(identity=str(uuid.uuid4()), url="https://example.com")
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


@pytest.mark.cli
def test_auth_request_handler_no_url_or_token_init():
    with pytest.raises(AuthenticationError):
        BearerAuthHandler(identity=str(uuid.uuid4()))

    try:
        BearerAuthHandler(token=str(uuid.uuid4()))  # OK
        BearerAuthHandler(url="https://example.com")  # OK
    except Exception as exc:
        pytest.fail(f"Expected no init error from valid combinations. Got [{exc}]")


@pytest.mark.cli
def test_auth_request_handler_no_url_ignored_request():
    req = WebTestRequest({})
    auth = BearerAuthHandler(
        identity=str(uuid.uuid4()),
        url="https://example.com",  # URL must be passed to avoid error
    )
    auth.url = None  # reset after init check
    with mock.patch("requests.Session.request") as mock_request:
        resp = auth(req)  # type: ignore
        mock_request.assert_not_called()
    assert not resp.headers, "No headers should have been added since URL could not be resolved."


@pytest.mark.cli
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
                "href": fake_href,
                "type": expect_file_format["mediaType"]
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
                    "type": ContentType.APP_JSON,
                    "format": {"mediaType": ContentType.APP_JSON},
                },
                {
                    "href": fake_href2,
                    "type": ContentType.APP_ZIP,
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


@pytest.mark.cli
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
    with mock.patch("weaver.cli.WeaverClient._request", return_value=OperationResult(success=False, code=404)):
        result = WeaverClient(url="https://fake.domain.com").version()
    assert result.code == 404
    assert "Failed to obtain server version." in result.message


@pytest.mark.cli
def test_cli_replace_with_body():
    """
    Test replace operation with full body parameter.
    """
    test_body = {"processDescription": {"id": "test-process", "version": "2.0.0"}}
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "2.0.0"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response):
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", body=test_body)

    assert result.success
    assert result.code == 200


@pytest.mark.cli
def test_cli_replace_with_metadata_kvp():
    """
    Test replace operation with metadata as key=value pairs.
    """
    metadata_list = ["title=Updated Title", "description=Updated description"]
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.0.1"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response):
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=metadata_list)

    assert result.success
    assert result.code == 200


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_with_inputs_outputs():
    """
    Test replace operation with inputs and outputs.
    """
    test_inputs = {"input1": {"title": "Input 1"}}
    test_outputs = {"output1": {"title": "Output 1"}}
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.1.0"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response):
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", inputs=test_inputs, outputs=test_outputs)

    assert result.success
    assert result.code == 200


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_with_version():
    """
    Test replace operation with explicit version.
    """
    test_metadata = {"title": "Updated Title"}
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "3.0.0"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response):
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=test_metadata, version="3.0.0")

    assert result.success
    assert result.code == 200


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_with_http_method():
    """
    Test replace operation with explicit HTTP method selection.
    """
    test_metadata = {"title": "Updated"}
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=test_metadata, http_method="PATCH")

    assert result.success
    assert mock_req.call_args[0][0] == "PATCH"


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_no_parameters_error():
    """
    Test that replace operation fails when no update parameters are provided.
    """
    client = WeaverClient(url="https://fake.domain.com")
    result = client.replace(process_id="test-process")

    assert not result.success
    assert "At least one field" in result.message


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_invalid_metadata_kvp():
    """
    Test that replace operation handles metadata KVP gracefully.

    Note: parse_kvp treats 'key' without '=' as valid (empty list value),
    so this just verifies the parsing succeeds but sends an empty array.
    """
    metadata_list = ["invalid_format"]  # Missing '=' - becomes key with empty list
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.0.1"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=metadata_list)

    assert result.success
    # Verify parse_kvp treated it as key with empty value
    call_kwargs = mock_req.call_args[1]
    payload = call_kwargs["json"]
    assert "invalid_format" in payload
    assert payload["invalid_format"] == []  # Empty list for key without value


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_with_complex_metadata_field():
    """
    Test replace operation with complex metadata field (list of metadata objects).
    Tests both link format (rel+href) and value format to showcase the distinction.
    """
    metadata_updates = {
        "metadata": [
            # Link-based metadata (href describes where to find information)
            {"role": "https://schema.org/author", "rel": "author",
             "href": "https://orcid.org/0000-0000-0000-0000", "title": "Author ORCID"},
            # Value-based metadata (actual value/data)
            {"role": "https://schema.org/name", "value": "John Doe"},
            {"role": "https://schema.org/codeRepository",
             "rel": "repository", "href": "https://github.com/org/repo"}
        ]
    }
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.0.1"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=metadata_updates)

    assert result.success
    # Verify the request payload contains the metadata field
    call_kwargs = mock_req.call_args[1]
    assert "json" in call_kwargs
    payload = call_kwargs["json"]
    assert "metadata" in payload
    assert len(payload["metadata"]) == 3
    # Verify link format entries
    assert payload["metadata"][0]["role"] == "https://schema.org/author"
    assert payload["metadata"][0]["rel"] == "author"
    assert payload["metadata"][0]["href"] == "https://orcid.org/0000-0000-0000-0000"
    assert payload["metadata"][0]["title"] == "Author ORCID"
    # Verify value format entry
    assert payload["metadata"][1]["role"] == "https://schema.org/name"
    assert payload["metadata"][1]["value"] == "John Doe"
    # Verify another link
    assert payload["metadata"][2]["role"] == "https://schema.org/codeRepository"
    assert payload["metadata"][2]["rel"] == "repository"


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_with_links():
    """
    Test replace operation with links field.
    """
    metadata_updates = {
        "links": [
            {"rel": "service-doc", "href": "https://example.com/docs", "type": "text/html"},
            {"rel": "license", "href": "https://example.com/license"}
        ]
    }
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.0.1"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=metadata_updates)

    assert result.success
    call_kwargs = mock_req.call_args[1]
    payload = call_kwargs["json"]
    assert "links" in payload
    assert len(payload["links"]) == 2
    assert payload["links"][0]["rel"] == "service-doc"
    assert payload["links"][1]["rel"] == "license"


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_with_keywords():
    """
    Test replace operation with keywords field.
    """
    metadata_updates = {"keywords": ["climate", "weather", "temperature"]}
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.0.1"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=metadata_updates)

    assert result.success
    call_kwargs = mock_req.call_args[1]
    payload = call_kwargs["json"]
    assert "keywords" in payload
    assert payload["keywords"] == ["climate", "weather", "temperature"]


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_with_job_control_options():
    """
    Test replace operation with jobControlOptions (MINOR-level change).
    """
    metadata_updates = {"jobControlOptions": ["async-execute", "sync-execute"]}
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.1.0"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=metadata_updates)

    assert result.success
    call_kwargs = mock_req.call_args[1]
    payload = call_kwargs["json"]
    assert "jobControlOptions" in payload
    assert payload["jobControlOptions"] == ["async-execute", "sync-execute"]


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_with_visibility():
    """
    Test replace operation with visibility field (MINOR-level change).
    """
    metadata_updates = {"visibility": "public"}
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.1.0"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=metadata_updates)

    assert result.success
    call_kwargs = mock_req.call_args[1]
    payload = call_kwargs["json"]
    assert "visibility" in payload
    assert payload["visibility"] == "public"


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_additive_body_and_metadata():
    """
    Test that body and metadata parameters are additive (metadata overlays body).
    """
    test_body = {"processDescription": {"id": "test-process", "title": "Original Title", "version": "2.0.0"}}
    metadata_updates = {"title": "Override Title", "keywords": ["new-tag"]}
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "2.0.0"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        # Mock the body parsing to avoid needing full deployment logic
        with mock.patch.object(client, "_parse_deploy_body", return_value=OperationResult(True, body=test_body)):
            with mock.patch.object(client, "_parse_deploy_package", return_value=OperationResult(True, body=test_body)):
                result = client.replace(process_id="test-process", body=test_body, metadata=metadata_updates)

    assert result.success
    call_kwargs = mock_req.call_args[1]
    payload = call_kwargs["json"]
    # Verify metadata fields override body fields
    assert payload["title"] == "Override Title"
    assert payload["keywords"] == ["new-tag"]


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_with_metadata_json_string():
    """
    Test replace operation with metadata provided as JSON string.
    """
    metadata_json = '{"title": "JSON Title", "description": "JSON Description", "keywords": ["json", "test"]}'
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.1.0"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=metadata_json)

    assert result.success
    call_kwargs = mock_req.call_args[1]
    payload = call_kwargs["json"]
    assert payload["title"] == "JSON Title"
    assert payload["description"] == "JSON Description"
    assert payload["keywords"] == ["json", "test"]


@pytest.mark.cli
def test_cli_replace_with_metadata_file():
    """
    Test replace operation with metadata loaded from file.
    """
    metadata_dict = {
        "title": "File Title",
        "metadata": [
            {"role": "https://schema.org/license", "rel": "license", "href": "https://example.com/license"}
        ]
    }
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.0.1"})

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp_file:
        json.dump(metadata_dict, tmp_file)
        tmp_file.flush()
        tmp_path = tmp_file.name

    try:
        with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
            client = WeaverClient(url="https://fake.domain.com")
            result = client.replace(process_id="test-process", metadata=tmp_path)

        assert result.success
        call_kwargs = mock_req.call_args[1]
        payload = call_kwargs["json"]
        assert payload["title"] == "File Title"
        assert "metadata" in payload
        assert len(payload["metadata"]) == 1
    finally:
        os.unlink(tmp_path)


@pytest.mark.cli
@pytest.mark.oap_part2
def test_cli_replace_multiple_fields_combined():
    """
    Test replace operation combining multiple field types.
    """
    metadata_updates = {
        "title": "Combined Title",
        "keywords": ["tag1", "tag2"],
        "metadata": [{"role": "https://schema.org/author", "rel": "author",
                      "href": "https://orcid.org/0000-0000-0000-0000", "title": "Author ORCID"}],
        "links": [{"rel": "about", "href": "https://example.com/about"}],
        "visibility": "public"
    }
    mock_response = MockedResponse(status_code=200, json_body={"id": "test-process", "version": "1.1.0"})

    with mock.patch("weaver.cli.request_extra", return_value=mock_response) as mock_req:
        client = WeaverClient(url="https://fake.domain.com")
        result = client.replace(process_id="test-process", metadata=metadata_updates)

    assert result.success
    call_kwargs = mock_req.call_args[1]
    payload = call_kwargs["json"]
    assert payload["title"] == "Combined Title"
    assert payload["keywords"] == ["tag1", "tag2"]
    assert len(payload["metadata"]) == 1
    assert len(payload["links"]) == 1
    assert payload["visibility"] == "public"


@pytest.mark.cli
@pytest.mark.parametrize(
    ["outputs", "output_ids", "expect_success", "expect_result", "expect_error_msg"],
    [
        # No filtering - return unchanged
        (
            {
                "output1": {"href": "http://example.com/data1"},
                "output2": [{"href": "http://example.com/data2"}, {"href": "http://example.com/data3"}]
            },
            None,
            True,
            {
                "output1": {"href": "http://example.com/data1"},
                "output2": [{"href": "http://example.com/data2"}, {"href": "http://example.com/data3"}]
            },
            None
        ),
        # Simple ID filtering
        (
            {
                "output1": {"href": "http://example.com/data1"},
                "output2": {"href": "http://example.com/data2"},
                "output3": {"href": "http://example.com/data3"}
            },
            ["output1", "output3"],
            True,
            {
                "output1": {"href": "http://example.com/data1"},
                "output3": {"href": "http://example.com/data3"}
            },
            None
        ),
        # Array with specific indices (with None placeholders)
        (
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    {"href": "http://example.com/data1"},
                    {"href": "http://example.com/data2"},
                    {"href": "http://example.com/data3"}
                ]
            },
            [("output1", 1), ("output1", 3)],
            True,
            {
                "output1": [
                    None,
                    {"href": "http://example.com/data1"},
                    None,
                    {"href": "http://example.com/data3"}
                ]
            },
            None
        ),
        # Array preserve length with None placeholders
        (
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    {"href": "http://example.com/data1"},
                    {"href": "http://example.com/data2"}
                ]
            },
            [("output1", 0), ("output1", 2)],
            True,
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    None,
                    {"href": "http://example.com/data2"}
                ]
            },
            None
        ),
        # Single value with index 0 (allowed)
        (
            {"output1": {"href": "http://example.com/data"}},
            [("output1", 0)],
            True,
            {"output1": {"href": "http://example.com/data"}},
            None
        ),
        # Single value with invalid index (error)
        (
            {"output1": {"href": "http://example.com/data"}},
            [("output1", 1)],
            False,
            None,
            "not an array"
        ),
        # Array index out of range (error)
        (
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    {"href": "http://example.com/data1"}
                ]
            },
            [("output1", 5)],
            False,
            None,
            "out of range"
        ),
        # Negative array index (error)
        (
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    {"href": "http://example.com/data1"}
                ]
            },
            [("output1", -1)],
            False,
            None,
            "out of range"
        ),
        # Mixed simple and indexed IDs
        (
            {
                "output1": {"href": "http://example.com/data1"},
                "output2": [
                    {"href": "http://example.com/data2-0"},
                    {"href": "http://example.com/data2-1"},
                    {"href": "http://example.com/data2-2"}
                ],
                "output3": {"href": "http://example.com/data3"}
            },
            ["output1", ("output2", 1)],
            True,
            {
                "output1": {"href": "http://example.com/data1"},
                "output2": [
                    None,
                    {"href": "http://example.com/data2-1"},
                    None
                ]
            },
            None
        ),
        # Multiple indices for same output
        (
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    {"href": "http://example.com/data1"},
                    {"href": "http://example.com/data2"},
                    {"href": "http://example.com/data3"},
                    {"href": "http://example.com/data4"}
                ]
            },
            [("output1", 0), ("output1", 2), ("output1", 4)],
            True,
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    None,
                    {"href": "http://example.com/data2"},
                    None,
                    {"href": "http://example.com/data4"}
                ]
            },
            None
        ),
        # Non-existent output ID (filtered out)
        (
            {
                "output1": {"href": "http://example.com/data1"},
                "output2": {"href": "http://example.com/data2"}
            },
            ["output1", "output999"],
            True,
            {"output1": {"href": "http://example.com/data1"}},
            None
        ),
        # Empty array with index (error)
        (
            {"output1": []},
            [("output1", 0)],
            False,
            None,
            "out of range"
        ),
        # Single element array
        (
            {"output1": [{"href": "http://example.com/data0"}]},
            [("output1", 0)],
            True,
            {"output1": [{"href": "http://example.com/data0"}]},
            None
        ),
        # Simple values (string literals)
        (
            {"out1": "val1", "out2": "val2", "out3": "val3"},
            ["out1", "out3"],
            True,
            {"out1": "val1", "out3": "val3"},
            None
        ),
        # Array with string values
        (
            {"out1": ["a", "b", "c"]},
            [("out1", 0), ("out1", 2)],
            True,
            {"out1": ["a", None, "c"]},
            None
        ),
        # Array without index - returns full array, filters other outputs
        (
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    {"href": "http://example.com/data1"},
                    {"href": "http://example.com/data2"}
                ],
                "output2": {"href": "http://example.com/other"},
                "output3": ["a", "b", "c"]
            },
            ["output1"],
            True,
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    {"href": "http://example.com/data1"},
                    {"href": "http://example.com/data2"}
                ]
            },
            None
        ),
        # Single value without index - returns as-is, filters other outputs
        (
            {
                "output1": {"href": "http://example.com/data"},
                "output2": ["a", "b"],
                "output3": {"href": "http://example.com/other"}
            },
            ["output1"],
            True,
            {"output1": {"href": "http://example.com/data"}},
            None
        ),
        # Array with index 0 - returns only that element with None placeholders, filters other outputs
        (
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    {"href": "http://example.com/data1"},
                    {"href": "http://example.com/data2"}
                ],
                "output2": {"href": "http://example.com/other"},
                "output3": ["x", "y", "z"]
            },
            [("output1", 0)],
            True,
            {
                "output1": [
                    {"href": "http://example.com/data0"},
                    None,
                    None
                ]
            },
            None
        ),
        # Mix of array without index and single value without index
        (
            {
                "arr1": ["a", "b", "c"],
                "single1": "value1",
                "arr2": [1, 2, 3, 4],
                "single2": "value2",
                "arr3": ["x", "y"]
            },
            ["arr1", "single1", "arr2"],
            True,
            {
                "arr1": ["a", "b", "c"],
                "single1": "value1",
                "arr2": [1, 2, 3, 4]
            },
            None
        ),
        # Mix of array with index and array without index
        (
            {
                "arr1": ["a", "b", "c"],
                "arr2": [1, 2, 3, 4],
                "arr3": ["x", "y", "z"]
            },
            ["arr1", ("arr2", 1), ("arr2", 3)],
            True,
            {
                "arr1": ["a", "b", "c"],
                "arr2": [None, 2, None, 4]
            },
            None
        ),
    ]
)
def test_filter_outputs(
    outputs,            # type: ExecutionResults
    output_ids,         # type: Optional[List[Union[str, Tuple[str, int]]]]
    expect_success,     # type: bool
    expect_result,      # type: Optional[ExecutionResults]
    expect_error_msg,   # type: Optional[str]
):                      # type: (...) -> None
    outputs_copy = copy.deepcopy(outputs)
    result = WeaverClient._filter_outputs(outputs_copy, output_ids)

    assert isinstance(result, OperationResult)
    if expect_success:
        assert result.success
        assert result.body == expect_result
    else:
        assert not result.success
        if expect_error_msg:
            assert expect_error_msg in result.message.lower()
