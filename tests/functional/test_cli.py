"""
Functional tests for :mod:`weaver.cli`.
"""
import contextlib
import copy
import os
import shutil
import tempfile

import pytest
import yaml

from tests.functional import APP_PKG_ROOT
from tests.functional.utils import WpsConfigBase
from tests.utils import get_weaver_url, mocked_execute_process, mocked_sub_requests, mocked_wps_output
from weaver.cli import WeaverClient
from weaver.formats import CONTENT_TYPE_TEXT_PLAIN
from weaver.status import STATUS_ACCEPTED, STATUS_SUCCEEDED


@pytest.mark.cli
class TestWeaverClient(WpsConfigBase):
    @classmethod
    def setUpClass(cls):
        cls.settings.update({
            "weaver.wps_output_dir": tempfile.mkdtemp(prefix="weaver-test-"),
            "weaver.wps_output_url": "http://random-file-server.com/wps-outputs"
        })
        super(TestWeaverClient, cls).setUpClass()
        cls.url = get_weaver_url(cls.app.app.registry)
        cls.client = WeaverClient(cls.url)

        # make one process available for testing features
        cls.test_process = "test-client-echo"
        cls.test_payload = cls.load_resource_file("DeployProcess_Echo.yml")
        cls.deploy_process(cls.test_payload, process_id=cls.test_process)

    @classmethod
    def tearDownClass(cls):
        super(TestWeaverClient, cls).tearDownClass()
        tmp_wps_out = cls.settings.get("weaver.wps_output_dir", "")
        if os.path.isdir(tmp_wps_out):
            shutil.rmtree(tmp_wps_out, ignore_errors=True)

    @staticmethod
    def load_resource_file(name):
        with open(os.path.join(APP_PKG_ROOT, name)) as echo_file:
            return yaml.safe_load(echo_file)

    def process_listing_op(self, operation):
        result = mocked_sub_requests(self.app, operation)
        assert result.success
        assert "processes" in result.body
        assert result.body["processes"] == [
            # builtin
            "file2string_array",
            "jsonarray2netcdf",
            "metalink2netcdf",
            # test process
            self.test_process,
        ]

    def test_capabilities(self):
        self.process_listing_op(self.client.capabilities)

    def test_processes(self):
        self.process_listing_op(self.client.processes)

    def test_undeploy(self):
        # deploy a new process to leave the test one available
        other_payload = copy.deepcopy(self.test_payload)
        other_process = self.test_process + "-other"
        self.deploy_process(other_payload, process_id=other_process)

        result = mocked_sub_requests(self.app, self.client.undeploy, other_process)
        assert result.success
        assert result.body.get("undeploymentDone", None) is True

        path = f"/processes/{other_process}"
        resp = mocked_sub_requests(self.app, "get", path, expect_errors=True)
        assert resp.status_code == 404

    def test_describe(self):
        result = mocked_sub_requests(self.app, self.client.describe, self.test_process)
        assert result.success
        # see deployment file for details that are expected here
        assert result.body["id"] == self.test_process
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

    def run_execute_inputs_schema_variant(self, inputs_param, preload=False, expect_success=True, mock_exec=True):
        if isinstance(inputs_param, str):
            if preload:
                inputs_param = self.load_resource_file(inputs_param)
            else:
                inputs_param = os.path.join(APP_PKG_ROOT, inputs_param)
        with contextlib.ExitStack() as stack_exec:
            # use pass-through function because don't care about execution result here, only the parsing of I/O
            if mock_exec:
                mock_exec_func = lambda *_, **__: None  # noqa
            else:
                mock_exec_func = None
            for mock_exec_proc in mocked_execute_process(func_execute_process=mock_exec_func):
                stack_exec.enter_context(mock_exec_proc)
            result = mocked_sub_requests(self.app, self.client.execute, self.test_process, inputs=inputs_param)
        if expect_success:
            assert result.success, result.text
            assert "jobID" in result.body
            assert "processID" in result.body
            assert "status" in result.body
            assert "location" in result.body
            assert result.body["processID"] == self.test_process
            assert result.body["status"] == STATUS_ACCEPTED
            assert result.body["location"] == result.headers["Location"]
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
        result = mocked_sub_requests(self.app, self.client.monitor, job_id, timeout=1, delta=1)
        assert result.success, result.text
        assert result.body.get("status") == STATUS_SUCCEEDED
        links = result.body.get("links")
        assert isinstance(links, list)
        assert len(list(filter(lambda _link: _link["rel"].endswith("results"), links))) == 1

        # first test to get job results details, but not downloading yet
        result = mocked_sub_requests(self.app, self.client.results, job_id)
        assert result.success, result.text
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
