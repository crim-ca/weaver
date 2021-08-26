import unittest

import pyramid.testing

from tests.utils import (
    get_test_weaver_app,
    mocked_remote_server_requests_wp1,
    setup_config_with_mongodb,
    setup_mongodb_jobstore,
    setup_mongodb_processstore,
    setup_mongodb_servicestore
)
from tests import resources
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

    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
    def test_register_provider_success(self):
        resp = self.register_provider()

        # should have fetched extra metadata to populate service definition
        assert resp.json["id"] == self.remote_provider_name
        assert resp.json["url"] == resources.TEST_REMOTE_SERVER_URL
        assert resp.json["title"] == "Mock Remote Server"
        assert resp.json["description"] == "Testing"
        assert resp.json["public"] is True

    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
    def test_register_provider_conflict(self):
        self.register_provider(clear=True, error=False)
        resp = self.register_provider(clear=False, error=True)
        assert resp.status_code == 409

    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
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

    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
    def test_get_provider_process_description_old_schema(self):
        self.register_provider()

        path = "/providers/{}/processes/{}".format(self.remote_provider_name, resources.TEST_REMOTE_PROCESS_WPS1_ID)
        resp = self.app.get(path, headers=self.json_headers)
        body = resp.json
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert "process" in resp.json and isinstance(body["process"], dict)
        process = body["process"]
        assert "id" in process and isinstance(process["id"], str)
        assert process["id"] == resources.TEST_REMOTE_PROCESS_WPS1_ID
        assert "title" in process and isinstance(process["title"], str)
        assert "description" in process and isinstance(process["description"], str)
        assert "version" in process and isinstance(process["version"], str)
        assert "keywords" in process and isinstance(process["keywords"], list)
        assert "metadata" in process and isinstance(process["metadata"], list)
        assert len(body["jobControlOptions"]) == 1
        assert EXECUTE_CONTROL_OPTION_ASYNC in process["jobControlOptions"]
        assert len(body["outputTransmission"]) == 1
        assert EXECUTE_TRANSMISSION_MODE_REFERENCE in process["outputTransmission"]
        assert "inputs" in process and isinstance(process["inputs"], list)
        assert all(isinstance(p_io, dict) and "id" in p_io for p_io in process["inputs"])
        assert "outputs" in process and isinstance(process["outputs"], list)
        assert all(isinstance(p_io, dict) and "id" in p_io for p_io in process["outputs"])

    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
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
        assert "version" in process and isinstance(process["version"], str)
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

    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.WPS_NO_INPUTS_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
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
