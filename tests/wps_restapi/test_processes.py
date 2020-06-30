import contextlib
import os
import unittest
from copy import deepcopy

import colander
import pyramid.testing
import pytest
import responses
import webtest

from tests.utils import (
    get_test_weaver_app,
    mocked_execute_process,
    mocked_process_job_runner,
    mocked_process_package,
    setup_config_with_mongodb,
    setup_mongodb_jobstore,
    setup_mongodb_processstore
)
from weaver.exceptions import JobNotFound, ProcessNotFound
from weaver.execute import (
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_MODE_ASYNC,
    EXECUTE_MODE_SYNC,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_TRANSMISSION_MODE_REFERENCE,
    EXECUTE_TRANSMISSION_MODE_VALUE
)
from weaver.formats import ACCEPT_LANGUAGE_EN_US, ACCEPT_LANGUAGE_FR_CA, CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_XML
from weaver.processes.wps_testing import WpsTestProcess
from weaver.status import STATUS_ACCEPTED
from weaver.utils import fully_qualified_name, ows_context_href
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from weaver.wps.utils import get_wps_url
from weaver.wps_restapi import swagger_definitions as sd

# simulated remote server with remote processes (mocked with `responses` package)
TEST_REMOTE_SERVER_URL = "https://remote-server.com"
TEST_REMOTE_PROCESS_WPS1_ID = "test-remote-process-wps1"
TEST_REMOTE_PROCESS_WPS3_ID = "test-remote-process-wps3"
TEST_REMOTE_PROCESS_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")
TEST_REMOTE_PROCESS_GETCAP_WPS1_FILE = os.path.join(TEST_REMOTE_PROCESS_ROOT, "test_get_capabilities_wps1.xml")
TEST_REMOTE_PROCESS_GETCAP_WPS1_URL = "{}/wps?service=WPS&request=GetCapabilities&version=1.0.0" \
                                      .format(TEST_REMOTE_SERVER_URL)
TEST_REMOTE_PROCESS_DESCRIBE_WPS1_FILE = os.path.join(TEST_REMOTE_PROCESS_ROOT, "test_describe_process_wps1.xml")
TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL = "{}/wps?service=WPS&request=DescribeProcess&identifier={}&version=1.0.0" \
                                        .format(TEST_REMOTE_SERVER_URL, TEST_REMOTE_PROCESS_WPS1_ID)
TEST_REMOTE_PROCESS_WPS3_FILE = os.path.join(TEST_REMOTE_PROCESS_ROOT, "test_describe_process_wps3.json")


def mock_remote_server_requests_wp1(test):
    """Mocks above `remote` references to local resources."""
    def mock_requests_wps1(*args, **kwargs):
        """Mock ``requests`` responses fetching ``TEST_REMOTE_SERVER_URL`` WPS reference."""
        xml_header = {"Content-Type": CONTENT_TYPE_APP_XML}
        with responses.RequestsMock(assert_all_requests_are_fired=False) as mock_resp:
            with open(TEST_REMOTE_PROCESS_DESCRIBE_WPS1_FILE, "r") as f:
                describe_xml = f.read()
            with open(TEST_REMOTE_PROCESS_GETCAP_WPS1_FILE, "r") as f:
                get_cap_xml = f.read()
            mock_resp.add(responses.GET, TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL, body=describe_xml, headers=xml_header)
            mock_resp.add(responses.GET, TEST_REMOTE_PROCESS_GETCAP_WPS1_URL, body=get_cap_xml, headers=xml_header)
            # special case where 'identifier' gets added to 'GetCapabilities', but is simply ignored
            getcap_with_process_id = TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL.replace("DescribeProcess", "GetCapabilities")
            mock_resp.add(responses.GET, body=get_cap_xml, headers=xml_header, url=getcap_with_process_id)
            return test(*args, **kwargs)
    return mock_requests_wps1


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
        cls.app = webtest.TestApp(cls.config.make_wsgi_app())

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def fully_qualified_test_process_name(self):
        return fully_qualified_name(self).replace(".", "-")

    def setUp(self):
        # rebuild clean db on each test
        self.process_store = setup_mongodb_processstore(self.config)
        self.job_store = setup_mongodb_jobstore(self.config)

        self.remote_server = "local"
        self.process_remote_WPS1 = "process_remote_wps1"
        self.process_remote_WPS3 = "process_remote_wps3"
        self.process_public = WpsTestProcess(identifier="process_public")
        self.process_private = WpsTestProcess(identifier="process_private")
        self.process_store.save_process(self.process_public)
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)

    @staticmethod
    def get_process_deploy_template(process_id):
        """
        Provides deploy process bare minimum template with undefined execution unit.
        To be used in conjunction with `get_process_package_mock` to avoid extra package content-specific validations.
        """
        return {
            "processDescription": {
                "process": {
                    "id": process_id,
                    "title": "Test process '{}'.".format(process_id),
                }
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            "executionUnit": [
                # full definition not required with mock
                {"unit": {
                    "class": "test"
                }}
            ]
        }

    @staticmethod
    def get_process_execute_template(test_input="not-specified"):
        """
        Provides execute process bare minimum template corresponding to
        WPS process `weaver.processes.wps_testing.WpsTestProcess`.
        """
        return {
            "inputs": [
                {"id": "test_input",
                 "data": test_input},
            ],
            "outputs": [
                {"id": "test_output",
                 "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE}
            ],
            "mode": EXECUTE_MODE_ASYNC,
            "response": EXECUTE_RESPONSE_DOCUMENT,
        }

    def test_get_processes(self):
        uri = "/processes"
        resp = self.app.get(uri, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert "processes" in resp.json and isinstance(resp.json["processes"], list) and len(resp.json["processes"]) > 0
        for process in resp.json["processes"]:
            assert "id" in process and isinstance(process["id"], str)
            assert "title" in process and isinstance(process["title"], str)
            assert "version" in process and isinstance(process["version"], str)
            assert "keywords" in process and isinstance(process["keywords"], list)
            assert "metadata" in process and isinstance(process["metadata"], list)

        processes_id = [p["id"] for p in resp.json["processes"]]
        assert self.process_public.identifier in processes_id
        assert self.process_private.identifier not in processes_id

    def test_get_processes_invalid_schemas_handled(self):
        path = "/processes"
        # deploy valid test process
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()
        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201
            assert resp.json["processSummary"]["id"] == process_name

        # change value that will trigger schema error on check
        process = self.process_store.fetch_by_id(process_name)
        process["jobControlOptions"] = "random"  # invalid
        process["visibility"] = VISIBILITY_PUBLIC
        self.process_store.save_process(process, overwrite=True)

        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 503
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert process_name in resp.json.get("description")

    def test_describe_process_visibility_public(self):
        uri = "/processes/{}".format(self.process_public.identifier)
        resp = self.app.get(uri, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_describe_process_visibility_private(self):
        uri = "/processes/{}".format(self.process_private.identifier)
        resp = self.app.get(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_deploy_process_success(self):
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201
            assert resp.content_type == CONTENT_TYPE_APP_JSON
            assert resp.json["processSummary"]["id"] == process_name
            assert isinstance(resp.json["deploymentDone"], bool) and resp.json["deploymentDone"]

    def test_deploy_process_bad_name(self):
        process_name = self.fully_qualified_test_process_name() + "..."
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 400
            assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_deploy_process_conflict(self):
        process_name = self.process_private.identifier
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 409
            assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_deploy_process_missing_or_invalid_components(self):
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        # remove components for testing different cases
        process_data_tests = [deepcopy(process_data) for _ in range(12)]
        process_data_tests[0].pop("processDescription")
        process_data_tests[1]["processDescription"].pop("process")
        process_data_tests[2]["processDescription"]["process"].pop("id")
        process_data_tests[3]["processDescription"]["jobControlOptions"] = EXECUTE_CONTROL_OPTION_ASYNC
        process_data_tests[4]["processDescription"]["jobControlOptions"] = [EXECUTE_MODE_ASYNC]
        process_data_tests[5].pop("deploymentProfileName")
        process_data_tests[6].pop("executionUnit")
        process_data_tests[7]["executionUnit"] = {}
        process_data_tests[8]["executionUnit"] = list()
        process_data_tests[9]["executionUnit"][0] = {"unit": "something"}  # unit as string instead of package
        process_data_tests[10]["executionUnit"][0] = {"href": {}}  # href as package instead of url
        process_data_tests[11]["executionUnit"][0] = {"unit": {}, "href": ""}  # can"t have both unit/href together

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            uri = "/processes"
            for i, data in enumerate(process_data_tests):
                resp = self.app.post_json(uri, params=data, headers=self.json_headers, expect_errors=True)
                msg = "Failed with test variation '{}' with value '{}'."
                assert resp.status_code in [400, 422], msg.format(i, resp.status_code)
                assert resp.content_type == CONTENT_TYPE_APP_JSON, msg.format(i, resp.content_type)

    def test_deploy_process_default_endpoint_wps1(self):
        """Validates that the default (localhost) endpoint to execute WPS requests are saved during deployment."""
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            uri = "/processes"
            resp = self.app.post_json(uri, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201

        weaver_wps_path = get_wps_url(self.config.registry.settings)
        process_wps_endpoint = self.process_store.fetch_by_id(process_name).processEndpointWPS1
        assert isinstance(process_wps_endpoint, str) and len(process_wps_endpoint)
        assert process_wps_endpoint == weaver_wps_path

    @staticmethod
    def assert_deployed_wps3(response_json, expected_process_id):
        assert expected_process_id in response_json["process"]["id"]
        assert len(response_json["process"]["inputs"]) == 1
        assert response_json["process"]["inputs"][0]["id"] == "input-1"
        assert response_json["process"]["inputs"][0]["minOccurs"] == "1"
        assert response_json["process"]["inputs"][0]["maxOccurs"] == "1"
        assert "formats" not in response_json["process"]["inputs"][0]   # literal data doesn't have "formats"
        assert len(response_json["process"]["outputs"]) == 1
        assert response_json["process"]["outputs"][0]["id"] == "output"
        assert "minOccurs" not in response_json["process"]["outputs"][0]
        assert "maxOccurs" not in response_json["process"]["outputs"][0]
        # TODO: handling multiple outputs (https://github.com/crim-ca/weaver/issues/25)
        # assert response_json["process"]["outputs"][0]["minOccurs"] == "1"
        # assert response_json["process"]["outputs"][0]["maxOccurs"] == "1"
        assert isinstance(response_json["process"]["outputs"][0]["formats"], list)
        assert len(response_json["process"]["outputs"][0]["formats"]) == 1
        assert response_json["process"]["outputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON

    def deploy_process_make_visible_and_fetch_deployed(self, deploy_payload, expected_process_id):
        """
        Attempts to deploy the process using the provided deployment payload, then makes it visible and finally
        fetches the deployed process to validate the resulting WPS-3 REST JSON description.

        Any failure along the way is raised.

        .. note::
            This is a shortcut method for all ``test_deploy_process_<>`` cases.
        """
        resp = self.app.post_json("/processes", params=deploy_payload, headers=self.json_headers)
        assert resp.status_code == 201
        assert resp.content_type == CONTENT_TYPE_APP_JSON

        # apply visibility to allow retrieval
        proc_id = resp.json["processSummary"]["id"]  # process id could have been cleaned up
        proc_url = "/processes/{}".format(proc_id)
        body = {"value": VISIBILITY_PUBLIC}
        resp = self.app.put_json("{}/visibility".format(proc_url), params=body, headers=self.json_headers)
        assert resp.status_code == 200

        resp = self.app.get(proc_url, headers=self.json_headers)
        assert resp.status_code == 200
        self.assert_deployed_wps3(resp.json, expected_process_id)

    # FIXME: implement
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_process_CWL_DockerRequirement_href(self):
        raise NotImplementedError

    # FIXME: implement
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_process_CWL_DockerRequirement_owsContext(self):
        raise NotImplementedError

    # FIXME: implement
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_process_CWL_DockerRequirement_executionUnit(self):
        raise NotImplementedError

    # FIXME: implement
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_process_CWL_WPS1Requirement_href(self):
        raise NotImplementedError

    # FIXME: implement
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_process_CWL_WPS1Requirement_owsContext(self):
        raise NotImplementedError

    # FIXME: implement
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_process_CWL_WPS1Requirement_executionUnit(self):
        raise NotImplementedError

    @mock_remote_server_requests_wp1
    def test_deploy_process_WPS1_DescribeProcess_href(self):
        body = {
            "processDescription": {"href": TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL},  # this one should be used
            "executionUnit": [{"href": TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, TEST_REMOTE_PROCESS_WPS1_ID)

    @mock_remote_server_requests_wp1
    def test_deploy_process_WPS1_DescribeProcess_owsContext(self):
        body = {
            "processDescription": {"process": {"id": TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        body["processDescription"]["process"].update(ows_context_href(TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL))
        self.deploy_process_make_visible_and_fetch_deployed(body, TEST_REMOTE_PROCESS_WPS1_ID)

    @mock_remote_server_requests_wp1
    def test_deploy_process_WPS1_DescribeProcess_executionUnit(self):
        """Test process deployment using a WPS-1 DescribeProcess URL specified as process description reference."""
        body = {
            "processDescription": {"process": {"id": TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, TEST_REMOTE_PROCESS_WPS1_ID)

    @pytest.mark.skip(reason="not implemented")
    @mock_remote_server_requests_wp1
    def test_deploy_process_WPS1_GetCapabilities_href(self):
        """Test process deployment using a WPS-1 GetCapabilities URL specified as process description reference."""
        body = {
            "processDescription": {"href": TEST_REMOTE_PROCESS_GETCAP_WPS1_URL},  # this one should be used
            "executionUnit": [{"href": TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, TEST_REMOTE_PROCESS_WPS1_ID)

    @pytest.mark.skip(reason="not implemented")
    @mock_remote_server_requests_wp1
    def test_deploy_process_WPS1_GetCapabilities_owsContext(self):
        """Test process deployment using a WPS-1 GetCapabilities URL specified through the OwsContext definition."""
        body = {
            "processDescription": {"process": {"id": TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        body["processDescription"]["process"].update(ows_context_href(TEST_REMOTE_PROCESS_GETCAP_WPS1_URL))
        self.deploy_process_make_visible_and_fetch_deployed(body, TEST_REMOTE_PROCESS_WPS1_ID)

    @pytest.mark.skip(reason="not implemented")
    @mock_remote_server_requests_wp1
    def test_deploy_process_WPS1_GetCapabilities_executionUnit(self):
        """Test process deployment using a WPS-1 GetCapabilities URL specified through the ExecutionUnit parameter."""
        body = {
            "processDescription": {"process": {"id": TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": TEST_REMOTE_PROCESS_GETCAP_WPS1_URL}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, TEST_REMOTE_PROCESS_WPS1_ID)

    # FIXME: implement
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_process_WPS3_DescribeProcess_href(self):
        raise NotImplementedError

    # FIXME: implement
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_process_WPS3_DescribeProcess_owsContext(self):
        raise NotImplementedError

    # FIXME: implement
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_process_WPS3_DescribeProcess_executionUnit(self):
        raise NotImplementedError

    def test_delete_process_success(self):
        uri = "/processes/{}".format(self.process_public.identifier)
        resp = self.app.delete_json(uri, headers=self.json_headers)
        assert resp.status_code == 200, "Error: {}".format(resp.text)
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert resp.json["identifier"] == self.process_public.identifier
        assert isinstance(resp.json["undeploymentDone"], bool) and resp.json["undeploymentDone"]
        with pytest.raises(ProcessNotFound):
            self.process_store.fetch_by_id(self.process_public.identifier)

    def test_delete_process_not_accessible(self):
        uri = "/processes/{}".format(self.process_private.identifier)
        resp = self.app.delete_json(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403, "Error: {}".format(resp.text)
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_delete_process_not_found(self):
        uri = "/processes/{}".format(self.fully_qualified_test_process_name())
        resp = self.app.delete_json(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404, "Error: {}".format(resp.text)
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_delete_process_bad_name(self):
        uri = "/processes/{}".format(self.fully_qualified_test_process_name() + "...")
        resp = self.app.delete_json(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400, "Error: {}".format(resp.text)
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_execute_process_success(self):
        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        data = self.get_process_execute_template()
        task = "job-{}".format(fully_qualified_name(self))
        mock_execute = mocked_process_job_runner(task)

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            resp = self.app.post_json(uri, params=data, headers=self.json_headers)
            assert resp.status_code == 201, "Error: {}".format(resp.text)
            assert resp.content_type == CONTENT_TYPE_APP_JSON
            assert resp.json["location"].endswith(resp.json["jobID"])
            assert resp.headers["Location"] == resp.json["location"]
            try:
                job = self.job_store.fetch_by_id(resp.json["jobID"])
            except JobNotFound:
                self.fail("Job should have been created and be retrievable.")
            assert job.id == resp.json["jobID"]
            assert job.task_id == STATUS_ACCEPTED  # temporary value until processed by celery

    def test_execute_process_language(self):
        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        data = self.get_process_execute_template()
        task = "job-{}".format(fully_qualified_name(self))
        mock_execute = mocked_process_job_runner(task)

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            headers = self.json_headers.copy()
            headers["Accept-Language"] = ACCEPT_LANGUAGE_FR_CA
            resp = self.app.post_json(uri, params=data, headers=headers)
            assert resp.status_code == 201, "Error: {}".format(resp.text)
            try:
                job = self.job_store.fetch_by_id(resp.json["jobID"])
            except JobNotFound:
                self.fail("Job should have been created and be retrievable.")
            assert job.id == resp.json["jobID"]
            assert job.accept_language == ACCEPT_LANGUAGE_FR_CA

    def test_execute_process_no_json_body(self):
        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        resp = self.app.post_json(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_execute_process_missing_required_params(self):
        execute_data = self.get_process_execute_template(fully_qualified_name(self))

        # remove components for testing different cases
        execute_data_tests = [deepcopy(execute_data) for _ in range(7)]
        execute_data_tests[0].pop("outputs")
        execute_data_tests[1].pop("mode")
        execute_data_tests[2].pop("response")
        execute_data_tests[3]["mode"] = "random"
        execute_data_tests[4]["response"] = "random"
        execute_data_tests[5]["inputs"] = [{"test_input": "test_value"}]  # bad format
        execute_data_tests[6]["outputs"] = [{"id": "test_output", "transmissionMode": "random"}]

        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        for i, exec_data in enumerate(execute_data_tests):
            resp = self.app.post_json(uri, params=exec_data, headers=self.json_headers, expect_errors=True)
            msg = "Failed with test variation '{}' with value '{}'."
            assert resp.status_code in [400, 422], msg.format(i, resp.status_code)
            assert resp.content_type == CONTENT_TYPE_APP_JSON, msg.format(i, resp.content_type)

    def test_execute_process_dont_cast_one_of(self):
        """
        When validating the schema for OneOf values, don't cast the result to the first valid schema.
        """
        # get basic mock/data templates
        name = fully_qualified_name(self)
        execute_mock_data_tests = list()

        mock_execute = mocked_process_job_runner("job-{}".format(name))
        data_execute = self.get_process_execute_template("100")
        execute_mock_data_tests.append((mock_execute, data_execute))

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            path = "/processes/{}/jobs".format(self.process_public.identifier)
            resp = self.app.post_json(path, params=data_execute, headers=self.json_headers)
            assert resp.status_code == 201, "Expected job submission without inputs created without error."
            job = self.job_store.fetch_by_id(resp.json["jobID"])
            assert job.inputs[0]["value"] == "100"  # not cast to float or integer

    def test_execute_process_no_error_not_required_params(self):
        """
        Optional parameters for execute job shouldn't raise an error if omitted,
        and should resolve to default values if any was specified.
        """
        # get basic mock/data templates
        name = fully_qualified_name(self)
        execute_mock_data_tests = list()
        for i in range(2):
            mock_execute = mocked_process_job_runner("job-{}-{}".format(name, i))
            data_execute = self.get_process_execute_template("{}-{}".format(name, i))
            execute_mock_data_tests.append((mock_execute, data_execute))

        # apply modifications for testing
        execute_mock_data_tests[0][1].pop("inputs")  # no inputs is valid (although can be required for WPS process)
        execute_mock_data_tests[0][1]["outputs"][0].pop("transmissionMode")  # should resolve to default value

        for mock_execute, data_execute in execute_mock_data_tests:
            with contextlib.ExitStack() as stack:
                for exe in mock_execute:
                    stack.enter_context(exe)
                path = "/processes/{}/jobs".format(self.process_public.identifier)
                resp = self.app.post_json(path, params=data_execute, headers=self.json_headers)
                assert resp.status_code == 201, "Expected job submission without inputs created without error."

    @pytest.mark.xfail(reason="Mode '{}' not supported for job execution.".format(EXECUTE_MODE_SYNC))
    def test_execute_process_mode_sync_not_supported(self):
        execute_data = self.get_process_execute_template(fully_qualified_name(self))
        execute_data["mode"] = EXECUTE_MODE_SYNC
        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        resp = self.app.post_json(uri, params=execute_data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 501
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    @pytest.mark.xfail(reason="Mode '{}' not supported for job execution.".format(EXECUTE_TRANSMISSION_MODE_VALUE))
    def test_execute_process_transmission_mode_value_not_supported(self):
        execute_data = self.get_process_execute_template(fully_qualified_name(self))
        execute_data["outputs"][0]["transmissionMode"] = EXECUTE_TRANSMISSION_MODE_VALUE
        uri = "/processes/{}/jobs".format(self.process_public.identifier)
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_process():
                stack_exec.enter_context(mock_exec)
            resp = self.app.post_json(uri, params=execute_data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 501
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_execute_process_not_visible(self):
        uri = "/processes/{}/jobs".format(self.process_private.identifier)
        data = self.get_process_execute_template()
        resp = self.app.post_json(uri, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_process_visibility_expected_response(self):
        for http_code, wps_process in [(403, self.process_private), (200, self.process_public)]:
            process = self.process_store.fetch_by_id(wps_process.identifier)
            uri = "/processes/{}/visibility".format(process.identifier)
            resp = self.app.get(uri, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == http_code
            assert resp.content_type == CONTENT_TYPE_APP_JSON
            if http_code == 200:
                assert resp.json["value"] == process.visibility
            else:
                assert "value" not in resp.json

    def test_get_process_visibility_not_found(self):
        uri = "/processes/{}/visibility".format(self.fully_qualified_test_process_name())
        resp = self.app.get(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_set_process_visibility_success(self):
        test_process = self.process_private.identifier
        uri_describe = "/processes/{}".format(test_process)
        uri_visibility = "{}/visibility".format(uri_describe)

        # validate cannot be found before
        resp = self.app.get(uri_describe, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403

        # make public
        data = {"value": VISIBILITY_PUBLIC}
        resp = self.app.put_json(uri_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert resp.json["value"] == VISIBILITY_PUBLIC

        # validate now visible and found
        resp = self.app.get(uri_describe, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.json["process"]["id"] == test_process

        # make private
        data = {"value": VISIBILITY_PRIVATE}
        resp = self.app.put_json(uri_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert resp.json["value"] == VISIBILITY_PRIVATE

        # validate cannot be found anymore
        resp = self.app.get(uri_describe, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403

    def test_set_process_visibility_bad_formats(self):
        uri = "/processes/{}/visibility".format(self.process_private.identifier)
        test_data = [
            {"visibility": VISIBILITY_PUBLIC},
            {"visibility": True},
            {"visibility": None},
            {"visibility": 1},
            {"value": True},
            {"value": None},
            {"value": 1}
        ]

        # bad body format or types
        for data in test_data:
            resp = self.app.put_json(uri, params=data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code in [400, 422]
            assert resp.content_type == CONTENT_TYPE_APP_JSON

        # bad method POST
        data = {"value": VISIBILITY_PUBLIC}
        resp = self.app.post_json(uri, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 405
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_process_description_metadata_href_or_value_valid(self):
        """Validates that metadata is accepted as either hyperlink reference or literal string value."""
        sd.Process().deserialize({
            "id": self._testMethodName,
            "metadata": [
                {"type": "value-typed", "value": "some-value", "lang": "en-US"},
                {"type": "link-typed", "href": "https://example.com", "hreflang": "en-US", "rel": "example"}
            ]
        })

    def test_process_description_metadata_href_or_value_invalid(self):
        """Validates that various invalid metadata definitions are indicated as such."""
        test_meta = [
            [{"type": "value", "lang": "en-US"}],  # missing 'value'
            [{"href": "https://example.com", "hreflang": "en-US"}],  # missing 'rel'
            [{"value": "https://example.com", "rel": "value-type"}],  # incorrect 'rel' with 'value' type
            [{"href": "https://example.com", "lang": "en-US"}],  # incorrect 'lang' instead of 'hreflang' with 'href'
            [{"value": "https://example.com", "hreflang": "en-US"}],  # incorrect 'hreflang' with 'value'
        ]
        for i, meta in enumerate(test_meta):
            try:
                sd.Process().deserialize({
                    "id": "{}_meta_{}".format(self._testMethodName, i),
                    "metadata": meta,
                })
            except colander.Invalid:
                pass
            else:
                self.fail("Metadata is expected to be raised as invalid: (test: {}, metadata: {})".format(i, test_meta))
