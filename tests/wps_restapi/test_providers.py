import unittest
from distutils.version import LooseVersion

import owslib
import pyramid.testing
import pytest

from tests import resources
from tests.utils import (
    get_test_weaver_app,
    mocked_remote_server_requests_wps1,
    setup_config_with_mongodb,
    setup_mongodb_jobstore,
    setup_mongodb_processstore,
    setup_mongodb_servicestore
)
from weaver.execute import EXECUTE_CONTROL_OPTION_ASYNC, EXECUTE_TRANSMISSION_MODE_REFERENCE
from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.utils import fully_qualified_name


# pylint: disable=C0103,invalid-name
class WpsRestApiProcessesTest(unittest.TestCase):
    remote_server = None

    @classmethod
    def setUpClass(cls):
        settings = {
            "weaver.url": "https://localhost",
            "weaver.wps_path": "/ows/wps",
        }
        cls.config = setup_config_with_mongodb(settings=settings)
        cls.app = get_test_weaver_app(config=cls.config)
        cls.json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def fully_qualified_test_process_name(self):
        return fully_qualified_name(self).replace(".", "-")

    def setUp(self):
        # rebuild clean db on each test
        self.service_store = setup_mongodb_servicestore(self.config)
        self.process_store = setup_mongodb_processstore(self.config)
        self.job_store = setup_mongodb_jobstore(self.config)

        self.remote_provider_name = "test-remote-provider"
        self.process_remote_WPS1 = "process_remote_wps1"

    def register_provider(self, clear=True, error=False):
        if clear:
            self.service_store.clear_services()
        path = "/providers"
        data = {"id": self.remote_provider_name, "url": resources.TEST_REMOTE_SERVER_URL}
        resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=error)
        assert (error and resp.status_code != 201) or (not error and resp.status_code == 201)
        return resp

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_register_provider_success(self):
        resp = self.register_provider()

        # should have fetched extra metadata to populate service definition
        assert resp.json["id"] == self.remote_provider_name
        assert resp.json["url"] == resources.TEST_REMOTE_SERVER_URL
        assert resp.json["title"] == "Mock Remote Server"
        assert resp.json["description"] == "Testing"
        assert resp.json["public"] is False

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_register_provider_conflict(self):
        self.register_provider(clear=True, error=False)
        resp = self.register_provider(clear=False, error=True)
        assert resp.status_code == 409

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_get_provider_processes(self):
        self.register_provider()

        path = "/providers/{}/processes".format(self.remote_provider_name)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert "processes" in resp.json and isinstance(resp.json["processes"], list)
        assert len(resp.json["processes"]) == 2
        remote_processes = []
        for process in resp.json["processes"]:
            assert "id" in process and isinstance(process["id"], str)
            assert "title" in process and isinstance(process["title"], str)
            assert "version" in process and isinstance(process["version"], str)
            assert "keywords" in process and isinstance(process["keywords"], list)
            assert "metadata" in process and isinstance(process["metadata"], list)
            assert len(process["jobControlOptions"]) == 1
            assert EXECUTE_CONTROL_OPTION_ASYNC in process["jobControlOptions"]
            remote_processes.append(process["id"])
        assert resources.TEST_REMOTE_PROCESS_WPS1_ID in remote_processes

    @pytest.mark.xfail(condition=LooseVersion(owslib.__version__) <= LooseVersion("0.25.0"),
                       reason="OWSLib fix for retrieval of processVersion from DescribeProcess not yet available")
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_get_provider_process_description_with_version(self):
        """
        Test only the version field which depends on a fix from :mod:`OWSLib`.

        The process description retrieved from a remote WPS-1 DescribeProcess request should provide
        its version converted into JSON schema, for both the ``"OLD"`` and ``"OGC"`` schema representations.

        .. seealso::
            - Full description validation (OGC schema): :meth:`test_get_provider_process_description_ogc_schema`
            - Full description validation (OLD schema): :meth:`test_get_provider_process_description_old_schema`
            - Fix in PR `geopython/OWSLib#794 <https://github.com/geopython/OWSLib/pull/794>`_
        """
        path = "/providers/{}/processes/{}".format(self.remote_provider_name, resources.TEST_REMOTE_PROCESS_WPS1_ID)
        resp = self.app.get(path, params={"schema": "OLD"}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        proc = resp.json["process"]

        resp = self.app.get(path, params={"schema": "OGC"}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        desc = resp.json

        assert "version" in proc and isinstance(proc["version"], str) and proc["version"] == "1.0.0"
        assert "version" in desc and isinstance(desc["version"], str) and desc["version"] == "1.0.0"

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_get_provider_process_description_old_schema(self):
        self.register_provider()

        query = {"schema": "OLD"}
        path = "/providers/{}/processes/{}".format(self.remote_provider_name, resources.TEST_REMOTE_PROCESS_WPS1_ID)
        resp = self.app.get(path, params=query, headers=self.json_headers)
        body = resp.json
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert "process" in resp.json and isinstance(body["process"], dict)
        process = body["process"]
        assert "id" in process and isinstance(process["id"], str)
        assert process["id"] == resources.TEST_REMOTE_PROCESS_WPS1_ID
        assert "title" in process and isinstance(process["title"], str)
        assert "description" in process and isinstance(process["description"], str)
        # evaluated in separate test (test_get_provider_process_description_with_version)
        # assert "version" in process and isinstance(process["version"], str)
        assert "keywords" in process and isinstance(process["keywords"], list)
        assert "metadata" in process and isinstance(process["metadata"], list)
        assert len(body["jobControlOptions"]) == 1
        assert EXECUTE_CONTROL_OPTION_ASYNC in body["jobControlOptions"]
        assert len(body["outputTransmission"]) == 1
        assert EXECUTE_TRANSMISSION_MODE_REFERENCE in body["outputTransmission"]
        assert "inputs" in process and isinstance(process["inputs"], list)
        assert all(isinstance(p_io, dict) and "id" in p_io for p_io in process["inputs"])
        assert "outputs" in process and isinstance(process["outputs"], list)
        assert all(isinstance(p_io, dict) and "id" in p_io for p_io in process["outputs"])

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_get_provider_process_description_ogc_schema(self):
        self.register_provider()

        path = "/providers/{}/processes/{}".format(self.remote_provider_name, resources.TEST_REMOTE_PROCESS_WPS1_ID)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert "process" not in resp.json and isinstance(resp.json, dict)
        process = resp.json
        assert "id" in process and isinstance(process["id"], str)
        assert process["id"] == resources.TEST_REMOTE_PROCESS_WPS1_ID
        assert "title" in process and isinstance(process["title"], str)
        assert "description" in process and isinstance(process["description"], str)
        # evaluated in separate test (test_get_provider_process_description_with_version)
        # assert "version" in process and isinstance(process["version"], str) and len(process["version"])
        assert "keywords" in process and isinstance(process["keywords"], list)
        assert "metadata" in process and isinstance(process["metadata"], list)
        assert len(process["jobControlOptions"]) == 1
        assert EXECUTE_CONTROL_OPTION_ASYNC in process["jobControlOptions"]
        assert len(process["outputTransmission"]) == 1
        assert EXECUTE_TRANSMISSION_MODE_REFERENCE in process["outputTransmission"]
        assert "inputs" in process and isinstance(process["inputs"], dict)
        assert all(isinstance(p_io, str) and isinstance(process["inputs"][p_io], dict) for p_io in process["inputs"])
        assert all("id" not in process["inputs"][p_io] for p_io in process["inputs"])
        assert "outputs" in process and isinstance(process["outputs"], dict)
        assert all(isinstance(p_io, str) and isinstance(process["outputs"][p_io], dict) for p_io in process["outputs"])
        assert all("id" not in process["outputs"][p_io] for p_io in process["outputs"])

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.WPS_NO_INPUTS_XML],
    ])
    def test_get_provider_process_no_inputs(self):
        """
        Process that takes no inputs should be permitted and its description must allow generation of empty map/list.
        """
        self.register_provider()

        path = "/providers/{}/processes/{}".format(self.remote_provider_name, resources.WPS_NO_INPUTS_ID)
        resp = self.app.get(path, params={"schema": "OLD"}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        inputs = resp.json["process"]["inputs"]
        assert isinstance(inputs, list) and len(inputs) == 0

        path = "/providers/{}/processes/{}".format(self.remote_provider_name, resources.WPS_NO_INPUTS_ID)
        resp = self.app.get(path, params={"schema": "OGC"}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        inputs = resp.json["inputs"]
        assert isinstance(inputs, dict) and len(inputs) == 0
