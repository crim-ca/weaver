"""
Unit tests of functions within :mod:`weaver.processes.wps_package`.

.. seealso::
    - :mod:`tests.functional.wps_package`.
"""
import contextlib
import os
import shutil
import sys
import tempfile
from collections import OrderedDict
from copy import deepcopy

import mock
import pytest
from pywps.app import WPSRequest

from weaver.datatype import Process
from weaver.exceptions import PackageExecutionError
from weaver.processes.wps_package import _check_package_file, _get_package_ordered_io  # noqa: W0212
from weaver.processes.wps_package import WpsPackage


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


class MockResponseOk(object):
    status_code = 200


def test_check_package_file_with_url():
    package_url = "https://example.com/package.cwl"
    with mock.patch("requests.Session.request", return_value=MockResponseOk()) as mock_request:
        res_path, is_url = _check_package_file(package_url)
        mock_request.assert_called_with("head", package_url)
    assert res_path == package_url
    assert is_url is True


def test_check_package_file_with_file_scheme():
    with mock.patch("requests.Session.request", return_value=MockResponseOk()) as mock_request:
        with tempfile.NamedTemporaryFile(mode="r", suffix="test-package.cwl") as tmp_file:
            package_file = "file://{}".format(tmp_file.name)
            res_path, is_url = _check_package_file(package_file)
            mock_request.assert_not_called()
            assert res_path == tmp_file.name
            assert is_url is False


def test_check_package_file_with_posix_path():
    with tempfile.NamedTemporaryFile(mode="r", suffix="test-package.cwl") as tmp_file:
        res_path, is_url = _check_package_file(tmp_file.name)
        assert res_path == tmp_file.name
        assert is_url is False


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Test for Windows only.")
def test_check_package_file_with_windows_path():
    test_file = "C:/Windows/Temp/package.cwl"   # fake existing, just test format handled correctly
    with mock.patch("os.path.isfile", return_value=True) as mock_isfile:
        res_path, is_url = _check_package_file(test_file)
        mock_isfile.assert_called_with(test_file)
    assert res_path == test_file
    assert is_url is False


def test_get_package_ordered_io_when_direct_type_string():
    inputs_as_strings = {
        "input-1": "File[]",
        "input-2": "float"
    }
    result = _get_package_ordered_io(inputs_as_strings)
    assert isinstance(result, list)
    assert len(result) == len(inputs_as_strings)
    assert all([isinstance(res_i, dict) for res_i in result])
    assert all([i in [res_i["id"] for res_i in result] for i in inputs_as_strings])
    assert all(["type" in res_i and res_i["type"] == inputs_as_strings[res_i["id"]] for res_i in result])


class MockWpsPackage(WpsPackage):
    """
    Mock of WPS package definition that ignores real status location updates and returns the mock for test validation.
    """
    mock_status_location = None

    @property
    def status_location(self):
        return self.mock_status_location

    @status_location.setter
    def status_location(self, value):
        pass


class MockWpsRequest(WPSRequest):
    def __init__(self, process_id=None):
        if not process_id:
            raise ValueError("must provide mock process identifier")
        super(MockWpsRequest, self).__init__()
        self.identifier = process_id
        self.json = {
            "identifier": process_id,
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
                        "allowed_values": [],
                    }
                ]
            },
            "outputs": {}
        }


class MockProcess(Process):
    def __init__(self, shell_command=None):
        if not shell_command:
            raise ValueError("must provide mock process shell command")
        # fix for Windows, need to tell explicitly the path to shell command
        # since cwltool sets subprocess.Popen with shell=False
        if sys.platform == "win32":
            shell_command = [shutil.which("cmd.exe"), "/c", shell_command]
        body = {
            "title": "mock-process",
            "id": "mock-process",
            "package": {
                "cwlVersion": "v1.0",
                "class": "CommandLineTool",
                "baseCommand": shell_command,
                "inputs": {
                    "message": {
                        "type": "string",
                        "inputBinding": {
                            "position": 1
                        }
                    }
                },
                "outputs": {}
            }
        }
        super(MockProcess, self).__init__(body)


def test_stdout_stderr_logging_for_commandline_tool_success():
    """
    Execute a process and assert that stdout is correctly logged to log file upon successful process execution.
    """
    with contextlib.ExitStack() as stack:
        xml_file = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".xml"))
        workdir = stack.enter_context(tempfile.TemporaryDirectory())
        process = MockProcess(shell_command="echo")
        wps_package_instance = MockWpsPackage(identifier=process["id"], title=process["title"],
                                              payload=process, package=process["package"])
        wps_package_instance.mock_status_location = xml_file.name
        wps_package_instance.set_workdir(workdir)

        # ExecuteResponse mock
        wps_request = MockWpsRequest(process_id=process.id)
        wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()
        wps_package_instance._handler(wps_request, wps_response)

        # log assertions
        expect_log = os.path.splitext(wps_package_instance.mock_status_location)[0] + ".log"
        with open(expect_log, "r") as file:
            log_data = file.read()
            # FIXME: add more specific asserts... validate CWL command called and sub-operations logged
            assert "Dummy message" in log_data


def test_stdout_stderr_logging_for_commandline_tool_failure():
    """
    Execute a process and assert that stderr is correctly logged to log file upon failing process execution.
    """
    with contextlib.ExitStack() as stack:
        xml_file = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".xml"))
        workdir = stack.enter_context(tempfile.TemporaryDirectory())
        process = MockProcess(shell_command="not_existing_command")
    wps_package_instance = MockWpsPackage(identifier=process["id"], title=process["title"],
                                          payload=process, package=process["package"])
    wps_package_instance.mock_status_location = xml_file.name
    wps_package_instance.set_workdir(workdir)

    # ExecuteResponse mock
    wps_request = MockWpsRequest()
    wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()
    # FIXME: add more specific asserts... validate CWL command called but as some execution error entry logged
    try:
        wps_package_instance._handler(wps_request, wps_response)
    except PackageExecutionError as exception:
        assert "Completed permanentFail" in exception.args[0]
    else:
        pytest.fail("\"wps_package._handler()\" was expected to throw \"PackageExecutionError\" exception")
