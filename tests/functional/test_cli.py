"""
Functional tests for :mod:`weaver.cli`.
"""

import contextlib
import copy
import json
import os
import shutil
import tempfile
import uuid
from typing import TYPE_CHECKING

import pytest
import yaml

from tests.functional import APP_PKG_ROOT
from tests.functional.utils import WpsConfigBase
from tests.utils import (
    get_weaver_url,
    mocked_dismiss_process,
    mocked_execute_process,
    mocked_sub_requests,
    mocked_wps_output,
    run_command
)
from weaver.cli import WeaverClient, main as weaver_cli
from weaver.formats import CONTENT_TYPE_TEXT_PLAIN
from weaver.status import STATUS_ACCEPTED, STATUS_FAILED, STATUS_RUNNING, STATUS_SUCCEEDED
from weaver.wps.utils import map_wps_output_location

if TYPE_CHECKING:
    from typing import Dict


@pytest.mark.cli
@pytest.mark.functional
class TestWeaverClientBase(WpsConfigBase):
    def __init__(self, *args, **kwargs):
        # won't run this as a test suite, only its derived classes
        setattr(self, "__test__", self is TestWeaverClientBase)
        super(TestWeaverClientBase, self).__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        cls.settings.update({
            "weaver.wps_output_dir": tempfile.mkdtemp(prefix="weaver-test-"),
            "weaver.wps_output_url": "http://random-file-server.com/wps-outputs"
        })
        super(TestWeaverClientBase, cls).setUpClass()
        cls.url = get_weaver_url(cls.app.app.registry)
        cls.client = WeaverClient(cls.url)

        cls.test_process_prefix = "test-client"

    def setUp(self):
        processes = self.process_store.list_processes()
        test_processes = filter(lambda _proc: _proc.id.startswith(self.test_process_prefix), processes)
        for proc in test_processes:
            self.process_store.delete_process(proc.id)

        # make one process available for testing features
        self.test_process = {}
        self.test_payload = {}
        for process in ["Echo", "CatFile"]:
            self.test_process[process] = f"{self.test_process_prefix}-{process}"
            self.test_payload[process] = self.load_resource_file(f"DeployProcess_{process}.yml", process)
            self.deploy_process(self.test_payload[process], process_id=self.test_process[process])

    @classmethod
    def tearDownClass(cls):
        super(TestWeaverClientBase, cls).tearDownClass()
        tmp_wps_out = cls.settings.get("weaver.wps_output_dir", "")
        if os.path.isdir(tmp_wps_out):
            shutil.rmtree(tmp_wps_out, ignore_errors=True)

    @staticmethod
    def get_resource_file(name, process="Echo"):
        if os.path.isfile(name):
            return os.path.abspath(name)
        return os.path.join(APP_PKG_ROOT, process, name)

    @classmethod
    def load_resource_file(cls, name, process="Echo"):
        with open(TestWeaverClientBase.get_resource_file(name, process)) as res_file:
            return yaml.safe_load(res_file)


class TestWeaverClient(TestWeaverClientBase):
    @classmethod
    def setUpClass(cls):
        super(TestWeaverClient, cls).setUpClass()
        cls.test_tmp_dir = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        super(TestWeaverClient, cls).tearDownClass()
        shutil.rmtree(cls.test_tmp_dir, ignore_errors=True)

    def setup_test_file(self, original_file, substitutions):
        # type: (str, Dict[str, str]) -> str
        path = os.path.join(self.test_tmp_dir, str(uuid.uuid4()))
        os.makedirs(path, exist_ok=True)
        test_file_path = os.path.join(path, os.path.split(original_file)[-1])
        with open(original_file, "r") as real_file:
            data = real_file.read()
            for sub, new in substitutions.items():
                data = data.replace(sub, new)
        with open(test_file_path, "w") as test_file:
            test_file.write(data)
        return test_file_path

    def process_listing_op(self, operation):
        result = mocked_sub_requests(self.app, operation)
        assert result.success
        assert "processes" in result.body
        assert set(result.body["processes"]) == {
            # builtin
            "file2string_array",
            "file_index_selector",
            "jsonarray2netcdf",
            "metalink2netcdf",
            # test process
            self.test_process["CatFile"],
            self.test_process["Echo"],
        }
        assert "undefined" not in result.message

    def test_capabilities(self):
        self.process_listing_op(self.client.capabilities)

    def test_processes(self):
        self.process_listing_op(self.client.processes)

    def test_deploy_payload_body_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}-deploy-body-no-cwl"
        payload = self.load_resource_file("DeployProcess_Echo.yml")
        package = self.load_resource_file("echo.cwl")
        payload["executionUnit"][0] = {"unit": package}

        result = mocked_sub_requests(self.app, self.client.deploy, test_id, payload)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_payload_file_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}-deploy-file-no-cwl"
        payload = self.load_resource_file("DeployProcess_Echo.yml")
        package = self.get_resource_file("echo.cwl")
        payload["executionUnit"][0] = {"href": package}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cwl") as body_file:
            json.dump(payload, body_file)
            body_file.flush()
            body_file.seek(0)
            result = mocked_sub_requests(self.app, self.client.deploy, test_id, body_file.name)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_payload_inject_cwl_body(self):
        test_id = f"{self.test_process_prefix}-deploy-body-with-cwl-body"
        payload = self.load_resource_file("DeployProcess_Echo.yml")
        package = self.load_resource_file("echo.cwl")
        payload.pop("executionUnit", None)

        result = mocked_sub_requests(self.app, self.client.deploy, test_id, payload, package)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_payload_inject_cwl_file(self):
        test_id = f"{self.test_process_prefix}-deploy-body-with-cwl-file"
        payload = self.load_resource_file("DeployProcess_Echo.yml")
        package = self.get_resource_file("echo.cwl")
        payload.pop("executionUnit", None)

        result = mocked_sub_requests(self.app, self.client.deploy, test_id, payload, package)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_with_undeploy(self):
        test_id = f"{self.test_process_prefix}-deploy-undeploy-flag"
        result = mocked_sub_requests(self.app, self.client.deploy, test_id, self.test_payload)
        assert result.success
        result = mocked_sub_requests(self.app, self.client.deploy, test_id, self.test_payload, undeploy=True)
        assert result.success
        assert "undefined" not in result.message

    def test_undeploy(self):
        # deploy a new process to leave the test one available
        other_payload = copy.deepcopy(self.test_payload)
        other_process = self.test_process["Echo"] + "-other"
        self.deploy_process(other_payload, process_id=other_process)

        result = mocked_sub_requests(self.app, self.client.undeploy, other_process)
        assert result.success
        assert result.body.get("undeploymentDone", None) is True
        assert "undefined" not in result.message

        path = f"/processes/{other_process}"
        resp = mocked_sub_requests(self.app, "get", path, expect_errors=True)
        assert resp.status_code == 404

    def test_describe(self):
        result = mocked_sub_requests(self.app, self.client.describe, self.test_process["Echo"])
        assert result.success
        # see deployment file for details that are expected here
        assert result.body["id"] == self.test_process["Echo"]
        assert result.body["version"] == "1.0"
        assert result.body["keywords"] == ["test", "application"]  # app is added by Weaver since not CWL Workflow
        assert "message" in result.body["inputs"]
        assert result.body["inputs"]["message"]["title"] == "message"
        assert result.body["inputs"]["message"]["description"] == "Message to echo."
        assert result.body["inputs"]["message"]["minOccurs"] == 1
        assert result.body["inputs"]["message"]["maxOccurs"] == 1
        assert result.body["inputs"]["message"]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert "output" in result.body["outputs"]
        assert result.body["outputs"]["output"]["title"] == "output"
        assert result.body["outputs"]["output"]["description"] == "Output file with echo message."
        assert result.body["outputs"]["output"]["formats"] == [{"default": True, "mediaType": CONTENT_TYPE_TEXT_PLAIN}]
        assert "undefined" not in result.message, "CLI should not have confused process description as response detail."
        assert "description" not in result.body, "CLI should not have overridden the process description field."

    def run_execute_inputs_schema_variant(self, inputs_param, process="Echo",
                                          preload=False, expect_success=True, mock_exec=True):
        if isinstance(inputs_param, str):
            if preload:
                inputs_param = self.load_resource_file(inputs_param, process=process)
            else:
                inputs_param = self.get_resource_file(inputs_param, process=process)
        with contextlib.ExitStack() as stack_exec:
            # use pass-through function because don't care about execution result here, only the parsing of I/O
            if mock_exec:
                mock_exec_func = lambda *_, **__: None  # noqa
            else:
                mock_exec_func = None
            for mock_exec_proc in mocked_execute_process(func_execute_process=mock_exec_func):
                stack_exec.enter_context(mock_exec_proc)
            result = mocked_sub_requests(self.app, self.client.execute, self.test_process[process], inputs=inputs_param)
        if expect_success:
            assert result.success, result.text
            assert "jobID" in result.body
            assert "processID" in result.body
            assert "status" in result.body
            assert "location" in result.body
            assert result.body["processID"] == self.test_process[process]
            assert result.body["status"] == STATUS_ACCEPTED
            assert result.body["location"] == result.headers["Location"]
            assert "undefined" not in result.message
        else:
            assert not result.success, result.text
        return result

    def test_execute_inputs_cwl_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml", preload=False)

    def test_execute_inputs_ogc_value_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_value_schema.yml", preload=False)

    def test_execute_inputs_ogc_mapping_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_mapping_schema.yml", preload=False)

    def test_execute_inputs_old_listing_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_old_listing_schema.yml", preload=False)

    def test_execute_inputs_cwl_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml", preload=True)

    def test_execute_inputs_ogc_value_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_value_schema.yml", preload=True)

    def test_execute_inputs_ogc_mapping_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_mapping_schema.yml", preload=True)

    def test_execute_inputs_old_listing_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_old_listing_schema.yml", preload=True)

    def test_execute_inputs_representation_literal_schema(self):
        self.run_execute_inputs_schema_variant(["message='hello world'"], preload=True)

    def test_execute_inputs_invalid(self):
        """
        Mostly check that errors don't raise an error in the client, but are handled and gracefully return a result.
        """
        for invalid_inputs_schema in [
            [1, 2, 3, 4],  # missing the ID
            [{"id": "message"}],  # missing the value
            {}  # valid schema, but missing inputs of process
        ]:
            self.run_execute_inputs_schema_variant(invalid_inputs_schema, expect_success=False)

    def test_execute_manual_monitor_status_and_download_results(self):
        """
        Test a typical case of :term:`Job` execution, result retrieval and download, but with manual monitoring.

        Manual monitoring can be valid in cases where a *very* long :term:`Job` must be executed, and the user does
        not intend to wait after it. This avoids leaving some shell/notebook/etc. open of a long time and provide a
        massive ``timeout`` value. Instead, the user can simply re-call :meth:`WeaverClient.monitor` at a later time
        to resume monitoring. Other situation can be if the connection was dropped or script runner crashed, and the
        want to pick up monitoring again.

        .. note::
            The :meth:`WeaverClient.execute` is accomplished synchronously during this test because of the mock.
            The :meth:`WeaverClient.monitor` step can therefore only return ``success``/``failed`` directly
            without any intermediate and asynchronous pooling of ``running`` status.
            The first status result from  :meth:`WeaverClient.execute` is ``accept`` because this is the
            default status that is generated by the HTTP response from the :term:`Job` creation.
            Any following GET status will directly return the final :term:`Job` result.
        """
        result = self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml", mock_exec=False)
        job_id = result.body["jobID"]
        result = mocked_sub_requests(self.app, self.client.monitor, job_id, timeout=1, interval=1)
        assert result.success, result.text
        assert "undefined" not in result.message
        assert result.body.get("status") == STATUS_SUCCEEDED
        links = result.body.get("links")
        assert isinstance(links, list)
        assert len(list(filter(lambda _link: _link["rel"].endswith("results"), links))) == 1

        # first test to get job results details, but not downloading yet
        result = mocked_sub_requests(self.app, self.client.results, job_id)
        assert result.success, result.text
        assert "undefined" not in result.message
        outputs_body = result.body
        assert isinstance(outputs_body, dict) and len(outputs_body) == 1
        output = outputs_body.get("output")  # single of this process
        assert isinstance(output, dict) and "href" in output, "Output named 'output' should be a 'File' reference."
        output_href = output.get("href")
        assert isinstance(output_href, str) and output_href.startswith(self.settings["weaver.wps_output_url"])

        # test download feature
        with contextlib.ExitStack() as stack:
            server_mock = stack.enter_context(mocked_wps_output(self.settings))
            target_dir = stack.enter_context(tempfile.TemporaryDirectory())
            result = mocked_sub_requests(self.app, self.client.results,
                                         job_id, download=True, out_dir=target_dir,  # 'client.results' parameters
                                         only_local=True)  # mock parameter (avoid download HTTP redirect to TestApp)
            assert result.success, result.text
            assert "undefined" not in result.message
            assert result.body != outputs_body, "Download operation should modify the original outputs body."
            output = result.body.get("output", {})
            assert output.get("href") == output_href
            output_path = output.get("path")  # inserted by download
            assert isinstance(output_path, str) and output_path.startswith(target_dir)
            output_name = output_href.split(job_id)[-1][1:]  # everything after jobID, and without the first '/'
            output_file = os.path.join(target_dir, output_name)
            assert output_path == output_file
            assert os.path.isfile(output_file) and not os.path.islink(output_file)
            assert len(server_mock.calls) == 1  # list of (PreparedRequest, Response)
            assert server_mock.calls[0][0].url == output_href

    @pytest.mark.xfail(reason="not implemented")
    def test_execute_with_auto_monitor(self):
        """
        Test case where monitoring is accomplished automatically and inline to the execution before result download.
        """
        # FIXME: Properly test execute+monitor,
        #   Need an actual (longer) async call because 'mocked_execute_process' blocks until complete.
        #   Therefore, no pooling monitoring actually occurs (only single get status with final result).
        #   Test should wrap 'get_job' in 'get_job_status' view (or similar wrapping approach) to validate that
        #   status was periodically pooled and returned 'running' until the final 'succeeded' resumes to download.
        raise NotImplementedError

    # NOTE:
    #   For all below '<>_auto_resolve_vault' test cases, the local file referenced in the Execute request body
    #   should be automatically handled by uploading to the Vault and forwarding the relevant X-Auth-Vault header.
    def run_execute_inputs_with_vault_file(self, test_input_file, process="CatFile", preload=False, embed=False):
        test_data = "DUMMY DATA"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as tmp_file:
            tmp_file.write(test_data)
            tmp_file.flush()
            tmp_file.seek(0)
            if embed:
                test_file = [test_input_file.format(test_file=tmp_file.name)]
            else:
                exec_file = self.get_resource_file(test_input_file, process=process)
                test_file = self.setup_test_file(exec_file, {"<TEST_FILE>": tmp_file.name})
            result = self.run_execute_inputs_schema_variant(test_file, process=process,
                                                            preload=preload, mock_exec=False)
        job_id = result.body["jobID"]
        result = mocked_sub_requests(self.app, self.client.results, job_id)
        assert result.success, result.message
        output = result.body["output"]["href"]
        output = map_wps_output_location(output, self.settings, exists=True)
        assert os.path.isfile(output)
        with open(output, "r") as out_file:
            out_data = out_file.read()
        assert out_data == test_data

    @pytest.mark.vault
    def test_execute_inputs_cwl_file_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_cwl_schema.yml", "CatFile", preload=False)

    @pytest.mark.vault
    def test_execute_inputs_ogc_mapping_file_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_ogc_mapping_schema.yml", "CatFile", preload=False)

    @pytest.mark.vault
    def test_execute_inputs_old_listing_file_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_old_listing_schema.yml", "CatFile", preload=False)

    @pytest.mark.vault
    def test_execute_inputs_cwl_literal_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_cwl_schema.yml", "CatFile", preload=True)

    @pytest.mark.vault
    def test_execute_inputs_ogc_mapping_literal_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_ogc_mapping_schema.yml", "CatFile", preload=True)

    @pytest.mark.vault
    def test_execute_inputs_old_listing_literal_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_old_listing_schema.yml", "CatFile", preload=True)

    @pytest.mark.vault
    def test_execute_inputs_representation_literal_schema_auto_resolve_vault(self):
        # 1st 'file' is the name of the process input
        # 2nd 'file' is the type (CWL) to ensure proper detection/conversion to href URL
        # 'test_file' will be replaced by the actual temp file instantiated with dummy data
        input_data = "file:file='{test_file}'"
        self.run_execute_inputs_with_vault_file(input_data, "CatFile", preload=False, embed=True)

    @mocked_dismiss_process()
    def test_dismiss(self):
        for status in [STATUS_ACCEPTED, STATUS_FAILED, STATUS_RUNNING, STATUS_SUCCEEDED]:
            proc = self.test_process["Echo"]
            job = self.job_store.save_job(task_id="12345678-1111-2222-3333-111122223333", process=proc)
            job.status = status
            job = self.job_store.update_job(job)
            result = mocked_sub_requests(self.app, self.client.dismiss, str(job.id))
            assert result.success
            assert "undefined" not in result.message


class TestWeaverCLI(TestWeaverClientBase):
    def test_help_operations(self):
        lines = run_command(
            [
                "weaver",
                "--help",
            ],
            trim=False,
        )
        operations = [
            "deploy",
            "undeploy",
            "capabilities",
            "processes",
            "describe",
            "execute",
            "monitor",
            "dismiss",
            "results",
            "status",
        ]
        assert all(any(op in line for line in lines) for op in operations)

    def test_log_options_any_level(self):
        """
        Logging parameters should be allowed at main parser level or under any operation subparser.
        """
        proc = self.test_process["Echo"]
        for options in [
            ["--verbose", "describe", self.url, "-p", proc],
            ["describe", self.url, "--verbose", "-p", proc],
            ["describe", self.url, "-p", proc, "--verbose"],
        ]:
            lines = mocked_sub_requests(
                self.app, run_command,
                options,
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"id\": \"{proc}\"" in line for line in lines)

    def test_deploy_no_process_id_option(self):
        payload = self.get_resource_file("DeployProcess_Echo.yml")
        package = self.get_resource_file("echo.cwl")
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "--body", payload,  # no --process/--id, but available through --body
                "--cwl", package,
                self.url
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any("\"id\": \"Echo\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_body_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}-deploy-body-no-cwl"
        payload = self.load_resource_file("DeployProcess_Echo.yml")
        package = self.load_resource_file("echo.cwl")
        payload["executionUnit"][0] = {"unit": package}

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-p", test_id,
                "-b", json.dumps(payload),  # literal JSON string accepted for CLI
                self.url
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_file_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}-deploy-file-no-cwl"
        payload = self.load_resource_file("DeployProcess_Echo.yml")
        package = self.get_resource_file("echo.cwl")
        payload["executionUnit"][0] = {"href": package}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cwl") as body_file:
            json.dump(payload, body_file)
            body_file.flush()
            body_file.seek(0)

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # weaver
                    "deploy",
                    "-p", test_id,
                    "-b", body_file.name,
                    self.url
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
            assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_inject_cwl_body(self):
        test_id = f"{self.test_process_prefix}-deploy-body-with-cwl-body"
        payload = self.load_resource_file("DeployProcess_Echo.yml")
        package = self.load_resource_file("echo.cwl")
        payload.pop("executionUnit", None)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-p", test_id,
                "--body", json.dumps(payload),  # literal JSON string accepted for CLI
                "--cwl", json.dumps(package),   # literal JSON string accepted for CLI
                self.url
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_inject_cwl_file(self):
        test_id = f"{self.test_process_prefix}-deploy-body-with-cwl-file"
        payload = self.load_resource_file("DeployProcess_Echo.yml")
        package = self.get_resource_file("echo.cwl")
        payload.pop("executionUnit", None)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-p", test_id,
                "--body", json.dumps(payload),  # literal JSON string accepted for CLI
                "--cwl", package,
                self.url
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_describe(self):
        # prints formatted JSON ProcessDescription over many lines
        proc = self.test_process["Echo"]
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "describe",
                self.url,
                "-p", proc,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        # ignore indents of fields from formatted JSON content
        assert any(f"\"id\": \"{proc}\"" in line for line in lines)
        assert any("\"inputs\": {" in line for line in lines)
        assert any("\"outputs\": {" in line for line in lines)

    def test_execute_inputs_capture(self):
        """
        Verify that specified inputs are captured for a limited number of 1 item per ``-I`` option.
        """
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_process():
                stack_exec.enter_context(mock_exec_proc)
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    "-p", proc,
                    "-I", "message='TEST MESSAGE!'",  # if -I not capture as indented, URL after would be combined in it
                    self.url,
                    "-M",
                    "-T", 10,
                    "-W", 1,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"status\": \"{STATUS_SUCCEEDED}\"" in line for line in lines)

    def test_execute_manual_monitor(self):
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_process():
                stack_exec.enter_context(mock_exec_proc)

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    self.url,
                    "-p", proc,
                    "-I", "message='TEST MESSAGE!'"
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            # ignore indents of fields from formatted JSON content
            assert any(f"\"processID\": \"{proc}\"" in line for line in lines)
            assert any("\"jobID\": \"" in line for line in lines)
            assert any("\"location\": \"" in line for line in lines)
            job_loc = [line for line in lines if "location" in line][0]
            job_ref = [line for line in job_loc.split("\"") if line][-1]
            job_id = job_ref.split("/")[-1]

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "monitor",
                    "-j", job_ref,
                    "-T", 10,
                    "-W", 1,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )

            assert any(f"\"jobID\": \"{job_id}\"" in line for line in lines)
            assert any(f"\"status\": \"{STATUS_SUCCEEDED}\"" in line for line in lines)
            assert any(f"\"href\": \"{job_ref}/results\"" in line for line in lines)
            assert any("\"rel\": \"http://www.opengis.net/def/rel/ogc/1.0/results\"" in line for line in lines)

    def test_execute_auto_monitor(self):
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_process():
                stack_exec.enter_context(mock_exec_proc)

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    self.url,
                    "-p", proc,
                    "-I", "message='TEST MESSAGE!'",
                    "-M",
                    "-T", 10,
                    "-W", 1
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any("\"jobID\": \"" in line for line in lines)  # don't care value, self-handled
            assert any(f"\"status\": \"{STATUS_SUCCEEDED}\"" in line for line in lines)
            assert any("\"rel\": \"http://www.opengis.net/def/rel/ogc/1.0/results\"" in line for line in lines)

    def test_execute_help_details(self):
        """
        Verify that formatting of the execute operation help provides multiple paragraphs with more details.
        """
        lines = run_command(
            [
                "weaver",
                "execute",
                "--help",
            ],
            trim=False
        )
        start = -1
        end = -1
        for index, line in enumerate(lines):
            if "-I INPUTS, --inputs INPUTS" in line:
                start = index + 1
            if "Example:" in line:
                end = index
                break
        assert 0 < start < end
        indent = "  " * lines[start].count("  ")
        assert len(indent) > 4
        assert all(line.startswith(indent) for line in lines[start:end])
        assert len([line for line in lines[start:end] if line == indent]) > 3, "Inputs should have a few paragraphs."

    def test_execute_invalid_format(self):
        proc = self.test_process["Echo"]
        bad_input_value = "'this is my malformed message'"  # missing '<id>=' portion
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "execute",
                self.url,
                "-p", proc,
                "-I", bad_input_value,
                "-M",
                "-T", 10,
                "-W", 1
            ],
            trim=False,
            entrypoint=weaver_cli,
            expect_error=True,
            only_local=True,
        )
        assert any(bad_input_value in line for line in lines)
