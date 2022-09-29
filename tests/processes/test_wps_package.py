"""
Unit tests of functions within :mod:`weaver.processes.wps_package`.

.. seealso::
    - :mod:`tests.functional.wps_package`.
"""
import contextlib
import io
import logging
import os
import re
import shutil
import sys
import tempfile

import pytest

from weaver.datatype import Process
from weaver.exceptions import PackageExecutionError
from weaver.processes.wps_package import WpsPackage
from weaver.wps.service import WorkerRequest

# pylint: disable=R1729  # ignore non-generator representation employed for displaying test log results


class MockWpsPackage(WpsPackage):
    """
    Mock of WPS package definition that ignores real status location updates and returns the mock for test validation.
    """

    def __init__(self, *_, **__):
        super(MockWpsPackage, self).__init__(*_, **__)
        self.mock_status_location = None

    @property
    def status_location(self):
        return self.mock_status_location

    @status_location.setter
    def status_location(self, value):
        pass


class MockWpsRequest(WorkerRequest):
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


def test_stdout_stderr_logging_for_commandline_tool_success(caplog):
    """
    Execute a process and assert that stdout is correctly logged to log file upon successful process execution.
    """
    caplog.set_level(logging.INFO, logger="cwltool")
    caplog.set_level(logging.INFO, logger="weaver")

    with contextlib.ExitStack() as stack:
        xml_file = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".xml"))  # noqa
        workdir = stack.enter_context(tempfile.TemporaryDirectory())
        process = MockProcess(shell_command="echo")
        wps_package_instance = MockWpsPackage(identifier=process["id"], title=process["title"],
                                              payload=process, package=process["package"])
        wps_package_instance.settings = {}
        wps_package_instance.mock_status_location = xml_file.name
        wps_package_instance.set_workdir(workdir)
        expect_log = os.path.splitext(wps_package_instance.mock_status_location)[0] + ".log"

        # ExecuteResponse mock
        wps_request = MockWpsRequest(process_id=process.id)
        wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()

        # depending on debug/command-line & pytest config, captured logs can be 'hijacked' or not, use any active one
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            wps_package_instance._handler(wps_request, wps_response)
        with open(expect_log, mode="r", encoding="utf-8") as file:
            job_log = file.read()
        log_data = stdout.getvalue() + "\n" + caplog.text + "\n" + job_log

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
        assert re.match(
            r".*"
            rf"cwltool.*job {process.id}.*\$ echo \\\n"
            r"\s+'Dummy message' \> [\w\-/\.]+/stdout\.log 2\> [\w\-/\.]+/stderr\.log\n"
            r".*",
            log_data,
            re.MULTILINE | re.DOTALL
        ), f"Information expected in:\n{log_data}"
        assert f"[cwltool] [job {process.id}] completed success" in log_data


def test_stdout_stderr_logging_for_commandline_tool_failure(caplog):
    """
    Execute a process and assert that stderr is correctly logged to log file upon failing process execution.
    """
    caplog.set_level(logging.INFO, logger="cwltool")
    caplog.set_level(logging.INFO, logger="weaver")

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
        # depending on debug/command-line & pytest config, captured logs can be 'hijacked' or not, use any active one
        log_err = stderr.getvalue() + "\n" + caplog.text
        assert "Could not retrieve any internal application log." not in log_err, (
            "Since tool did not reach execution, not captured logged is expected."
        )
        assert "Traceback (most recent call last):" in log_err
        assert "weaver.processes.wps_package|mock-process" in log_err
        assert "Missing required input parameter 'message'" in log_err
    else:
        pytest.fail("\"wps_package._handler()\" was expected to throw \"PackageExecutionError\" exception")


def test_stdout_stderr_logging_for_commandline_tool_exception(caplog):
    """
    Execute a process and assert that traceback is correctly logged to log file upon failing process execution.
    """
    caplog.set_level(logging.INFO, logger="cwltool")
    caplog.set_level(logging.INFO, logger="weaver")

    with contextlib.ExitStack() as stack:
        xml_file = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".xml"))  # noqa
        workdir = stack.enter_context(tempfile.TemporaryDirectory())
        process = MockProcess(shell_command="not_existing_command")
    wps_package_instance = MockWpsPackage(identifier=process["id"], title=process["title"],
                                          payload=process, package=process["package"])
    wps_package_instance.settings = {}
    wps_package_instance.mock_status_location = xml_file.name
    wps_package_instance.set_workdir(workdir)
    expect_log = os.path.splitext(wps_package_instance.mock_status_location)[0] + ".log"

    # ExecuteResponse mock
    wps_request = MockWpsRequest(process_id=process["id"])
    wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()

    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            wps_package_instance._handler(wps_request, wps_response)
    except PackageExecutionError as exception:
        assert "Completed permanentFail" in exception.args[0]
        # depending on debug/command-line & pytest config, captured logs can be 'hijacked' or not, use any active one
        with open(expect_log, mode="r", encoding="utf-8") as file:
            job_err = file.read()
        log_err = stderr.getvalue() + "\n" + caplog.text + "\n" + job_err
        assert "Could not retrieve any internal application log." in log_err, (
            "Since command did not run, nothing captured is expected"
        )
        assert "Traceback (most recent call last):" in log_err
        assert "weaver.processes.wps_package|mock-process" in log_err
    else:
        pytest.fail("\"wps_package._handler()\" was expected to throw \"PackageExecutionError\" exception")
