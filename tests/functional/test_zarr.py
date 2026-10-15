"""
Zarr-specific functional tests.

Validates that a :term:`Zarr` directory store can be provided as input, produced as output, and chained between
:term:`Workflow` steps (in -> out -> in -> out) while remaining a ``type: Directory`` from the :term:`CWL` perspective.
"""
import contextlib
import copy
import json
import os
import tempfile

import pytest
from pyramid.httpexceptions import HTTPUnprocessableEntity

from tests.functional.test_workflow import WorkflowProcesses, WorkflowTestRunnerBase
from tests.utils import mocked_file_server, mocked_wps_output
from weaver.config import WeaverConfiguration
from weaver.execute import ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import ContentType, is_zarr_media_type
from weaver.wps.utils import map_wps_output_location

ZARR_HOST = "https://mocked-file-server.com"
ZARR_INPUT_NAME = "input.zarr"
ZARR_INPUT_FILES = {
    "zarr.json": json.dumps({"zarr_format": 3, "node_type": "group"}),
    "data/zarr.json": json.dumps({"zarr_format": 3, "node_type": "array"}),
    "data/c/0": "dummy-chunk",
}


@pytest.mark.functional
@pytest.mark.workflow
class ZarrTestCase(WorkflowTestRunnerBase):
    WEAVER_TEST_CONFIGURATION = WeaverConfiguration.HYBRID
    WEAVER_TEST_SERVER_BASE_PATH = ""

    WEAVER_TEST_APPLICATION_SET = {
        WorkflowProcesses.APP_ZARR_COPY,
    }
    WEAVER_TEST_WORKFLOW_SET = {
        WorkflowProcesses.WORKFLOW_ZARR_CHAIN,
    }

    @staticmethod
    def create_dummy_zarr(root_dir):
        # type: (str) -> None
        """
        Generates a minimal dummy :term:`Zarr` directory store in the provided directory.
        """
        for file, content in ZARR_INPUT_FILES.items():
            path = os.path.join(root_dir, ZARR_INPUT_NAME, file)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, mode="w", encoding="utf-8") as f:
                f.write(content)

    def mock_zarr_input(self, tmp_dir):
        def mock_tmp_input(requests_mock):
            mocked_file_server(
                tmp_dir, ZARR_HOST, self.settings,
                requests_mock=requests_mock,
                mock_head=True,
                mock_get=True,
                mock_browse_index=True,
            )
            mocked_wps_output(
                self.settings,
                requests_mock=requests_mock,
                mock_head=True,
                mock_get=True,
                mock_browse_index=True,
            )
        return mock_tmp_input

    def assert_zarr_output(self, result):
        """
        Validates that the output is a :term:`Zarr` directory that preserved the input data.
        """
        assert "zarr_out" in result
        output = result["zarr_out"]
        assert output["href"].endswith("/zarr_out/copy.zarr/"), "Zarr directory name should be preserved"
        assert is_zarr_media_type(output.get("type")), "Zarr output media-type should be reported"
        output_path = map_wps_output_location(output["href"], container=self.settings)
        assert os.path.isdir(output_path)
        for file, content in ZARR_INPUT_FILES.items():
            file_path = os.path.join(output_path, file)
            assert os.path.isfile(file_path), f"Zarr content '{file}' should be preserved in output"
            with open(file_path, mode="r", encoding="utf-8") as f:
                assert f.read() == content

    def test_deploy_zarr_with_cwl_file_type_error(self):
        """
        Zarr is a directory store, therefore a CWL ``File`` declaring a Zarr format must be refused at deployment.
        """
        for io_name in ["zarr_in", "zarr_out"]:
            proc_info = self.test_processes_info[WorkflowProcesses.APP_ZARR_COPY]
            body = copy.deepcopy(proc_info.deploy_payload)
            cwl_io_section = "inputs" if io_name == "zarr_in" else "outputs"
            body["executionUnit"][0]["unit"][cwl_io_section][io_name]["type"] = "File"
            resp = self.request("POST", "/processes", headers=self.headers, json=body,
                                status=HTTPUnprocessableEntity.code, ignore_errors=True)
            assert "Directory" in json.dumps(resp.json), f"Error should indicate expected type for '{io_name}'"

    def test_zarr_in_zarr_out_process(self):
        """
        Executes a single process that receives a Zarr directory and produces a Zarr directory.
        """
        with contextlib.ExitStack() as stack:
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            self.create_dummy_zarr(tmp_dir)
            exec_body = {
                "inputs": {
                    "zarr_in": {"href": f"{ZARR_HOST}/{ZARR_INPUT_NAME}/", "type": ContentType.APP_ZARR_V3},
                },
                "outputs": {"zarr_out": {"transmissionMode": ExecuteTransmissionMode.REFERENCE}},
                "response": ExecuteResponse.DOCUMENT,
            }
            proc_info = self.prepare_process(WorkflowProcesses.APP_ZARR_COPY)
            result = self.execute_monitor_process(
                proc_info,
                override_execute_body=exec_body,
                requests_mock_callback=self.mock_zarr_input(tmp_dir),
                detailed_results=False,
            )
            self.assert_zarr_output(result)

    def test_workflow_zarr_chain(self):
        """
        Executes a Workflow chaining Zarr directories as in -> out -> in -> out between two steps.

        Each step copies its Zarr input, so the final output matching the original validates that the Zarr produced
        by the first step was properly staged as the Zarr input of the second step.
        """
        with contextlib.ExitStack() as stack:
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            self.create_dummy_zarr(tmp_dir)
            exec_body = {
                "inputs": {
                    "zarr_in": {"href": f"{ZARR_HOST}/{ZARR_INPUT_NAME}/", "type": ContentType.APP_ZARR_V3},
                },
                "outputs": {"zarr_out": {"transmissionMode": ExecuteTransmissionMode.REFERENCE}},
                "response": ExecuteResponse.DOCUMENT,
            }
            result = self.workflow_runner(
                WorkflowProcesses.WORKFLOW_ZARR_CHAIN,
                [WorkflowProcesses.APP_ZARR_COPY],
                override_execute_body=exec_body,
                log_full_trace=True,
                requests_mock_callback=self.mock_zarr_input(tmp_dir),
            )
            self.assert_zarr_output(result)
