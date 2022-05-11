# pylint: disable=R1729  # ignore non-generator representation employed for displaying test log results

import base64
import contextlib
import copy
import json
import os
import tempfile
import unittest
from copy import deepcopy
from typing import TYPE_CHECKING

import colander
import pyramid.testing
import pytest
import stopit

from tests import resources
from tests.utils import (
    get_links,
    get_test_weaver_app,
    mocked_execute_celery,
    mocked_process_job_runner,
    mocked_process_package,
    mocked_remote_server_requests_wps1,
    mocked_wps_output,
    setup_config_with_mongodb,
    setup_mongodb_jobstore,
    setup_mongodb_processstore,
    setup_mongodb_servicestore
)
from weaver import WEAVER_ROOT_DIR
from weaver.datatype import AuthenticationTypes, Process, Service
from weaver.exceptions import JobNotFound, ProcessNotFound
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import AcceptLanguage, ContentType, get_cwl_file_format
from weaver.processes.constants import CWL_REQUIREMENT_APP_WPS1, ProcessSchema
from weaver.processes.wps_testing import WpsTestProcess
from weaver.status import Status
from weaver.utils import fully_qualified_name, get_path_kvp, load_file, ows_context_href
from weaver.visibility import Visibility
from weaver.wps.utils import get_wps_url
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Optional

    from weaver.processes.constants import ProcessSchemaType
    from weaver.typedefs import CWL, JSON


# pylint: disable=C0103,invalid-name
class WpsRestApiProcessesTest(unittest.TestCase):
    remote_server = None
    settings = None
    config = None

    @classmethod
    def setUpClass(cls):
        cls.settings = {
            "weaver.url": "https://localhost",
            "weaver.wps_path": "/ows/wps",
        }
        cls.config = setup_config_with_mongodb(settings=cls.settings)
        cls.app = get_test_weaver_app(config=cls.config)
        cls.json_headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def fully_qualified_test_process_name(self):
        return (fully_qualified_name(self) + "-" + self._testMethodName).replace(".", "-")

    def setUp(self):
        # rebuild clean db on each test
        self.service_store = setup_mongodb_servicestore(self.config)
        self.process_store = setup_mongodb_processstore(self.config)
        self.job_store = setup_mongodb_jobstore(self.config)

        self.remote_server = "local"
        self.process_remote_WPS1 = "process_remote_wps1"
        self.process_remote_WPS3 = "process_remote_wps3"
        self.process_public = WpsTestProcess(identifier="process_public")
        self.process_private = WpsTestProcess(identifier="process_private")
        self.process_store.save_process(self.process_public)
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_public.identifier, Visibility.PUBLIC)
        self.process_store.set_visibility(self.process_private.identifier, Visibility.PRIVATE)

    def get_process_deploy_template(self, process_id=None, cwl=None, schema=ProcessSchema.OLD):
        # type: (Optional[str], Optional[CWL], ProcessSchemaType) -> JSON
        """
        Provides deploy process bare minimum template with undefined execution unit.

        To be used in conjunction with :meth:`get_application_package` and :meth:`validate_wps1_package`
        to avoid extra package content-specific validations.
        """
        if not process_id:
            process_id = self.fully_qualified_test_process_name()
        body = {
            "processDescription": {},
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            "executionUnit": []
        }
        meta = {
            "id": process_id,
            "title": f"Test process '{process_id}'.",
        }
        if schema == ProcessSchema.OLD:
            body["processDescription"]["process"] = meta
        else:
            body["processDescription"].update(meta)
        if cwl:
            body["executionUnit"].append({"unit": cwl})
        else:
            # full definition not required with mock
            # use 'href' variant to avoid invalid schema validation via more explicit 'unit'
            # note:
            #   hostname cannot have underscores according to [RFC-1123](https://www.ietf.org/rfc/rfc1123.txt)
            #   schema validator of Reference URL will appropriately raise such invalid string
            body["executionUnit"].append({"href": f"http://weaver.test/{process_id}.cwl"})
        return body

    @staticmethod
    def get_process_execute_template(test_input="not-specified"):
        """
        Provides execute process bare minimum template definition.

        Contents correspond to required I/O for WPS process :class:`weaver.processes.wps_testing.WpsTestProcess`.
        """
        return {
            "inputs": [
                {"id": "test_input",
                 "data": test_input},
            ],
            "outputs": [
                {"id": "test_output",
                 "transmissionMode": ExecuteTransmissionMode.VALUE}
            ],
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
        }

    def test_get_processes(self):
        path = "/processes"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "processes" in resp.json
        assert isinstance(resp.json["processes"], list) and len(resp.json["processes"]) > 0
        for process in resp.json["processes"]:
            assert "id" in process and isinstance(process["id"], str)
            assert "title" in process and isinstance(process["title"], str)
            assert "version" in process and isinstance(process["version"], str)
            assert "keywords" in process and isinstance(process["keywords"], list)
            assert "metadata" in process and isinstance(process["metadata"], list)
            assert len(process["jobControlOptions"]) == 1
            assert ExecuteControlOption.ASYNC in process["jobControlOptions"]

        processes_id = [p["id"] for p in resp.json["processes"]]
        assert self.process_public.identifier in processes_id
        assert self.process_private.identifier not in processes_id

    def test_get_processes_with_paging(self):
        test_prefix = "test-proc-temp"
        for i in range(10):
            p_id = f"{test_prefix}-{i}"
            proc = self.process_private = Process(id=p_id, package={}, visibility=Visibility.PUBLIC)
            self.process_store.save_process(proc)
        _, total = self.process_store.list_processes(total=True, visibility=Visibility.PUBLIC)
        assert 10 < total < 15, "cannot run process paging test with current number of processes"
        limit = 5  # some value to get 3 pages, 2 full and the last partial
        remain = total - (2 * limit)
        limit_kvp = f"limit={limit}"

        path = get_path_kvp("/processes", page=1, limit=limit)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "processes" in resp.json
        processes = resp.json["processes"]
        assert isinstance(processes, list)
        assert resp.json["total"] == total

        base_url = self.settings["weaver.url"]
        proc_url = base_url + "/processes"
        assert len(resp.json["processes"]) == limit
        assert "links" in resp.json
        links = get_links(resp.json["links"])
        assert links["collection"] == proc_url
        assert links["search"] == proc_url
        assert links["up"] == base_url
        assert links["current"].startswith(proc_url) and limit_kvp in links["current"] and "page=1" in links["current"]
        assert links["prev"].startswith(proc_url) and limit_kvp in links["prev"] and "page=0" in links["prev"]
        assert links["next"].startswith(proc_url) and limit_kvp in links["next"] and "page=2" in links["next"]
        assert links["first"].startswith(proc_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(proc_url) and limit_kvp in links["last"] and "page=2" in links["last"]

        path = get_path_kvp("/processes", page=0, limit=limit)
        resp = self.app.get(path, headers=self.json_headers)
        assert len(resp.json["processes"]) == limit
        assert "links" in resp.json
        links = get_links(resp.json["links"])
        assert links["collection"] == proc_url
        assert links["search"] == proc_url
        assert links["up"] == base_url
        assert links["current"].startswith(proc_url) and limit_kvp in links["current"] and "page=0" in links["current"]
        assert links["prev"] is None
        assert links["next"].startswith(proc_url) and limit_kvp in links["next"] and "page=1" in links["next"]
        assert links["first"].startswith(proc_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(proc_url) and limit_kvp in links["last"] and "page=2" in links["last"]

        path = get_path_kvp("/processes", page=2, limit=limit)
        resp = self.app.get(path, headers=self.json_headers)
        assert len(resp.json["processes"]) == remain, "Last page should have only remaining processes."
        assert "links" in resp.json
        links = get_links(resp.json["links"])
        assert links["collection"] == proc_url
        assert links["search"] == proc_url
        assert links["up"] == base_url
        assert links["current"].startswith(proc_url) and limit_kvp in links["current"] and "page=2" in links["current"]
        assert links["prev"].startswith(proc_url) and limit_kvp in links["prev"] and "page=1" in links["prev"]
        assert links["next"] is None
        assert links["first"].startswith(proc_url) and limit_kvp in links["first"] and "page=0" in links["first"]
        assert links["last"].startswith(proc_url) and limit_kvp in links["last"] and "page=2" in links["last"]

    def test_get_processes_page_out_of_range(self):
        # ensure we have few items to list
        for i in range(10):
            proc = Process(id=f"test-process-paging-{i}", package={}, visibility=Visibility.PUBLIC)
            self.process_store.save_process(proc)
        resp = self.app.get(sd.processes_service.path, headers=self.json_headers)
        total = resp.json["total"]
        limit = total // 2
        max_limit = 1 if 2 * limit == total else 2  # exact match or last page remainder
        bad_page = 4

        path = get_path_kvp(sd.processes_service.path, page=bad_page, limit=limit)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert "IndexError" in resp.json["error"]
        assert f"[0,{max_limit}]" in resp.json["description"]
        assert "page" in resp.json["value"] and resp.json["value"]["page"] == bad_page

        # note:
        #   Following errors are generated by schema validators (page min=0, limit min=1) rather than above explicit
        #   checks. They don't provide the range because the error can apply to more than just paging failing value
        #   is still explicitly reported though. Because comparisons happen at query param level, it reports str values.

        path = get_path_kvp(sd.processes_service.path, page=-1, limit=limit)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["code"] == "ProcessInvalidParameter"
        assert "page" in str(resp.json["cause"]) and "less than minimum" in str(resp.json["cause"])
        assert "page" in resp.json["value"] and resp.json["value"]["page"] == str(-1)

        path = get_path_kvp(sd.processes_service.path, page=0, limit=0)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.json["code"] == "ProcessInvalidParameter"
        assert "limit" in str(resp.json["cause"]) and "less than minimum" in str(resp.json["cause"])
        assert "limit" in resp.json["value"] and resp.json["value"]["limit"] == str(0)

    def test_get_processes_bad_request_paging_providers(self):
        path = get_path_kvp("/processes", page=0, limit=10, providers=True)
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert "ListingInvalidParameter" in resp.json["error"]

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_get_processes_with_providers(self):
        test_svc_id = "test-provider-processes-listing"
        test_svc = Service(name=test_svc_id, url=resources.TEST_REMOTE_SERVER_URL)
        self.service_store.save_service(test_svc)
        _, total = self.process_store.list_processes(total=True, visibility=Visibility.PUBLIC)

        path = get_path_kvp("/processes", providers=True, detail=False)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert "processes" in resp.json and isinstance(resp.json["processes"], list)
        assert "providers" in resp.json and isinstance(resp.json["providers"], list)
        assert all(isinstance(proc, str) for proc in resp.json["processes"])
        assert all(isinstance(prov, dict) for prov in resp.json["providers"])
        assert len(resp.json["processes"]) == total
        assert len(resp.json["providers"]) == 1
        prov = resp.json["providers"][0]
        assert "id" in prov and prov["id"] == test_svc_id
        assert "processes" in prov and isinstance(prov["processes"], list)
        assert all(isinstance(proc, str) for proc in prov["processes"])
        assert len(prov["processes"]) == 2  # number of descriptions in TEST_REMOTE_PROCESS_GETCAP_WPS1_XML
        assert set(prov["processes"]) == {"pavicstestdocs", "test-remote-process-wps1"}
        assert resp.json["total"] == total + 2, "Grand total of local+remote processes should be reported."

    # register valid server here, and another invalid within test
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_get_processes_with_providers_error_servers(self, mock_responses):
        # register service reachable but returning invalid XML
        invalid_id = "test-provider-process-listing-invalid"
        invalid_url = resources.TEST_REMOTE_SERVER_URL + "/invalid"
        invalid_data = "<xml> not a wps </xml>"
        mocked_remote_server_requests_wps1([invalid_url, invalid_data, []], mock_responses, data=True)

        # register a provider that doesn't have any responding server
        missing_id = "test-provider-process-listing-missing"
        missing_url = resources.TEST_REMOTE_SERVER_URL + "/does-not-exist"

        valid_id = "test-provider-process-listing-valid"
        self.service_store.clear_services()
        self.service_store.save_service(Service(name=valid_id, url=resources.TEST_REMOTE_SERVER_URL))
        self.service_store.save_service(Service(name=invalid_id, url=invalid_url))
        self.service_store.save_service(Service(name=missing_id, url=missing_url))

        # with ignore flag and no detail, failing providers are not validated and operation returns successfully
        # - servers that respond successfully with any content are kept (even if not valid WPS)
        # - servers without responses (cannot ping) are dropped from response
        path = get_path_kvp("/processes", providers=True, detail=False, ignore=True)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert "providers" in resp.json
        assert len(resp.json["providers"]) == 2
        providers = [prov["id"] for prov in resp.json["providers"]]
        assert set(providers) == {valid_id, invalid_id}
        valid_processes = resp.json["providers"][providers.index(valid_id)]["processes"]
        invalid_processes = resp.json["providers"][providers.index(invalid_id)]["processes"]
        assert set(valid_processes) == {"pavicstestdocs", "test-remote-process-wps1"}
        assert invalid_processes == []

        # with ignore and detail requested, providers must be parsed to obtain the extra metadata
        # invalid parsing should now also be dropped and return successfully with only the valid provider
        path = get_path_kvp("/processes", providers=True, detail=True, ignore=True)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert len(resp.json["providers"]) == 1
        assert resp.json["providers"][0]["id"] == valid_id
        prov_proc_info = resp.json["providers"][0]["processes"]
        assert all(isinstance(proc, dict) for proc in prov_proc_info)
        expected_fields = ["id", "title", "version", "description", "keywords", "metadata", "executeEndpoint"]
        assert all([all([field in proc for field in expected_fields]) for proc in prov_proc_info])
        prov_proc_id = [proc["id"] for proc in prov_proc_info]
        assert set(prov_proc_id) == {"pavicstestdocs", "test-remote-process-wps1"}

        # with ignore disabled, regardless of detail flag, error should be raised instead
        # whole listing fails because at least one provider cannot be generated properly
        for detail in [True, False]:
            path = get_path_kvp("/processes", providers=True, detail=detail, ignore=False)
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 503, "Parsing error should mark service as unavailable."

    def test_set_jobControlOptions_async_execute(self):
        path = "/processes"
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        process_data["processDescription"]["jobControlOptions"] = [ExecuteControlOption.ASYNC]
        package_mock = mocked_process_package()
        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201
            assert resp.json["processSummary"]["id"] == process_name

        process = self.process_store.fetch_by_id(process_name)
        assert ExecuteControlOption.ASYNC in process["jobControlOptions"]

    def test_set_jobControlOptions_sync_execute(self):
        path = "/processes"
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        process_data["processDescription"]["jobControlOptions"] = [ExecuteControlOption.SYNC]
        package_mock = mocked_process_package()
        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 201
            assert resp.json["processSummary"]["id"] == process_name

        process = self.process_store.fetch_by_id(process_name)
        assert ExecuteControlOption.SYNC in process["jobControlOptions"]

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
        process["version"] = "random"  # invalid (cannot use any property that executes in-place fixes)
        process["visibility"] = Visibility.PUBLIC
        self.process_store.save_process(process, overwrite=True)

        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 503
        assert resp.content_type == ContentType.APP_JSON
        assert process_name in resp.json.get("description")

    def test_describe_process_visibility_public(self):
        path = f"/processes/{self.process_public.identifier}"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON

    def test_describe_process_visibility_private(self):
        path = f"/processes/{self.process_private.identifier}"
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == ContentType.APP_JSON

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
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["processSummary"]["id"] == process_name
            assert isinstance(resp.json["deploymentDone"], bool) and resp.json["deploymentDone"]

    def test_deploy_process_ogc_schema(self):
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name, schema=ProcessSchema.OGC)
        process_desc = process_data["processDescription"]
        package_mock = mocked_process_package()

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            assert "process" not in process_desc
            assert "id" in process_desc
            process_desc["visibility"] = Visibility.PUBLIC  # save ourself an update request
            path = "/processes"
            resp = self.app.post_json(path, params=process_data, headers=self.json_headers)
            assert resp.status_code == 201
            assert resp.content_type == ContentType.APP_JSON
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
            assert resp.content_type == ContentType.APP_JSON

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
            assert resp.content_type == ContentType.APP_JSON

    def test_deploy_process_missing_or_invalid_components(self):
        process_name = self.fully_qualified_test_process_name()
        process_data = self.get_process_deploy_template(process_name)
        package_mock = mocked_process_package()

        # remove components for testing different cases
        process_data_tests = [deepcopy(process_data) for _ in range(13)]
        process_data_tests[0].pop("processDescription")
        process_data_tests[1]["processDescription"].pop("process")
        process_data_tests[2]["processDescription"]["process"].pop("id")  # noqa
        process_data_tests[3]["processDescription"]["jobControlOptions"] = ExecuteControlOption.ASYNC
        process_data_tests[4]["processDescription"]["jobControlOptions"] = [ExecuteMode.ASYNC]  # noqa
        process_data_tests[5]["deploymentProfileName"] = "random"  # can be omitted, but if provided, must be valid
        process_data_tests[6].pop("executionUnit")
        process_data_tests[7]["executionUnit"] = {}
        process_data_tests[8]["executionUnit"] = []
        process_data_tests[9]["executionUnit"][0] = {"unit": "something"}  # unit as string instead of package
        process_data_tests[10]["executionUnit"][0] = {"href": {}}  # noqa  # href as package instead of URL
        process_data_tests[11]["executionUnit"][0] = {"unit": {}, "href": ""}  # can't have both unit/href together
        process_data_tests[12]["executionUnit"][0] = {"href": ""}  # href correct type, but missing link reference

        with contextlib.ExitStack() as stack:
            for pkg in package_mock:
                stack.enter_context(pkg)
            path = "/processes"
            for i, data in enumerate(process_data_tests):
                resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=True)
                msg = "Failed with test variation '{}' with value '{}' using data:\n{}"
                assert resp.status_code in [400, 422], msg.format(i, resp.status_code, json.dumps(data, indent=2))
                assert resp.content_type == ContentType.APP_JSON, msg.format(i, resp.content_type, "")

    def test_deploy_process_default_endpoint_wps1(self):
        """
        Validates that the default (localhost) endpoint to execute WPS requests are saved during deployment.
        """
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
        proc = response_json["process"]
        assert expected_process_id in proc["id"]
        assert len(proc["inputs"]) == 1
        assert proc["inputs"][0]["id"] == "input-1"
        assert proc["inputs"][0]["minOccurs"] == 1
        assert proc["inputs"][0]["maxOccurs"] == 1
        assert "formats" not in proc["inputs"][0]   # literal data doesn't have "formats"
        assert len(proc["outputs"]) == 1
        assert proc["outputs"][0]["id"] == "output"
        assert "minOccurs" not in proc["outputs"][0]
        assert "maxOccurs" not in proc["outputs"][0]
        # TODO: handling multiple outputs (https://github.com/crim-ca/weaver/issues/25)
        # assert proc["outputs"][0]["minOccurs"] == "1"
        # assert proc["outputs"][0]["maxOccurs"] == "1"
        assert isinstance(proc["outputs"][0]["formats"], list)
        assert len(proc["outputs"][0]["formats"]) == 1
        assert proc["outputs"][0]["formats"][0]["mediaType"] == ContentType.APP_JSON

    def deploy_process_make_visible_and_fetch_deployed(self, deploy_payload, expected_process_id):
        """
        Deploy, make visible and obtain process description.

        Attempts to deploy the process using the provided deployment payload, then makes it visible and finally
        fetches the deployed process to validate the resulting WPS-3 REST JSON description.
        Any failure along the way is raised, ensuring that returned data corresponds to a process ready for execution.

        .. note::
            This is a shortcut method for all ``test_deploy_process_<>`` cases.
        """
        resp = self.app.post_json("/processes", params=deploy_payload, headers=self.json_headers)
        assert resp.status_code == 201
        assert resp.content_type == ContentType.APP_JSON

        # apply visibility to allow retrieval
        proc_id = resp.json["processSummary"]["id"]  # process id could have been cleaned up
        proc_url = f"/processes/{proc_id}"
        vis_url = f"{proc_url}/visibility"
        body = {"value": Visibility.PUBLIC}
        resp = self.app.put_json(vis_url, params=body, headers=self.json_headers)
        assert resp.status_code == 200

        proc_query = {"schema": ProcessSchema.OLD}
        resp = self.app.get(proc_url, params=proc_query, headers=self.json_headers)
        assert resp.status_code == 200
        self.assert_deployed_wps3(resp.json, expected_process_id)
        return resp.json

    def get_application_package(self, process_id):
        resp = self.app.get(f"/processes/{process_id}/package", headers=self.json_headers)
        assert resp.status_code == 200
        return resp.json

    def validate_wps1_package(self, process_id, provider_url):
        cwl = self.get_application_package(process_id)
        assert "hints" in cwl and CWL_REQUIREMENT_APP_WPS1 in cwl["hints"]
        assert "process" in cwl["hints"][CWL_REQUIREMENT_APP_WPS1]
        assert "provider" in cwl["hints"][CWL_REQUIREMENT_APP_WPS1]
        assert cwl["hints"][CWL_REQUIREMENT_APP_WPS1]["process"] == process_id
        if provider_url.endswith("/"):
            valid_urls = [provider_url, provider_url[:-1]]
        else:
            valid_urls = [provider_url, provider_url + "/"]
        assert cwl["hints"][CWL_REQUIREMENT_APP_WPS1]["provider"] in valid_urls

    def test_deploy_process_CWL_DockerRequirement_auth_header_format(self):
        """
        Test deployment ofa process with authentication to access the referenced repository.

        .. note::
            Use same definition as the one provided in :ref:`app_pkg_script` documentation.
        """
        cwl = load_file(os.path.join(WEAVER_ROOT_DIR, "docs/examples/docker-shell-script-cat.cwl"))  # type: CWL
        docker = "fake.repo/org/private-image:latest"
        cwl["requirements"]["DockerRequirement"]["dockerPull"] = docker
        body = self.get_process_deploy_template(cwl=cwl)
        headers = copy.deepcopy(self.json_headers)

        for bad_token in ["0123456789", "Basic:0123456789", "Bearer fake:0123456789"]:  # nosec
            headers.update({"X-Auth-Docker": bad_token})
            resp = self.app.post_json("/processes", params=body, headers=headers, expect_errors=True)
            assert resp.status_code == 422
            assert resp.content_type == ContentType.APP_JSON
            assert "authentication header" in resp.json["description"]

        token = base64.b64encode(b"fake:0123456789").decode("utf-8")  # nosec
        headers.update({"X-Auth-Docker": f"Basic {token}"})  # nosec
        resp = self.app.post_json("/processes", params=body, headers=headers)
        assert resp.status_code == 201
        proc_id = body["processDescription"]["process"]["id"]  # noqa
        process = self.process_store.fetch_by_id(proc_id)
        assert process.auth is not None
        assert process.auth.type == AuthenticationTypes.DOCKER
        assert process.auth.token == token
        assert process.auth.docker == docker

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

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_deploy_process_CWL_WPS1Requirement_href(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            out_dir = self.settings["weaver.wps_output_dir"]
            out_url = self.settings["weaver.wps_output_url"]
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory(dir=out_dir))
            tmp_file = os.path.join(tmp_dir, "wps1.cwl")
            tmp_href = tmp_file.replace(out_dir, out_url, 1)
            ns, fmt = get_cwl_file_format(ContentType.APP_JSON)
            with open(tmp_file, mode="w", encoding="utf-8") as cwl_file:
                json.dump({
                    "cwlVersion": "v1.0",
                    "class": "CommandLineTool",
                    "hints": {
                        CWL_REQUIREMENT_APP_WPS1: {
                            "process": resources.TEST_REMOTE_PROCESS_WPS1_ID,
                            "provider": resources.TEST_REMOTE_SERVER_URL
                        }
                    },
                    # FIXME: must provide inputs/outputs since CWL provided explicitly.
                    #   Update from CWL->WPS complementary details is supported.
                    #   Inverse update WPS->CWL is not supported (https://github.com/crim-ca/weaver/issues/50).
                    # following are based on expected results for I/O defined in XML
                    "inputs": {
                        "input-1": {
                            "type": "string"
                        },
                    },
                    "outputs": {
                        "output": {
                            "type": "File",
                            "format": fmt,
                            "outputBinding": {
                                "glob": "*.json"
                            },
                        }
                    },
                    "$namespace": ns
                }, cwl_file)

            body = {
                "processDescription": {"process": {"id": resources.TEST_REMOTE_PROCESS_WPS1_ID}},
                "executionUnit": [{"href": tmp_href}],
                # FIXME: avoid error on omitted deploymentProfileName (https://github.com/crim-ca/weaver/issues/319)
                "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            }
            self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)
            self.validate_wps1_package(
                resources.TEST_REMOTE_PROCESS_WPS1_ID,
                resources.TEST_REMOTE_SERVER_URL
            )

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_deploy_process_CWL_WPS1Requirement_owsContext(self):
        ns, fmt = get_cwl_file_format(ContentType.APP_JSON)
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "hints": {
                CWL_REQUIREMENT_APP_WPS1: {
                    "process": resources.TEST_REMOTE_PROCESS_WPS1_ID,
                    "provider": resources.TEST_REMOTE_SERVER_URL
                }
            },
            # FIXME: must provide inputs/outputs since CWL provided explicitly.
            #   Update from CWL->WPS complementary details is supported.
            #   Inverse update WPS->CWL is not supported (https://github.com/crim-ca/weaver/issues/50).
            # following are based on expected results for I/O defined in XML
            "inputs": {
                "input-1": {
                    "type": "string"
                },
            },
            "outputs": {
                "output": {
                    "type": "File",
                    "format": fmt,
                    "outputBinding": {
                        "glob": "*.json"
                    },
                }
            },
            "$namespace": ns
        }
        with contextlib.ExitStack() as stack:
            stack.enter_context(mocked_wps_output(self.settings))
            wps_dir = self.settings["weaver.wps_output_dir"]
            wps_url = self.settings["weaver.wps_output_url"]
            tmp_file = stack.enter_context(tempfile.NamedTemporaryFile(dir=wps_dir, mode="w", suffix=".cwl"))
            tmp_http = tmp_file.name.replace(wps_dir, wps_url, 1)
            json.dump(cwl, tmp_file)
            tmp_file.flush()
            tmp_file.seek(0)

            body = {
                "processDescription": {"process": {
                    "id": resources.TEST_REMOTE_PROCESS_WPS1_ID,
                }},
                "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}],  # just to fulfill schema validation
                # FIXME: avoid error on omitted deploymentProfileName (https://github.com/crim-ca/weaver/issues/319)
                "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            }
            ows_ctx = ows_context_href(tmp_http)
            body["processDescription"]["process"].update(ows_ctx)
            self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)
            self.validate_wps1_package(
                resources.TEST_REMOTE_PROCESS_WPS1_ID,
                resources.TEST_REMOTE_SERVER_URL
            )

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_deploy_process_CWL_WPS1Requirement_executionUnit(self):
        ns, fmt = get_cwl_file_format(ContentType.APP_JSON)
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "hints": {
                CWL_REQUIREMENT_APP_WPS1: {
                    "process": resources.TEST_REMOTE_PROCESS_WPS1_ID,
                    "provider": resources.TEST_REMOTE_SERVER_URL
                }
            },
            # FIXME: must provide inputs/outputs since CWL provided explicitly.
            #   Update from CWL->WPS complementary details is supported.
            #   Inverse update WPS->CWL is not supported (https://github.com/crim-ca/weaver/issues/50).
            # following are based on expected results for I/O defined in XML
            "inputs": {
                "input-1": {
                    "type": "string"
                },
            },
            "outputs": {
                "output": {
                    "type": "File",
                    "format": fmt,
                    "outputBinding": {
                        "glob": "*.json"
                    },
                }
            },
            "$namespace": ns
        }
        body = {
            "processDescription": {"process": {
                "id": resources.TEST_REMOTE_PROCESS_WPS1_ID,
            }},
            "executionUnit": [{"unit": cwl}],
            # FIXME: avoid error on omitted deploymentProfileName (https://github.com/crim-ca/weaver/issues/319)
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)
        self.validate_wps1_package(
            resources.TEST_REMOTE_PROCESS_WPS1_ID,
            resources.TEST_REMOTE_SERVER_URL
        )

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_deploy_process_WPS1_DescribeProcess_href(self):
        body = {
            "processDescription": {"href": resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL},  # this one should be used
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)
        self.validate_wps1_package(
            resources.TEST_REMOTE_PROCESS_WPS1_ID,
            resources.TEST_REMOTE_SERVER_URL
        )

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_deploy_process_WPS1_DescribeProcess_owsContext(self):
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        body["processDescription"]["process"].update(ows_context_href(resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL))
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_deploy_process_WPS1_DescribeProcess_executionUnit(self):
        """
        Test process deployment using a WPS-1 DescribeProcess URL specified as an execution unit reference.
        """
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)
        self.validate_wps1_package(
            resources.TEST_REMOTE_PROCESS_WPS1_ID,
            resources.TEST_REMOTE_SERVER_URL
        )

    @pytest.mark.skip(reason="not implemented")
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_deploy_process_WPS1_GetCapabilities_href(self):
        """
        Test process deployment using a WPS-1 GetCapabilities URL specified as process description reference.
        """
        body = {
            "processDescription": {"href": resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_URL},  # this one should be used
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)

    @pytest.mark.skip(reason="not implemented")
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_deploy_process_WPS1_GetCapabilities_owsContext(self):
        """
        Test process deployment using a WPS-1 GetCapabilities URL specified through the OwsContext definition.
        """
        body = {
            "processDescription": {"process": {"id": resources.TEST_REMOTE_PROCESS_WPS1_ID}},
            "executionUnit": [{"href": resources.TEST_REMOTE_SERVER_URL}]  # some URL just to fulfill schema validation
        }
        body["processDescription"]["process"].update(ows_context_href(resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_URL))
        self.deploy_process_make_visible_and_fetch_deployed(body, resources.TEST_REMOTE_PROCESS_WPS1_ID)

    @pytest.mark.skip(reason="not implemented")
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_PROCESS_GETCAP_WPS1_XML,
        [resources.TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML],
    ])
    def test_deploy_process_WPS1_GetCapabilities_executionUnit(self):
        """
        Test process deployment using a WPS-1 GetCapabilities URL specified through the ExecutionUnit parameter.
        """
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
        path = f"/processes/{self.process_public.identifier}"
        resp = self.app.delete_json(path, headers=self.json_headers)
        assert resp.status_code == 200, f"Error: {resp.text}"
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["identifier"] == self.process_public.identifier
        assert isinstance(resp.json["undeploymentDone"], bool) and resp.json["undeploymentDone"]
        with pytest.raises(ProcessNotFound):
            self.process_store.fetch_by_id(self.process_public.identifier)

    def test_delete_process_not_accessible(self):
        path = f"/processes/{self.process_private.identifier}"
        resp = self.app.delete_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403, f"Error: {resp.text}"
        assert resp.content_type == ContentType.APP_JSON

    def test_delete_process_not_found(self):
        name = self.fully_qualified_test_process_name()
        path = f"/processes/{name}"
        resp = self.app.delete_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404, f"Error: {resp.text}"
        assert resp.content_type == ContentType.APP_JSON

    def test_delete_process_bad_name(self):
        name = self.fully_qualified_test_process_name() + "..."
        path = f"/processes/{name}"
        resp = self.app.delete_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400, f"Error: {resp.text}"
        assert resp.content_type == ContentType.APP_JSON

    def test_execute_process_success(self):
        path = f"/processes/{self.process_public.identifier}/jobs"
        data = self.get_process_execute_template()
        task = f"job-{fully_qualified_name(self)}"
        mock_execute = mocked_process_job_runner(task)

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            resp = self.app.post_json(path, params=data, headers=self.json_headers)
            assert resp.status_code == 201, f"Error: {resp.text}"
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["location"].endswith(resp.json["jobID"])
            assert resp.headers["Location"] == resp.json["location"]
            try:
                job = self.job_store.fetch_by_id(resp.json["jobID"])
            except JobNotFound:
                self.fail("Job should have been created and be retrievable.")
            assert str(job.id) == resp.json["jobID"]
            assert job.task_id == Status.ACCEPTED  # temporary value until processed by celery

    def test_execute_process_language(self):
        path = f"/processes/{self.process_public.identifier}/jobs"
        data = self.get_process_execute_template()
        task = f"job-{fully_qualified_name(self)}"
        mock_execute = mocked_process_job_runner(task)

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            headers = self.json_headers.copy()
            headers["Accept-Language"] = AcceptLanguage.FR_CA
            resp = self.app.post_json(path, params=data, headers=headers)
            assert resp.status_code == 201, f"Error: {resp.text}"
            try:
                job = self.job_store.fetch_by_id(resp.json["jobID"])
            except JobNotFound:
                self.fail("Job should have been created and be retrievable.")
            assert str(job.id) == resp.json["jobID"]
            assert job.accept_language == AcceptLanguage.FR_CA

    def test_execute_process_no_json_body(self):
        path = f"/processes/{self.process_public.identifier}/jobs"
        resp = self.app.post_json(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == ContentType.APP_JSON

    def test_execute_process_missing_required_params(self):
        """
        Validate execution against missing parameters.

        .. versionchanged:: 4.15.0
            Multiple parameters are not **required** anymore because the alternative with ``Prefer`` header
            for :term:`OGC API - Processes` compliance is permitted. When the values are specified through,
            they should still be validated to provide relevant error details to the user.
        """
        execute_data = self.get_process_execute_template(fully_qualified_name(self))

        # remove components for testing different cases
        execute_data_tests = [[True, deepcopy(execute_data)] for _ in range(7)]
        execute_data_tests[0][0] = False
        execute_data_tests[0][1].pop("outputs")
        execute_data_tests[1][0] = False
        execute_data_tests[1][1].pop("mode")
        execute_data_tests[2][0] = False
        execute_data_tests[2][1].pop("response")
        execute_data_tests[3][1]["mode"] = "random"
        execute_data_tests[4][1]["response"] = "random"
        execute_data_tests[5][1]["inputs"] = [{"test_input": "test_value"}]  # noqa  # bad format on purpose
        execute_data_tests[6][1]["outputs"] = [{"id": "test_output", "transmissionMode": "random"}]

        def no_op(*_, **__):
            return Status.SUCCEEDED

        path = f"/processes/{self.process_public.identifier}/jobs"
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery(func_execute_task=no_op):
                stack_exec.enter_context(mock_exec)
            for i, (is_invalid, exec_data) in enumerate(execute_data_tests):
                data_json = json.dumps(exec_data, indent=2)
                try:
                    # timeout to kill execution if schema validation did not raise
                    with stopit.ThreadingTimeout(3) as timeout:
                        resp = self.app.post_json(path, params=exec_data, headers=self.json_headers, expect_errors=True)
                        msg = "Failed with test variation '{}' with status '{}' using:\n{}"
                        code = [400, 422] if is_invalid else [201]
                        assert resp.status_code in code, msg.format(i, resp.status_code, data_json)
                        assert resp.content_type == ContentType.APP_JSON, msg.format(i, resp.content_type)
                except stopit.TimeoutException:
                    # if required, not normal to have passed validation
                    # if optional, valid since omitting field does not raise missing field in schema
                    if is_invalid:
                        msg = f"Killed test '{i}' request taking too long using:\n{data_json}"
                        assert timeout.state == timeout.EXECUTED, msg

    def test_execute_process_dont_cast_one_of(self):
        """
        When validating the schema for OneOf values, don't cast the result to the first valid schema.
        """
        # get basic mock/data templates
        name = fully_qualified_name(self)
        execute_mock_data_tests = []

        mock_execute = mocked_process_job_runner(f"job-{name}")
        data_execute = self.get_process_execute_template("100")
        execute_mock_data_tests.append((mock_execute, data_execute))

        with contextlib.ExitStack() as stack:
            for exe in mock_execute:
                stack.enter_context(exe)
            path = f"/processes/{self.process_public.identifier}/jobs"
            resp = self.app.post_json(path, params=data_execute, headers=self.json_headers)
            assert resp.status_code == 201, "Expected job submission without inputs created without error."
            job = self.job_store.fetch_by_id(resp.json["jobID"])
            assert job.inputs[0]["data"] == "100", "Input value should remain string and not be cast to float/integer"

    def test_execute_process_no_error_not_required_params(self):
        """
        Test that optional parameters not provided during execute request do not fail.

        Optional parameters for execute job shouldn't raise an error if omitted, and should resolve to default
        values if any was explicitly specified during deployment, or inferred from it.
        """
        # get basic mock/data templates
        name = fully_qualified_name(self)
        execute_mock_data_tests = []
        for i in range(2):
            mock_execute = mocked_process_job_runner(f"job-{name}-{i}")
            data_execute = self.get_process_execute_template(f"{name}-{i}")
            execute_mock_data_tests.append((mock_execute, data_execute))

        # apply modifications for testing
        execute_mock_data_tests[0][1].pop("inputs")  # no inputs is valid (although can be required for WPS process)
        execute_mock_data_tests[0][1]["outputs"][0].pop("transmissionMode")  # should resolve to default value

        for mock_execute, data_execute in execute_mock_data_tests:
            with contextlib.ExitStack() as stack:
                for exe in mock_execute:
                    stack.enter_context(exe)
                path = f"/processes/{self.process_public.identifier}/jobs"
                resp = self.app.post_json(path, params=data_execute, headers=self.json_headers)
                assert resp.status_code == 201, "Expected job submission without inputs created without error."

    def test_execute_process_not_visible(self):
        path = f"/processes/{self.process_private.identifier}/jobs"
        data = self.get_process_execute_template()
        resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type == ContentType.APP_JSON

    def test_get_process_visibility_expected_response(self):
        for http_code, wps_process in [(403, self.process_private), (200, self.process_public)]:
            process = self.process_store.fetch_by_id(wps_process.identifier)
            path = f"/processes/{process.identifier}/visibility"
            resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == http_code
            assert resp.content_type == ContentType.APP_JSON
            if http_code == 200:
                assert resp.json["value"] == process.visibility
            else:
                assert "value" not in resp.json

    def test_get_process_visibility_not_found(self):
        path = f"/processes/{self.fully_qualified_test_process_name()}/visibility"
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 404
        assert resp.content_type == ContentType.APP_JSON

    def test_set_process_visibility_success(self):
        test_process = self.process_private.identifier
        proc_schema = {"schema": ProcessSchema.OLD}
        path_describe = f"/processes/{test_process}"
        path_visibility = f"{path_describe}/visibility"

        # validate cannot be found before
        resp = self.app.get(path_describe, params=proc_schema, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403

        # make public
        data = {"value": Visibility.PUBLIC}
        resp = self.app.put_json(path_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["value"] == Visibility.PUBLIC

        # validate now visible and found
        resp = self.app.get(path_describe, params=proc_schema, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.json["process"]["id"] == test_process

        # make private
        data = {"value": Visibility.PRIVATE}
        resp = self.app.put_json(path_visibility, params=data, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert resp.json["value"] == Visibility.PRIVATE

        # validate cannot be found anymore
        resp = self.app.get(path_describe, params=proc_schema, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403

    def test_set_process_visibility_bad_formats(self):
        path = f"/processes/{self.process_private.identifier}/visibility"
        test_data = [
            {"visibility": Visibility.PUBLIC},
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
            assert resp.content_type == ContentType.APP_JSON

        # bad method POST
        data = {"value": Visibility.PUBLIC}
        resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 405
        assert resp.content_type == ContentType.APP_JSON

    def test_process_description_metadata_href_or_value_valid(self):
        """
        Validates that metadata is accepted as either hyperlink reference or literal string value.
        """
        process = {
            "id": self._testMethodName,
            "metadata": [
                {"role": "http://example.com/value-typed", "value": "some-value", "lang": "en-US"},
                {"type": ContentType.TEXT_PLAIN, "href": "https://example.com", "hreflang": "en-US", "rel": "example"}
            ],
            "inputs": [],
            "outputs": [],
        }
        result = sd.Process().deserialize(process)
        assert process["metadata"] == result["metadata"]

    def test_process_description_metadata_href_or_value_invalid(self):
        """
        Validates that various invalid metadata definitions are indicated as such.
        """
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
                    "id": f"{self._testMethodName}_meta_{i}",
                    "metadata": meta,
                })
            except colander.Invalid:
                pass
            else:
                self.fail(f"Metadata is expected to be raised as invalid: (test: {i}, metadata: {meta})")
