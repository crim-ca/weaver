"""
Functional tests for :mod:`weaver.cli`.
"""
import copy
import os

import pytest
import yaml

from tests.utils import get_weaver_url, mocked_sub_requests
from tests.functional import APP_PKG_ROOT
from tests.functional.utils import WpsConfigBase
from weaver.cli import WeaverClient
from weaver.formats import CONTENT_TYPE_TEXT_PLAIN


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

    def test_capabilities(self):
        result = mocked_sub_requests(self.app, self.client.capabilities)
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
        assert "outputs" in result.body["outputs"]
        assert result.body["outputs"]["output"]["title"] == "output"
        assert result.body["outputs"]["output"]["description"] == "Output file with echo message."
        assert result.body["outputs"]["output"]["formats"] == [{"default": True, "mediaType": CONTENT_TYPE_TEXT_PLAIN}]
