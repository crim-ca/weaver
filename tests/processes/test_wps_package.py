"""
Unit tests of functions within :mod:`weaver.processes.wps_package`.

.. seealso::
    - :mod:`tests.functional.wps_package`.
"""
import contextlib
import copy
import io
import itertools
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import warnings
from typing import TYPE_CHECKING

import cwltool.process
import mock
import pytest
from _pytest.outcomes import Failed
from cwltool.errors import WorkflowException
from cwltool.factory import Factory as CWLFactory
from pywps.inout.formats import Format
from pywps.inout.outputs import ComplexOutput
from pywps.validator.mode import MODE

from tests.utils import assert_equal_any_order
from weaver.datatype import Process
from weaver.exceptions import PackageExecutionError, PackageTypeError
from weaver.formats import ContentType
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_DOCKER_GPU,
    CWL_REQUIREMENT_CUDA,
    CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS,
    CWL_REQUIREMENT_CUDA_NAMESPACE,
    CWL_REQUIREMENT_PROCESS_GENERATOR,
    CWL_REQUIREMENT_SECRETS,
    CWL_REQUIREMENT_TIME_LIMIT
)
from weaver.processes.wps_package import (
    WpsPackage,
    _load_package_content,
    _update_package_compatibility,
    _update_package_metadata,
    format_extension_validator,
    get_application_requirement,
    mask_process_inputs
)
from weaver.wps.service import WorkerRequest

if TYPE_CHECKING:
    from typing import Any, Dict, TypeVar

    KT = TypeVar("KT")
    VT_co = TypeVar("VT_co", covariant=True)

    from weaver.typedefs import CWL

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


def assert_equal_requirements_any_order(result, expected):
    for field in ["hints", "requirements"]:
        if field in expected:
            if isinstance(expected[field], dict):
                assert result[field] == expected[field]
            else:
                assert_equal_any_order(result[field], expected[field])
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
    )
])
def test_update_package_compatibility(original, expected):
    # type: (CWL, CWL) -> None
    cwl_base = {"cwlVersion": "v1.2", "class": "CommandLineTool"}  # type: CWL
    original = _combine(cwl_base, original)
    expected = _combine(cwl_base, expected)
    test_cwl = _update_package_compatibility(original)
    assert_equal_requirements_any_order(test_cwl, expected)


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
    }  # type: CWL

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
                valid_msg = [
                    "checking field `requirements`",
                    "Field `class` contains undefined reference to",
                    CWL_REQUIREMENT_CUDA.split(":", 1)[-1],
                ]
                assert all(any(msg in message for msg in [info, info.replace("`", "'")]) for info in valid_msg), (
                    "Validation error should have been caused by missing CWL CUDA extension schema. "
                    f"Error message must contain all following items: {valid_msg}. "
                    f"Some items were missing in: \n{message}"
                )

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
    valid_msg = [
        "checking field `requirements`",
        "Field `class` contains undefined reference to",
        CWL_REQUIREMENT_TIME_LIMIT.split(":", 1)[-1],
    ]
    assert all(any(msg in message for msg in [info, info.replace("`", "'")]) for info in valid_msg), (
        "Validation error should have been caused by missing CWL ToolTimeLimit extension schema. "
        f"Error message must contain all following items: {valid_msg}. "
        f"Some items were missing in: \n{message}"
    )

    # test unsupported schema extension to ensure still disallowed
    cwl["requirements"] = {  # type: ignore  # purposely invalid/unsupported type
        CWL_REQUIREMENT_PROCESS_GENERATOR: {
            "class": "CommandLineTool",
            "run": copy.deepcopy(cwl),
        }
    }
    with pytest.raises(cwltool.process.ValidationException) as exc_info:
        _load_package_content(cwl, "test")
    message = str(exc_info.value)
    valid_msg = [
        "checking field `requirements`",
        "Field `class` contains undefined reference to",
        CWL_REQUIREMENT_PROCESS_GENERATOR,
    ]
    assert all(any(msg in message for msg in [info, info.replace("`", "'")]) for info in valid_msg), (
        "Validation failure should have been caused by an unsupported CWL extension schema. "
        f"Error message must contain all following items: {valid_msg}. "
        f"Some items were missing in: \n{message}"
    )


@pytest.mark.parametrize(
    "cwl",
    [
        {"requirements": {"custom": {}}},
        {"requirements": {"custom": {}, "DockerRequirement": {"dockerPull": "debian:latest"}}},
        {"hints": {"custom": {}}, "requirements": {"DockerRequirement": {"dockerPull": "debian:latest"}}},
    ]
)
def test_get_application_requirement_hints_supported(cwl):
    # type: (CWL) -> None
    """
    Ensure that unknown :term:`CWL` requirements or hints are raised.

    Although ``hints`` are considered optional from typical :term:`CWL` specification, they could be employed in
    an :term:`Application Package` definition, and produce valid operations to be applied when the :term:`CWL`
    execution is handed of to :mod:`cwltool`. To ensure no undesired side-effects occur this way, our ``hints``
    are handled more strictly as if they were ``requirements``.

    .. seealso::
        :data:`weaver.processes.constants.CWL_REQUIREMENTS_SUPPORTED`
    """
    with pytest.raises(PackageTypeError):
        get_application_requirement(cwl, validate=True, required=True)


def test_cwl_enum_schema_name_patched():
    """
    Ensure that :term:`CWL` ``Enum`` contains a ``name`` to avoid false-positive conflicting schemas.

    When an ``Enum`` is reused multiple times to define an I/O, omitting the ``name`` makes the duplicate definition
    to be considered a conflict, since :mod:`cwltool` will automatically apply an auto-generated ``name`` for that
    schema.

    .. seealso::
        - https://github.com/common-workflow-language/cwltool/issues/1908
        - :meth:`weaver.processes.wps_package.WpsPackage.update_cwl_schema_names`
    """
    test_symbols = [str(i) for i in range(100)]
    cwl_input_without_name = {
        "type": [
            "null",
            {
                "type": "enum",
                "symbols": test_symbols,
            },
            {
                "type": "array",
                "items": {
                    "type": "enum",
                    "symbols": test_symbols,
                },
            },
        ]
    }
    cwl_without_name = {
        "cwlVersion": "v1.2",
        "class": "CommandLineTool",
        "baseCommand": "echo",
        "requirements": {
            CWL_REQUIREMENT_APP_DOCKER: {
                "dockerPull": "debian:latest",
            }
        },
        "inputs": {
            "test": cwl_input_without_name,
        },
        "outputs": {
            "output": {"type": "stdout"},
        }
    }  # type: CWL

    factory = CWLFactory()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as tmp_file:
        json.dump(cwl_without_name, tmp_file)
        tmp_file.flush()
        try:
            with pytest.raises(WorkflowException):
                tool = factory.make(f"file://{tmp_file.name}")
                tool(test=test_symbols[0])
        except Failed:
            # WARNING:
            #   CWL tool schema-salad validator seems to inconsistently raise in some situations and not others (?)
            #   (see https://github.com/common-workflow-language/cwltool/issues/1908)
            #   Ignore if it raises since it is not breaking for our test and implementation.
            warnings.warn("CWL nested enums without 'name' did not raise, but not breaking...")

    # our implementation that eventually gets called goes through 'update_cwl_schema_names', that one MUST NOT raise
    pkg = WpsPackage(package=cwl_without_name, identifier="test", title="test")
    pkg.update_cwl_schema_names()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as tmp_file:
        json.dump(pkg.package, tmp_file)
        tmp_file.flush()
        tool = factory.make(f"file://{tmp_file.name}")
        tool(test=None)
        tool(test=test_symbols[0])
        tool(test=[test_symbols[0]])


@pytest.mark.parametrize(
    ["inputs", "expect"],
    [
        (
            [{"id": "normal", "value": "ok to show"}, {"id": "hidden", "value": "value to mask"}],
            [{"id": "normal", "value": "ok to show"}, {"id": "hidden", "value": "(secret)"}],
        ),
        (
            {"normal": {"value": "ok to show"}, "hidden": {"value": "value to mask"}},
            {"normal": {"value": "ok to show"}, "hidden": {"value": "(secret)"}},
        ),
        (
            {"normal": "ok to show", "hidden": "value to mask"},
            {"normal": "ok to show", "hidden": "(secret)"},
        ),
    ]
)
def test_mask_process_inputs(inputs, expect):
    cwl = {
        "cwlVersion": "v1.2",
        "class": "CommandLineTool",
        "inputs": {
            "normal": {"type": "string"},
            "hidden": {"type": "string"},
        },
        "outputs": {},
        "requirements": {
            CWL_REQUIREMENT_APP_DOCKER: {
                "dockerPull": "debian:latest",
            }
        },
        "hints": {
            CWL_REQUIREMENT_SECRETS: {
                "secrets": ["hidden"],
            }
        }
    }  # type: CWL
    with mock.patch("cwltool.secrets.SecretStore.add", return_value="(secret)"):  # avoid unique UUID for each
        result = mask_process_inputs(cwl, inputs)
    assert result == expect, "expected inputs should have been masked"
    assert inputs != expect, "original inputs should not be modified"


@pytest.mark.parametrize(
    ["data_input", "mode", "expect"],
    [
        (*params, False) for params in itertools.product(
            [object()],
            [MODE.SIMPLE, MODE.STRICT, MODE.VERYSTRICT],
        )
    ] +
    [
        (*params, True) for params in itertools.product(
            [ComplexOutput("test", "test")],
            [MODE.NONE, MODE.SIMPLE, MODE.STRICT, MODE.VERYSTRICT],
        )
    ] + [
        (ComplexOutput("test", "test", [Format(ContentType.APP_JSON)], mode=MODE.NONE), MODE.NONE, True),
    ]
)
def test_format_extension_validator_basic(data_input, mode, expect):
    # type: (Any, int, bool) -> None
    assert format_extension_validator(data_input, mode) == expect


@pytest.mark.parametrize("original, expected", [
    (
        # Test author metadata with empty wps_package
        {
            "cwl_package_package": {
                "s:author": [
                    {"class": "s:Person", "s:name": "John Doe", "s:affiliation": "Example Inc."}
                ],
            },
            "wps_package_metadata": {}
        },
        {
            "abstract": "",
            "title": "",
            "version": "",
            "metadata": [
                {
                    "role": "author",
                    "value": {
                        "$schema": "https://schema.org/Person",
                        "name": "John Doe",
                        "affiliation": "Example Inc."
                    }
                }
            ]
        }
    ),
    (
        # Test codeRepository
        {
            "cwl_package_package": {
                "s:codeRepository": "https://gitlab.com/",
            },
            "wps_package_metadata": {}
        },
        {
            "abstract": "",
            "title": "",
            "version": "",
            "metadata": [
                {
                    "type": "text/html",
                    "rel": "codeRepository",
                    "href": "https://gitlab.com/"
                }
            ]
        }
    ),
    (
        # Test Version with existing metadata
        {
            "cwl_package_package": {
                "s:version": "1.0"
            },
            "wps_package_metadata": {
                "metadata": [
                    {
                        "type": "text/html",
                        "rel": "codeRepository",
                        "href": "https://gitlab.com/"
                    }
                ]
            }
        },
        {
            "abstract": "",
            "title": "",
            "metadata": [
                {
                    "type": "text/html",
                    "rel": "codeRepository",
                    "href": "https://gitlab.com/"
                },
            ],
            "version": "1.0"
        }
    ),
    (
        # Test softwareVersion
        {
            "cwl_package_package": {
                "s:softwareVersion": "1.0.0"
            },
            "wps_package_metadata": {}
        },
        {
            "abstract": "",
            "title": "",
            "version": "1.0.0"
        }
    ),
])
def test_process_metadata(original, expected):
    # type: (CWL, CWL) -> None
    cwl_package_package = original["cwl_package_package"]
    wps_package_metadata = original["wps_package_metadata"]
    _update_package_metadata(wps_package_metadata, cwl_package_package)
    # Assertions
    assert wps_package_metadata == expected
