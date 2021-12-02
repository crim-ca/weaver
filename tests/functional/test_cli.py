"""
Functional tests for :mod:`weaver.cli`.
"""
import os

import pytest
import yaml

from tests.utils import get_weaver_url, mocked_sub_requests
from tests.functional import APP_PKG_ROOT
from tests.functional.utils import WpsConfigBase
from weaver.cli import WeaverClient


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
            payload = yaml.safe_load(echo_file)
        cls.deploy_process(payload, process_id=cls.test_process)

    def test_capabilities(self):
        result = mocked_sub_requests(self.app, self.client.capabilities)
        assert "processes" in result.body
        assert result.body["processes"] == [
            # builtin
            "file2string_array",
            "jsonarray2netcdf",
            "metalink2netcdf",
            # test process
            self.test_process,
        ]

