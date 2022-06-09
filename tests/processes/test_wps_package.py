"""
Unit tests of functions within :mod:`weaver.processes.wps_package`.

.. seealso::
    - :mod:`tests.functional.wps_package`.
"""
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile

import mock
import pytest
from pywps.app import WPSRequest

from weaver.datatype import Process
from weaver.exceptions import PackageExecutionError
from weaver.processes.wps_package import WpsPackage, _check_package_file  # noqa: W0212

# pylint: disable=R1729  # ignore non-generator representation employed for displaying test log results


class MockResponseOk(object):
    status_code = 200


def test_check_package_file_with_url():
    package_url = "https://example.com/package.cwl"
    with mock.patch("requests.Session.request", return_value=MockResponseOk()) as mock_request:
        res_path = _check_package_file(package_url)
        assert mock_request.call_count == 1
        assert mock_request.call_args[0][:2] == ("head", package_url)  # ignore extra args
    assert res_path == package_url


def test_check_package_file_with_file_scheme():
    with mock.patch("requests.Session.request", return_value=MockResponseOk()) as mock_request:
        with tempfile.NamedTemporaryFile(mode="r", suffix="test-package.cwl") as tmp_file:
            package_file = f"file://{tmp_file.name}"
            res_path = _check_package_file(package_file)
            mock_request.assert_not_called()
            assert res_path == tmp_file.name


def test_check_package_file_with_posix_path():
    with tempfile.NamedTemporaryFile(mode="r", suffix="test-package.cwl") as tmp_file:
        res_path = _check_package_file(tmp_file.name)
        assert res_path == tmp_file.name


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Test for Windows only.")
def test_check_package_file_with_windows_path():
    test_file = "C:/Windows/Temp/package.cwl"   # fake existing, just test format handled correctly
    with mock.patch("os.path.isfile", return_value=True) as mock_isfile:
        res_path = _check_package_file(test_file)
        mock_isfile.assert_called_with(test_file)
    assert res_path == test_file


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
    def __init__(self, process_id=None, with_message_input=True):
        if not process_id:
            raise ValueError("must provide mock process identifier")
        super(MockWpsRequest, self).__init__()
        self.identifier = process_id
        data = {
            "identifier": process_id,
            "operation": "execute",
            "version": "1.0.0",
            "language": "null",
            "identifiers": "null",
            "store_execute": "true",
            "status": "true",
            "lineage": "true",
            "raw": "false",
            "inputs": {},
            "outputs": {}
        }
        if with_message_input:
            data["inputs"]["message"] = [
                {
                    "identifier": "message",
                    "title": "A dummy message",
                    "type": "literal",
                    "data_type": "string",
                    "data": "Dummy message",
                    "allowed_values": [],
                }
            ]
        self.json = data


class MockProcess(Process):
    def __init__(self, shell_command, arguments=None, with_message_input=True):
        if not shell_command:
            raise ValueError("must provide mock process shell command")
        # fix for Windows, need to tell explicitly the path to shell command
        # since cwltool sets subprocess.Popen with shell=False
        if sys.platform == "win32":
            shell_command = [shutil.which("cmd.exe"), "/c", shell_command]
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": shell_command,
            "inputs": {},
            "outputs": {}
        }
        if isinstance(arguments, list) and arguments:
            cwl["arguments"] = arguments
        if with_message_input:
            cwl["inputs"]["message"] = {
                "type": "string",
                "inputBinding": {
                    "position": 1
                }
            }
        body = {
            "title": "mock-process",
            "id": "mock-process",
            "package": cwl
        }
        super(MockProcess, self).__init__(body)


def test_stdout_stderr_logging_for_commandline_tool_success():
    """
    Execute a process and assert that stdout is correctly logged to log file upon successful process execution.
    """
    with contextlib.ExitStack() as stack:
        xml_file = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".xml"))  # noqa
        workdir = stack.enter_context(tempfile.TemporaryDirectory())
        process = MockProcess(shell_command="echo")
        wps_package_instance = MockWpsPackage(identifier=process["id"], title=process["title"],
                                              payload=process, package=process["package"])
        wps_package_instance.settings = {}
        wps_package_instance.mock_status_location = xml_file.name
        wps_package_instance.set_workdir(workdir)

        # ExecuteResponse mock
        wps_request = MockWpsRequest(process_id=process.id)
        wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()
        wps_package_instance._handler(wps_request, wps_response)

        # log assertions
        expect_log = os.path.splitext(wps_package_instance.mock_status_location)[0] + ".log"
        with open(expect_log, mode="r", encoding="utf-8") as file:
            log_data = file.read()
        # captured log portion added by the injected stdout/stderr logs
        assert re.match(
            r".*"
            r"----- Captured Log \(stdout\) -----\n"
            r"Dummy message\n"
            r"----- End of Logs -----\n"
            r".*",
            log_data,
            re.MULTILINE | re.DOTALL
        )
        # cwltool call with reference to the command and stdout/stderr redirects
        log_cwltool = f"[cwltool] [job {process.id}]"
        assert re.match(
            r".*"
            rf"{log_cwltool}.*\$ echo \\\n"
            r"\s+'Dummy message' \> [\w\-/\.]+/stdout\.log 2\> [\w\-/\.]+/stderr\.log\n"
            r".*",
            log_data,
            re.MULTILINE | re.DOTALL
        )
        assert f"{log_cwltool} completed success" in log_data


def test_stdout_stderr_logging_for_commandline_tool_failure():
    """
    Execute a process and assert that stderr is correctly logged to log file upon failing process execution.
    """
    with contextlib.ExitStack() as stack:
        xml_file = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".xml"))  # noqa
        workdir = stack.enter_context(tempfile.TemporaryDirectory())
        process = MockProcess(shell_command="echo", with_message_input=True)
    wps_package_instance = MockWpsPackage(identifier=process["id"], title=process["title"],
                                          payload=process, package=process["package"])
    wps_package_instance.settings = {}
    wps_package_instance.mock_status_location = xml_file.name
    wps_package_instance.set_workdir(workdir)

    # ExecuteResponse mock
    wps_request = MockWpsRequest(process_id=process["id"], with_message_input=False)
    wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()

    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            wps_package_instance._handler(wps_request, wps_response)
    except PackageExecutionError as exception:
        assert "Failed package execution" in exception.args[0]
        assert "Missing required input parameter 'message'" in exception.args[0]
        log_err = stderr.getvalue()
        assert "Could not retrieve any internal application log." not in log_err, (
            "Since tool did not reach execution, not captured logged is expected."
        )
        assert "Traceback (most recent call last):" in log_err
        assert "[weaver.processes.wps_package|mock-process]" in log_err
        assert "Missing required input parameter 'message'" in log_err
    else:
        pytest.fail("\"wps_package._handler()\" was expected to throw \"PackageExecutionError\" exception")


def test_stdout_stderr_logging_for_commandline_tool_exception():
    """
    Execute a process and assert that traceback is correctly logged to log file upon failing process execution.
    """
    with contextlib.ExitStack() as stack:
        xml_file = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".xml"))  # noqa
        workdir = stack.enter_context(tempfile.TemporaryDirectory())
        process = MockProcess(shell_command="not_existing_command")
    wps_package_instance = MockWpsPackage(identifier=process["id"], title=process["title"],
                                          payload=process, package=process["package"])
    wps_package_instance.settings = {}
    wps_package_instance.mock_status_location = xml_file.name
    wps_package_instance.set_workdir(workdir)

    # ExecuteResponse mock
    wps_request = MockWpsRequest(process_id=process["id"])
    wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()

    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            wps_package_instance._handler(wps_request, wps_response)
    except PackageExecutionError as exception:
        assert "Completed permanentFail" in exception.args[0]
        log_err = stderr.getvalue()
        assert "Could not retrieve any internal application log." in log_err, (
            "Since command did not run, nothing captured is expected"
        )
        assert "Traceback (most recent call last):" in log_err
        assert "[weaver.processes.wps_package|mock-process]" in log_err
    else:
        pytest.fail("\"wps_package._handler()\" was expected to throw \"PackageExecutionError\" exception")
