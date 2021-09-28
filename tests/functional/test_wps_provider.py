import contextlib

import pyramid.testing
import pytest
import responses

from tests import resources
from tests.utils import (
    mocked_execute_process,
    mocked_remote_server_requests_wps1,
    mocked_sub_requests,
    setup_mongodb_jobstore,
    setup_mongodb_processstore,
    setup_mongodb_servicestore
)
from tests.functional.utils import WpsConfigBase
from weaver.execute import (
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_MODE_ASYNC,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_TRANSMISSION_MODE_REFERENCE
)
from weaver.formats import CONTENT_TYPE_APP_NETCDF, CONTENT_TYPE_TEXT_PLAIN
from weaver.processes.types import PROCESS_WPS_REMOTE


# pylint: disable=C0103,invalid-name
@pytest.mark.functional
class WpsRestApiProcessesTest(WpsConfigBase):

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def setUp(self):
        # rebuild clean db on each test
        self.service_store = setup_mongodb_servicestore(self.config)
        self.process_store = setup_mongodb_processstore(self.config)
        self.job_store = setup_mongodb_jobstore(self.config)
        self.app_url = self.settings["weaver.url"]

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_INVALID_ESCAPE_CHARS_GETCAP_WPS1_XML,
        [],
    ])
    def test_register_finch_with_invalid_escape_chars(self):
        """
        Remote provider that has invalid characters that should be escaped (<, <=) but should succeeds registration.

        This test ensure that temporary patch of XML parser with *permissive* invalid characters that can be recovered
        in some obvious cases are handled (e.g.: values within a description string field).

        .. seealso::
            - Parameter ``recover`` from instance :data:`weaver.xml_util.XML_PARSER` and
              override :meth:`weaver.xml_util.fromstring` employed by :mod:`OWSLib` during WPS-XML requests.
            - Comments in :data:`resources.TEST_INVALID_ESCAPE_CHARS_GETCAP_WPS1_XML` file describe bad characters.
        """
        self.service_store.clear_services()

        # register the provider
        remote_provider_name = "test-wps-remote-provider-finch"
        path = "/providers"
        data = {"id": remote_provider_name, "url": resources.TEST_REMOTE_SERVER_URL}
        resp = self.app.post_json(path, params=data, headers=self.json_headers)
        assert resp.status_code == 201

        # validate service capabilities
        path = "/providers/{}".format(remote_provider_name)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_HUMMINGBIRD_GETCAP_WPS1_XML,
        [resources.TEST_HUMMINGBIRD_DESCRIBE_WPS1_XML],
    ])
    def test_register_describe_execute_ncdump(self):
        """
        Test the full workflow from remote WPS-1 provider registration, process description and execution.

        Validation is accomplished against the same process and mocked server from corresponding test deployment
        of a complete server in order to detect early any breaking feature.

        .. seealso::
            https://github.com/Ouranosinc/pavics-sdi/blob/master/docs/source/notebook-components/weaver_example.ipynb.
        """
        self.service_store.clear_services()

        # register the provider
        remote_provider_name = "test-wps-remote-provider-hummingbird"
        path = "/providers"
        data = {"id": remote_provider_name, "url": resources.TEST_REMOTE_SERVER_URL}
        resp = self.app.post_json(path, params=data, headers=self.json_headers)
        assert resp.status_code == 201

        # validate service capabilities
        path = "/providers/{}".format(remote_provider_name)
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert "id" in body and body["id"] == remote_provider_name
        assert "hummingbird" in body["title"].lower()
        assert body["type"] == PROCESS_WPS_REMOTE

        # validate processes capabilities
        path = "/providers/{}/processes".format(remote_provider_name)
        resp = self.app.get(path, headers=self.json_headers)
        body = resp.json
        assert resp.status_code == 200
        assert "processes" in body and len(body["processes"]) == 14  # in TEST_HUMMINGBIRD_GETCAP_WPS1_XML
        processes = {process["id"]: process for process in body["processes"]}
        assert "ncdump" in processes
        assert processes["ncdump"]["version"] == "4.4.1.1"
        assert processes["ncdump"]["metadata"][0]["rel"] == "birdhouse"
        assert processes["ncdump"]["metadata"][1]["rel"] == "user-guide"
        # keyword 'Hummingbird' in this case is from GetCapabilities ProviderName
        # keyword of the service name within Weaver is also provided, which can be different than provider
        expect_keywords = [PROCESS_WPS_REMOTE, "Hummingbird", remote_provider_name]
        assert all(key in processes["ncdump"]["keywords"] for key in expect_keywords)
        proc_desc_url = processes["ncdump"]["processDescriptionURL"]
        proc_wps1_url = processes["ncdump"]["processEndpointWPS1"]
        proc_exec_url = processes["ncdump"]["executeEndpoint"]
        assert proc_wps1_url.startswith(resources.TEST_REMOTE_SERVER_URL)
        assert proc_desc_url == self.app_url + path + "/ncdump"
        assert proc_exec_url == self.app_url + path + "/ncdump/jobs"

        # validate process description
        resp = self.app.get(proc_desc_url, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json

        assert "inputs" in body and len(body["inputs"]) == 2
        assert all(iid in body["inputs"] for iid in ["dataset", "dataset_opendap"])
        assert body["inputs"]["dataset"]["minOccurs"] == 0
        assert body["inputs"]["dataset"]["maxOccurs"] == 100
        assert "formats" in body["inputs"]["dataset"]
        assert len(body["inputs"]["dataset"]["formats"]) == 1
        assert body["inputs"]["dataset"]["formats"][0]["default"] is True
        assert "literalDataDomains" not in body["inputs"]["dataset"]
        assert body["inputs"]["dataset"]["formats"][0]["mediaType"] == CONTENT_TYPE_APP_NETCDF
        assert body["inputs"]["dataset_opendap"]["minOccurs"] == 0
        assert body["inputs"]["dataset_opendap"]["maxOccurs"] == 100
        assert "formats" not in body["inputs"]["dataset_opendap"]
        assert "literalDataDomains" in body["inputs"]["dataset_opendap"]
        assert len(body["inputs"]["dataset_opendap"]["literalDataDomains"]) == 1
        assert body["inputs"]["dataset_opendap"]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert body["inputs"]["dataset_opendap"]["literalDataDomains"][0]["valueDefinition"]["anyValue"] is True
        assert body["inputs"]["dataset_opendap"]["literalDataDomains"][0]["default"] is True

        assert "outputs" in body and len(body["outputs"]) == 1
        assert "output" in body["outputs"]
        assert "formats" in body["outputs"]["output"]
        assert len(body["outputs"]["output"]["formats"]) == 1
        assert body["outputs"]["output"]["formats"][0]["default"] is True
        assert body["outputs"]["output"]["formats"][0]["mediaType"] == CONTENT_TYPE_TEXT_PLAIN
        assert "literalDataDomains" not in body["outputs"]["output"]

        assert body["processDescriptionURL"] == proc_desc_url
        assert body["processEndpointWPS1"] == proc_wps1_url
        assert body["executeEndpoint"] == proc_exec_url
        job_exec_url = proc_exec_url.replace("/execution", "/jobs")  # both are aliases, any could be returned
        ogc_exec_url = proc_exec_url.replace("/jobs", "/execution")
        assert any(link["href"] in [job_exec_url, ogc_exec_url] and link["rel"] == "execute" for link in body["links"])
        assert any(link["href"] == proc_desc_url and link["rel"] == "process-desc" for link in body["links"])
        # WPS-1 URL also includes relevant query parameters to obtain a valid response
        assert any(link["href"].startswith(proc_wps1_url) and link["rel"] == "service-desc" for link in body["links"])

        assert EXECUTE_CONTROL_OPTION_ASYNC in body["jobControlOptions"]
        assert EXECUTE_TRANSMISSION_MODE_REFERENCE in body["outputTransmission"]

        # validate execution submission
        # (don't actually execute because server is mocked, only validate parsing of I/O and job creation)
        exec_file = "http://localhost.com/dont/care.nc"
        exec_body = {
            "mode": EXECUTE_MODE_ASYNC,
            "response": EXECUTE_RESPONSE_DOCUMENT,
            "inputs": [{"id": "dataset", "href": exec_file}],
            "outputs": [{"id": "output", "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE}]
        }
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_process():
                stack_exec.enter_context(mock_exec)
            mock_resp = stack_exec.enter_context(responses.RequestsMock(assert_all_requests_are_fired=False))
            mock_resp.add("GET", exec_file, body="Fake NetCDF", headers={"Content-Type": CONTENT_TYPE_APP_NETCDF})
            resp = mocked_sub_requests(self.app, "post_json", proc_exec_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], "Failed with: [{}]\nReason:\n{}".format(resp.status_code, resp.json)
            status_url = resp.json["location"]
            job_id = resp.json["jobID"]
            results = self.monitor_job(status_url)
            outputs = self.get_outputs(status_url)

