"""
Unit tests of functions within :mod:`weaver.processes.wps_package`.

.. seealso::
    - :mod:`tests.functional.wps_package`.
"""
import contextlib
import copy
import io
import logging
import os
import re
import shutil
import sys
import tempfile
from typing import TYPE_CHECKING

import cwltool.process
import mock
import pytest

from tests.utils import assert_equal_any_order
from weaver.datatype import Process
from weaver.exceptions import PackageExecutionError
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_DOCKER_GPU,
    CWL_REQUIREMENT_CUDA,
    CWL_REQUIREMENT_CUDA_NAME,
    CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS,
    CWL_REQUIREMENT_CUDA_NAMESPACE,
    CWL_REQUIREMENT_PROCESS_GENERATOR,
    CWL_REQUIREMENT_TIME_LIMIT
)
from weaver.processes.wps_package import WpsPackage, _load_package_content, _update_package_compatibility
from weaver.wps.service import WorkerRequest

if TYPE_CHECKING:
    from typing import Dict, TypeVar
    from typing_extensions import Literal

    from weaver.typedefs import CWL

    KT = TypeVar("KT")
    VT_co = TypeVar("VT_co", covariant=True)

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

    def setup_docker_image(self):
        return None


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
            "requirements": {"DockerRequirement": {"dockerPull": "alpine:latest"}},
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
        expect_log = f"{os.path.splitext(wps_package_instance.mock_status_location)[0]}.log"

        # ExecuteResponse mock
        wps_request = MockWpsRequest(process_id=process.id)
        wps_response = type("", (object,), {"_update_status": lambda *_, **__: 1})()

        # depending on debug/command-line & pytest config, captured logs can be 'hijacked' or not, use any active one
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            wps_package_instance._handler(wps_request, wps_response)
        with open(expect_log, mode="r", encoding="utf-8") as file:
            job_log = file.read()
        log_data = f"{stdout.getvalue()}\n{caplog.text}\n{job_log}"

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
            rf"cwltool:job.* \[job {process.id}\].*echo \\\n"
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
        log_err = f"{stderr.getvalue()}\n{caplog.text}"
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
    expect_log = f"{os.path.splitext(wps_package_instance.mock_status_location)[0]}.log"

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
        log_err = f"{stderr.getvalue()}\n{caplog.text}\n{job_err}"
        assert "Package completed with errors." in log_err
        assert "Traceback (most recent call last):" in log_err
        assert "weaver.processes.wps_package|mock-process" in log_err
    else:
        pytest.fail("\"wps_package._handler()\" was expected to throw \"PackageExecutionError\" exception")


def _combine(dict1, dict2):
    # type: (Dict[KT, VT_co], Dict[KT, VT_co]) -> Dict[KT, VT_co]
    dict1 = dict1.copy()
    dict1.update(dict2)
    return dict1


def assert_equal_requirements_any_order(result, expected, diff=False):
    # type: (CWL, CWL, bool) -> None
    for field in ["hints", "requirements"]:  # type: Literal["hints", "requirements"]
        if field in expected:
            if isinstance(expected[field], dict):
                assert result[field] == expected[field]
            else:
                assert_equal_any_order(result[field], expected[field], diff=diff)
        else:
            assert field not in result


@pytest.mark.parametrize("original, expected", [
    (
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"}}},
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                          CWL_REQUIREMENT_CUDA: CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS}},
    ),
    (
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"},
                          CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                          CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"}]},
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                          _combine({"class": CWL_REQUIREMENT_CUDA}, CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS)]},
    ),
    (
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"},
                          _combine({"class": CWL_REQUIREMENT_CUDA},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                          _combine({"class": CWL_REQUIREMENT_CUDA},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    (
        {"hints": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"}}},
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                   CWL_REQUIREMENT_CUDA: CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS}},
    ),
    (
        {"hints": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"},
                   CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                   CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"}]},
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                   _combine({"class": CWL_REQUIREMENT_CUDA}, CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS)]},
    ),
    (
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"},
                   _combine({"class": CWL_REQUIREMENT_CUDA},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                   _combine({"class": CWL_REQUIREMENT_CUDA},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    (
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"}},
         "hints": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}},
         "hints": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"hints": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"}},
         "requirements": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}},
         "requirements": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"}],
         "hints": [_combine({"class": CWL_REQUIREMENT_CUDA},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"}],
         "hints": [_combine({"class": CWL_REQUIREMENT_CUDA},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    (
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"}],
         "requirements": [_combine({"class": CWL_REQUIREMENT_CUDA},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"}],
         "requirements": [_combine({"class": CWL_REQUIREMENT_CUDA},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    # cases that should trigger no change in definition
    (
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}}},
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}}},
    ),
    (
        {"requirements": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaDeviceCountMin": 8}}},
        {"requirements": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaDeviceCountMin": 8}}},
    ),
    (
        {"requirements": [_combine({"class": CWL_REQUIREMENT_CUDA}, {"custom": 1, "cudaDeviceCountMin": 8})]},
        {"requirements": [_combine({"class": CWL_REQUIREMENT_CUDA}, {"custom": 1, "cudaDeviceCountMin": 8})]},
    ),
    (
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}}},
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}}},
    ),
    (
        {"hints": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaDeviceCountMin": 8}}},
        {"hints": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaDeviceCountMin": 8}}},
    ),
    (
        {"hints": [_combine({"class": CWL_REQUIREMENT_CUDA}, {"custom": 1, "cudaDeviceCountMin": 8})]},
        {"hints": [_combine({"class": CWL_REQUIREMENT_CUDA}, {"custom": 1, "cudaDeviceCountMin": 8})]},
    ),
    # cases for CUDA+DockerGPU, using the non-namespaced CUDA requirement, should fix both
    (
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                          CWL_REQUIREMENT_CUDA_NAME: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                          CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                          _combine({"class": CWL_REQUIREMENT_CUDA_NAME},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                          _combine({"class": CWL_REQUIREMENT_CUDA},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    (
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                   CWL_REQUIREMENT_CUDA_NAME: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                   CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                   _combine({"class": CWL_REQUIREMENT_CUDA_NAME},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                   _combine({"class": CWL_REQUIREMENT_CUDA},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    (
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}},
         "hints": {CWL_REQUIREMENT_CUDA_NAME: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}},
         "hints": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}},
         "requirements": {CWL_REQUIREMENT_CUDA_NAME: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}},
         "requirements": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"}],
         "hints": [_combine({"class": CWL_REQUIREMENT_CUDA_NAME},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"}],
         "hints": [_combine({"class": CWL_REQUIREMENT_CUDA},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    (
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"}],
         "requirements": [_combine({"class": CWL_REQUIREMENT_CUDA_NAME},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"}],
         "requirements": [_combine({"class": CWL_REQUIREMENT_CUDA},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    # cases for CUDA+Docker, but using the non-namespaced CUDA requirement, should fix CUDA only
    (
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"},
                          CWL_REQUIREMENT_CUDA_NAME: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                          CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"},
                          _combine({"class": CWL_REQUIREMENT_CUDA_NAME},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                          _combine({"class": CWL_REQUIREMENT_CUDA},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    (
        {"hints": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"},
                   CWL_REQUIREMENT_CUDA_NAME: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"},
                   CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"},
                   _combine({"class": CWL_REQUIREMENT_CUDA_NAME},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"},
                   _combine({"class": CWL_REQUIREMENT_CUDA},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    (
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"}},
         "hints": {CWL_REQUIREMENT_CUDA_NAME: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"requirements": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}},
         "hints": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"hints": {CWL_REQUIREMENT_APP_DOCKER_GPU: {"dockerPull": "python:3.7-alpine"}},
         "requirements": {CWL_REQUIREMENT_CUDA_NAME: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
        {"hints": {CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}},
         "requirements": {CWL_REQUIREMENT_CUDA: {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8}}},
    ),
    (
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"}],
         "hints": [_combine({"class": CWL_REQUIREMENT_CUDA_NAME},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"requirements": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"}],
         "hints": [_combine({"class": CWL_REQUIREMENT_CUDA},
                            {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    (
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER_GPU, "dockerPull": "python:3.7-alpine"}],
         "requirements": [_combine({"class": CWL_REQUIREMENT_CUDA_NAME},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
        {"hints": [{"class": CWL_REQUIREMENT_APP_DOCKER, "dockerPull": "python:3.7-alpine"}],
         "requirements": [_combine({"class": CWL_REQUIREMENT_CUDA},
                                   {"custom": 1, "cudaVersionMin": "11.0", "cudaDeviceCountMin": 8})]},
    ),
    # cases for CUDA-only (no Docker), but using the non-namespaced requirement
    (
        {"requirements": [{"class": CWL_REQUIREMENT_CUDA_NAME}]},
        {"requirements": [{"class": CWL_REQUIREMENT_CUDA}]},
    ),
    (
        {"hints": [{"class": CWL_REQUIREMENT_CUDA_NAME}]},
        {"hints": [{"class": CWL_REQUIREMENT_CUDA}]},
    ),
    (
        {"requirements": [_combine({"class": CWL_REQUIREMENT_CUDA_NAME}, {"custom": 1, "cudaDeviceCountMin": 8})]},
        {"requirements": [_combine({"class": CWL_REQUIREMENT_CUDA}, {"custom": 1, "cudaDeviceCountMin": 8})]},
    ),
    (
        {"hints": [_combine({"class": CWL_REQUIREMENT_CUDA_NAME}, {"custom": 1, "cudaDeviceCountMin": 8})]},
        {"hints": [_combine({"class": CWL_REQUIREMENT_CUDA}, {"custom": 1, "cudaDeviceCountMin": 8})]},
    ),
])
def test_update_package_compatibility(original, expected):
    # type: (CWL, CWL) -> None
    cwl_base = {"cwlVersion": "v1.2", "class": "CommandLineTool"}
    original = _combine(cwl_base, original)
    expected = _combine(cwl_base, expected)
    test_cwl = _update_package_compatibility(original)
    assert_equal_requirements_any_order(test_cwl, expected, diff=True)


def test_cwl_extension_requirements_no_error():
    """
    Validate that specific :term:`CWL` extensions supported by Weaver can be loaded.

    When initialized, the :term:`CWL` factory will validate the document requirement references by resoling against
    the registered definitions to ensure they are all correctly formatted and provide all necessary details.

    By default, only the "base" schemas for the specified ``cwlVersion`` in the :term:`CWL` document are employed.
    Extensions supported by Weaver will raise a validation error.

    This test ensures that known extensions such as :data:`CWL_REQUIREMENT_CUDA` will be resolved without error.
    Unknown or unsupported definitions should however continue raising the validation error.
    """
    cwl = {
        "cwlVersion": "v1.2",
        "class": "CommandLineTool",
        "baseCommand": ["echo", "test"],
        "inputs": {},
        "outputs": {},
        "requirements": {CWL_REQUIREMENT_CUDA: dict(CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS)},
        "$namespaces": dict(CWL_REQUIREMENT_CUDA_NAMESPACE)
    }

    # default behaviour without loading supported extensions should fail validation
    with mock.patch("weaver.processes.wps_package._load_supported_schemas", side_effect=lambda: None):
        # mock caches to ensure that previous tests did not already perform schema registration,
        # making the "unknown" extensions for below test to actually be defined and valid in advance
        with mock.patch.dict("weaver.processes.wps_package.PACKAGE_SCHEMA_CACHE", {}, clear=True):
            with mock.patch.dict("cwltool.process.SCHEMA_CACHE", {}, clear=True):
                cwltool.process.use_standard_schema("v1.2")  # enforce standard CWL without any extension

                with pytest.raises(cwltool.process.ValidationException) as exc_info:
                    _load_package_content(cwl, "test")
                message = str(exc_info.value)
                assert all(
                    info in message for info in [
                        "checking field `requirements`",
                        "Field `class` contains undefined reference to",
                        CWL_REQUIREMENT_CUDA.split(":", 1)[-1],
                    ]
                ), "Validation error should have been caused by missing CWL CUDA extension schema, not something else."

    # no error expected after when supported schema extensions are applied
    # here we reset the caches again to ensure the standard schema are overridden by the custom selection of extensions
    with mock.patch.dict("weaver.processes.wps_package.PACKAGE_SCHEMA_CACHE", {}, clear=True):
        with mock.patch.dict("cwltool.process.SCHEMA_CACHE", {}, clear=True):
            _load_package_content(cwl, "test")

    # even though the extensions are now enabled,
    # validation should allow them only for the relevant versions where they are applicable
    cwl_old = copy.deepcopy(cwl)
    cwl_old["cwlVersion"] = "v1.0"
    cwl_old["requirements"] = {
        # note: 'TimeLimit' (v1.0) renamed to 'ToolTimeLimit' (v1.1 and beyond)
        CWL_REQUIREMENT_TIME_LIMIT: {"timelimit": 10}
    }
    with pytest.raises(cwltool.process.ValidationException) as exc_info:
        _load_package_content(cwl_old, "test")
    message = str(exc_info.value)
    assert all(
        info in message for info in [
            "checking field `requirements`",
            "Field `class` contains undefined reference to",
            CWL_REQUIREMENT_TIME_LIMIT.split(":", 1)[-1],
        ]
    ), "Validation error should have been caused by missing CWL ToolTimeLimit extension schema, not something else."

    # test unsupported schema extension to ensure still disallowed
    cwl["requirements"] = {
        CWL_REQUIREMENT_PROCESS_GENERATOR: {
            "class": "CommandLineTool",
            "run": copy.deepcopy(cwl),
        }
    }
    with pytest.raises(cwltool.process.ValidationException) as exc_info:
        _load_package_content(cwl, "test")
    message = str(exc_info.value)
    assert all(
        info in message for info in [
            "checking field `requirements`",
            "Field `class` contains undefined reference to",
            CWL_REQUIREMENT_PROCESS_GENERATOR,
        ]
    ), "Validation failure should have been caused by unsupported CWL extension schema, not something else."
