"""
Functional tests for :mod:`weaver.cli`.
"""
import contextlib
import copy
import os

import pytest
import yaml

from tests.utils import get_weaver_url, mocked_execute_process, mocked_sub_requests
from tests.functional import APP_PKG_ROOT
from tests.functional.utils import WpsConfigBase
from weaver.cli import WeaverClient
from weaver.formats import CONTENT_TYPE_TEXT_PLAIN
from weaver.status import STATUS_ACCEPTED


@pytest.mark.cli
class TestWeaverClient(WpsConfigBase):
    @classmethod
    def setUpClass(cls):
        super(TestWeaverClient, cls).setUpClass()
        cls.url = get_weaver_url(cls.app.app.registry)
        cls.client = WeaverClient(cls.url)

        # make one process available for testing features
        cls.test_process = "test-client-echo"
        with open(os.path.join(APP_PKG_ROOT, "DeployProcess_Echo.yml")) as echo_file:
            cls.test_payload = yaml.safe_load(echo_file)
        cls.deploy_process(cls.test_payload, process_id=cls.test_process)

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

    def run_execute_inputs_schema_variant(self, input_file_variant):
        file_ref = os.path.join(APP_PKG_ROOT, input_file_variant)
        with contextlib.ExitStack() as stack_exec:
            # use pass-through function because don't care about execution result here, only the parsing of I/O
            for mock_exec in mocked_execute_process(func_execute_process=lambda *_, **__: None):  # noqa
                stack_exec.enter_context(mock_exec)
            result = mocked_sub_requests(self.app, self.client.execute, self.test_process, inputs=file_ref)
        assert result.success, result.text
        assert "jobID" in result.body
        assert "processID" in result.body
        assert "status" in result.body
        assert "location" in result.body
        assert result.body["processID"] == self.test_process
        assert result.body["status"] == STATUS_ACCEPTED
        assert result.body["location"] == result.headers["Location"]

    def test_execute_inputs_cwl_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml")

    def test_execute_inputs_ogc_value_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_value_schema.yml")

    def test_execute_inputs_ogc_mapping_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_mapping_schema.yml")

    def test_execute_inputs_old_listing_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_old_listing_schema.yml")

    @pytest.mark.xfail(reason="not implemented")
    def test_execute_with_auto_monitor(self):
        # FIXME:
        #   properly test execute+monitor,
        #   need an actual async call because 'mocked_execute_process' blocks until complete,
        #   therefore, no pooling monitoring actually occurs (only single get status with final result)
        raise NotImplementedError
