import contextlib
import json
import unittest
from copy import deepcopy
from typing import TYPE_CHECKING

import colander
import pyramid.testing
import pytest
import stopit

from tests.utils import (
    get_test_weaver_app,
    mocked_execute_process,
    mocked_process_job_runner,
    mocked_process_package,
    mocked_remote_server_requests_wp1,
    setup_config_with_mongodb,
    setup_mongodb_jobstore,
    setup_mongodb_processstore
)
from tests import resources
from weaver.exceptions import JobNotFound, ProcessNotFound
from weaver.execute import (
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_CONTROL_OPTION_SYNC,
    EXECUTE_MODE_ASYNC,
    EXECUTE_MODE_SYNC,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_TRANSMISSION_MODE_REFERENCE,
    EXECUTE_TRANSMISSION_MODE_VALUE
)
from weaver.formats import ACCEPT_LANGUAGE_FR_CA, CONTENT_TYPE_APP_JSON
from weaver.processes.wps_testing import WpsTestProcess
from weaver.status import STATUS_ACCEPTED
from weaver.utils import fully_qualified_name, ows_context_href
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from weaver.wps.utils import get_wps_url
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from weaver.typedefs import JSON


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
        # type: (str) -> JSON
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
                # use 'href' variant to avoid invalid schema validation via more explicit 'unit'
                # note:
                #   hostname cannot have underscores according to [RFC-1123](https://www.ietf.org/rfc/rfc1123.txt)
                #   schema validator of Reference URL will appropriately raise such invalid string
                {"href": "http://weaver.test/{}.cwl".format(process_id)}
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
        path = "/processes"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert "processes" in resp.json and isinstance(resp.json["processes"], list) and len(resp.json["processes"]) > 0
        for process in resp.json["processes"]:
            assert "id" in process and isinstance(process["id"], str)
            assert "title" in process and isinstance(process["title"], str)
            assert "version" in process and isinstance(process["version"], str)
            assert "keywords" in process and isinstance(process["keywords"], list)
            assert "metadata" in process and isinstance(process["metadata"], list)
            assert len(process["jobControlOptions"]
                       ) == 1 and EXECUTE_CONTROL_OPTION_ASYNC in process["jobControlOptions"]

        processes_id = [p["id"] for p in resp.json["processes"]]
        assert self.process_public.identifier in processes_id
        assert self.process_private.identifier not in processes_id

    def test_set_jobControlOptions_async_execute(self):
        path = "/processes"
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        process_data["processDescription"]["jobControlOptions"] = [EXECUTE_CONTROL_OPTION_ASYNC]
        package_mock = mocked_process_package()
        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201
            assert resp.json["processSummary"]["id"] == process_name

        process = self.process_store.fetch_by_id(process_name)
        assert EXECUTE_CONTROL_OPTION_ASYNC in process["jobControlOptions"]

    def test_set_jobControlOptions_sync_execute(self):
        path = "/processes"
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        process_data["processDescription"]["jobControlOptions"] = [EXECUTE_CONTROL_OPTION_SYNC]
        package_mock = mocked_process_package()
        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201
            assert resp.json["processSummary"]["id"] == process_name

        process = self.process_store.fetch_by_id(process_name)
        assert EXECUTE_CONTROL_OPTION_SYNC in process["jobControlOptions"]

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
        process["outputTransmission"] = "random"  # invalid (don't use jobControlOptions fixed in-place)
        process["visibility"] = VISIBILITY_PUBLIC
        self.process_store.save_process(process, overwrite=True)

        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 503
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert process_name in resp.json.get("description")

    def test_describe_process_visibility_public(self):
        path = "/processes/{}".format(self.process_public.identifier)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_describe_process_visibility_private(self):
        path = "/processes/{}".format(self.process_private.identifier)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_deploy_process_success(self):
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
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
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 400
            assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_deploy_process_conflict(self):
        process_name = self.process_private.identifier
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
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
        process_data_tests[2]["processDescription"]["process"].pop("id")  # noqa
        process_data_tests[3]["processDescription"]["jobControlOptions"] = EXECUTE_CONTROL_OPTION_ASYNC
        process_data_tests[4]["processDescription"]["jobControlOptions"] = [EXECUTE_MODE_ASYNC]  # noqa
        process_data_tests[5].pop("deploymentProfileName")
        process_data_tests[6].pop("executionUnit")
        process_data_tests[7]["executionUnit"] = {}
        process_data_tests[8]["executionUnit"] = list()
        process_data_tests[9]["executionUnit"][0] = {"unit": "something"}  # unit as string instead of package
        process_data_tests[10]["executionUnit"][0] = {"href": {}}  # noqa  # href as package instead of URL
        process_data_tests[11]["executionUnit"][0] = {"unit": {}, "href": ""}  # can"t have both unit/href together

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            for i, data in enumerate(process_data_tests):
                resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=True)
                msg = "Failed with test variation '{}' with value '{}' using data:\n{}"
                assert resp.status_code in [400, 422], msg.format(i, resp.status_code, json.dumps(data, indent=2))
                assert resp.content_type == CONTENT_TYPE_APP_JSON, msg.format(i, resp.content_type)

    def test_deploy_process_default_endpoint_wps1(self):
        """Validates that the default (localhost) endpoint to execute WPS requests are saved during deployment."""
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201

        weaver_wps_path = get_wps_url(self.config.registry.settings)
        process_wps_endpoint = self.process_store.fetch_by_id(process_name).processEndpointWPS1
        assert isinstance(process_wps_endpoint, str) and len(process_wps_endpoint)
        assert process_wps_endpoint == weaver_wps_path

    @staticmethod
    def assert_deployed_wps3(response_json, expected_process_id):
        assert expected_process_id in response_json["id"]
        assert len(response_json["inputs"]) == 1
        assert response_json["inputs"][0]["id"] == "input-1"
        assert response_json["inputs"][0]["minOccurs"] == 1
        assert response_json["inputs"][0]["maxOccurs"] == 1
        assert "formats" not in response_json["inputs"][0]   # literal data doesn't have "formats"
        assert len(response_json["outputs"]) == 1
        assert response_json["outputs"][0]["id"] == "output"
        assert "minOccurs" not in response_json["outputs"][0]
        assert "maxOccurs" not in response_json["outputs"][0]
        # TODO: handling multiple outputs (https://github.com/crim-ca/weaver/issues/25)
        # assert response_json["outputs"][0]["minOccurs"] == "1"
        # assert response_json["outputs"][0]["maxOccurs"] == "1"
        assert isinstance(response_json["outputs"][0]["formats"], list)
        assert len(response_json["outputs"][0]["formats"]) == 1
        assert response_json["outputs"][0]["formats"][0]["mediaType"] == CONTENT_TYPE_APP_JSON

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

        proc_query = {"schema": "OLD"}
        resp = self.app.get(proc_url, params=proc_query, headers=self.json_headers)
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

    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
    def test_deploy_process_WPS1_DescribeProcess_href(self):
        body = {
            "processDescription": {"href": resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL},  # this one should be used
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)

    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
    def test_deploy_process_WPS1_DescribeProcess_owsContext(self):
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        body["processDescription"]["process"].update(ows_context_href(resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL))
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)

    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
    def test_deploy_process_WPS1_DescribeProcess_executionUnit(self):
        """Test process deployment using a WPS-1 DescribeProcess URL specified as process description reference."""
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)

    @pytest.mark.skip(reason="not implemented")
    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
    def test_deploy_process_WPS1_GetCapabilities_href(self):
        """Test process deployment using a WPS-1 GetCapabilities URL specified as process description reference."""
        body = {
            "processDescription": {"href": resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_URL},  # this one should be used
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)

    @pytest.mark.skip(reason="not implemented")
    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
    def test_deploy_process_WPS1_GetCapabilities_owsContext(self):
        """Test process deployment using a WPS-1 GetCapabilities URL specified through the OwsContext definition."""
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        body["processDescription"]["process"].update(ows_context_href(resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_URL))
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)

    @pytest.mark.skip(reason="not implemented")
    @mocked_remote_server_requests_wp1(
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
        resources.TEST_REMOTE_SERVER_URL
    )
    def test_deploy_process_WPS1_GetCapabilities_executionUnit(self):
        """Test process deployment using a WPS-1 GetCapabilities URL specified through the ExecutionUnit parameter."""
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_URL}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)

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
        path = "/processes/{}".format(self.process_public.identifier)
        resp = self.app.delete_json(path, headers=self.json_headers)
        assert resp.status_code == 200, "Error: {}".format(resp.text)
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert resp.json["identifier"] == self.process_public.identifier
        assert isinstance(resp.json["undeploymentDone"], bool) and resp.json["undeploymentDone"]
        with pytest.raises(ProcessNotFound):
            self.process_store.fetch_by_id(self.process_public.identifier)

    def test_delete_process_not_accessible(self):
        path = "/processes/{}".format(self.process_private.identifier)
        resp = self.app.delete_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403, "Error: {}".format(resp.text)
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_delete_process_not_found(self):
        path = "/processes/{}".format(self.fully_qualified_test_process_name())
        resp = self.app.delete_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404, "Error: {}".format(resp.text)
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_delete_process_bad_name(self):
        path = "/processes/{}".format(self.fully_qualified_test_process_name() + "...")
        resp = self.app.delete_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400, "Error: {}".format(resp.text)
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_execute_process_success(self):
        path = "/processes/{}/jobs".format(self.process_public.identifier)
        data = self.get_process_execute_template()
        task = "job-{}".format(fully_qualified_name(self))
        mock_execute = mocked_process_job_runner(task)

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            resp = self.app.post_json(path, params=data, headers=self.json_headers)
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
        path = "/processes/{}/jobs".format(self.process_public.identifier)
        data = self.get_process_execute_template()
        task = "job-{}".format(fully_qualified_name(self))
        mock_execute = mocked_process_job_runner(task)

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            headers = self.json_headers.copy()
            headers["Accept-Language"] = ACCEPT_LANGUAGE_FR_CA
            resp = self.app.post_json(path, params=data, headers=headers)
            assert resp.status_code == 201, "Error: {}".format(resp.text)
            try:
                job = self.job_store.fetch_by_id(resp.json["jobID"])
            except JobNotFound:
                self.fail("Job should have been created and be retrievable.")
            assert job.id == resp.json["jobID"]
            assert job.accept_language == ACCEPT_LANGUAGE_FR_CA

    def test_execute_process_no_json_body(self):
        path = "/processes/{}/jobs".format(self.process_public.identifier)
        resp = self.app.post_json(path, headers=self.json_headers, expect_errors=True)
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

        path = "/processes/{}/jobs".format(self.process_public.identifier)
        for i, exec_data in enumerate(execute_data_tests):
            data_json = json.dumps(exec_data, indent=2)
            with stopit.ThreadingTimeout(3) as timeout:  # timeout to kill dummy execution if schema validation fails
                resp = self.app.post_json(path, params=exec_data, headers=self.json_headers, expect_errors=True)
                msg = "Failed with test variation '{}' with status '{}' using {}."
                assert resp.status_code in [400, 422], msg.format(i, resp.status_code, data_json)
                assert resp.content_type == CONTENT_TYPE_APP_JSON, msg.format(i, resp.content_type)
            msg = "Killed test '{}' request taking too long using:\n{}".format(i, data_json)
            assert timeout.state == timeout.EXECUTED, msg

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
            assert job.inputs[0]["data"] == "100", "Input value should remain string and not be cast to float/integer"

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
        path = "/processes/{}/jobs".format(self.process_public.identifier)
        resp = self.app.post_json(path, params=execute_data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 501
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    @pytest.mark.xfail(reason="Mode '{}' not supported for job execution.".format(EXECUTE_TRANSMISSION_MODE_VALUE))
    def test_execute_process_transmission_mode_value_not_supported(self):
        execute_data = self.get_process_execute_template(fully_qualified_name(self))
        execute_data["outputs"][0]["transmissionMode"] = EXECUTE_TRANSMISSION_MODE_VALUE
        path = "/processes/{}/jobs".format(self.process_public.identifier)
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_process():
                stack_exec.enter_context(mock_exec)
            resp = self.app.post_json(path, params=execute_data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 501
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_execute_process_not_visible(self):
        path = "/processes/{}/jobs".format(self.process_private.identifier)
        data = self.get_process_execute_template()
        resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_get_process_visibility_expected_response(self):
        for http_code, wps_process in [(403, self.process_private), (200, self.process_public)]:
            process = self.process_store.fetch_by_id(wps_process.identifier)
            path = "/processes/{}/visibility".format(process.identifier)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == http_code
            assert resp.content_type == CONTENT_TYPE_APP_JSON
            if http_code == 200:
                assert resp.json["value"] == process.visibility
            else:
                assert "value" not in resp.json

    def test_get_process_visibility_not_found(self):
        path = "/processes/{}/visibility".format(self.fully_qualified_test_process_name())
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_set_process_visibility_success(self):
        test_process = self.process_private.identifier
        path_describe = "/processes/{}?schema=OLD".format(test_process)
        path_visibility = "{}/visibility".format(path_describe)

        # validate cannot be found before
        resp = self.app.get(path_describe, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403

        # make public
        data = {"value": VISIBILITY_PUBLIC}
        resp = self.app.put_json(path_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert resp.json["value"] == VISIBILITY_PUBLIC

        # validate now visible and found
        resp = self.app.get(path_describe, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.json["process"]["id"] == test_process

        # make private
        data = {"value": VISIBILITY_PRIVATE}
        resp = self.app.put_json(path_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == CONTENT_TYPE_APP_JSON
        assert resp.json["value"] == VISIBILITY_PRIVATE

        # validate cannot be found anymore
        resp = self.app.get(path_describe, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403

    def test_set_process_visibility_bad_formats(self):
        path = "/processes/{}/visibility".format(self.process_private.identifier)
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
            resp = self.app.put_json(path, params=data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code in [400, 422]
            assert resp.content_type == CONTENT_TYPE_APP_JSON

        # bad method POST
        data = {"value": VISIBILITY_PUBLIC}
        resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 405
        assert resp.content_type == CONTENT_TYPE_APP_JSON

    def test_process_description_metadata_href_or_value_valid(self):
        """Validates that metadata is accepted as either hyperlink reference or literal string value."""
        process = {
            "id": self._testMethodName,
            "metadata": [
                {"type": "value-typed", "value": "some-value", "lang": "en-US"},
                {"type": "link-typed", "href": "https://example.com", "hreflang": "en-US", "rel": "example"}
            ],
            "inputs": [],
            "outputs": [],
        }
        result = sd.Process().deserialize(process)
        assert process["metadata"] == result["metadata"]

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
                self.fail("Metadata is expected to be raised as invalid: (test: {}, metadata: {})".format(i, meta))
