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
from weaver.config import WeaverConfiguration
from weaver.datatype import Service
from weaver.execute import ExecuteControlOption, ExecuteTransmissionMode
from weaver.formats import ContentType
from weaver.processes.constants import ProcessSchema
from weaver.utils import fully_qualified_name


# pylint: disable=C0103,invalid-name
class WpsProviderBase(unittest.TestCase):
    remote_provider_name = None
    settings = {}
    config = None

    def fully_qualified_test_process_name(self):
        return fully_qualified_name(self).replace(".", "-")

    def register_provider(self, clear=True, error=False, data=None):
        if clear:
            self.service_store.clear_services()
        path = "/providers"
        data = data or {"id": self.remote_provider_name, "url": resources.TEST_REMOTE_SERVER_URL}
        resp = self.app.post_json(path, params=data, headers=self.json_headers, expect_errors=error)
        if error:
            assert resp.status_code != 201, "Expected provider to fail registration, but erroneously succeeded."
        else:
            err = resp.json
            assert resp.status_code == 201, f"Expected failed provider registration to succeed. Error:\n{err}"
        return resp

    @classmethod
    def setUpClass(cls):
        cls.config = setup_config_with_mongodb(settings=cls.settings)
        cls.app = get_test_weaver_app(config=cls.config)
        cls.json_headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def setUp(self):
        # rebuild clean db on each test
        self.service_store = setup_mongodb_servicestore(self.config)
        self.process_store = setup_mongodb_processstore(self.config)
        self.job_store = setup_mongodb_jobstore(self.config)


# pylint: disable=C0103,invalid-name
class WpsRestApiProvidersTest(WpsProviderBase):
    remote_provider_name = "test-remote-provider"
    settings = {
        "weaver.url": "https://localhost",
        "weaver.wps_path": "/ows/wps",
        "weaver.configuration": WeaverConfiguration.HYBRID
    }

    def test_empty_provider_listing(self):
        """
        Ensure schema validation succeeds when providers are empty.

        Because of empty items within the list, ``OneOf["name",{detail}]`` cannot resolve which item is applicable.

        .. seealso:
            - https://github.com/crim-ca/weaver/issues/339
        """
        self.service_store.clear_services()
        resp = self.app.get("/providers", headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        body = resp.json
        assert "providers" in body and len(body["providers"]) == 0

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_provider_listing_error_handling_queries(self, mock_responses):
        """
        Verify that provider listing handles invalid/unresponsive services as specified by query parameters.
        """
        # register valid service
        self.register_provider()

        # register service reachable but returning invalid XML
        invalid_id = self.remote_provider_name + "-invalid"
        invalid_url = resources.TEST_REMOTE_SERVER_URL + "/invalid"
        with open(resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML, mode="r", encoding="utf-8") as xml:
            # inject badly formatted XML in otherwise valid GetCapabilities response
            # following causes 'wps.provider' to be 'None', which raises during metadata link generation (no check)
            invalid_data = xml.read().replace(
                "<ows:ServiceIdentification>",
                "<ows:ServiceIdentification> <ows:Title>Double Title <bad></ows:Title>"
            )
        mocked_remote_server_requests_wps1([invalid_url, invalid_data, []], mock_responses, data=True)
        # must store directly otherwise it raises during registration check
        # (simulate original service was ok, but was restarted at some point and now has invalid XML)
        self.service_store.save_service(Service(name=invalid_id, url=invalid_url))

        # register service reachable wit invalid XML but can be recovered since it does not impact structure directly
        recover_id = self.remote_provider_name + "-recover"
        recover_url = resources.TEST_REMOTE_SERVER_URL + "/recover"
        with open(resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML, mode="r", encoding="utf-8") as xml:
            # inject badly formatted XML in otherwise valid GetCapabilities response
            # following causes 'wps.processes' to be unresolvable, but service definition itself works
            recover_data = xml.read().replace(
                "<ows:ProcessOffering>",
                "<ows:ProcessOffering   <wps:random> bad content <!-- -->  <info>  >"
            )
        mocked_remote_server_requests_wps1([recover_url, recover_data, []], mock_responses, data=True)
        # must store directly otherwise it raises during registration check
        # (simulate original service was ok, but was restarted at some point and now has invalid XML)
        self.service_store.save_service(Service(name=recover_id, url=recover_url))

        # register service unreachable (eg: was reachable at some point but stopped responding)
        # must store directly since registration will attempt to check it with failing request
        unresponsive_id = self.remote_provider_name + "-unresponsive"
        unresponsive_url = resources.TEST_REMOTE_SERVER_URL + "/unresponsive"
        unresponsive_caps = unresponsive_url + "?service=WPS&request=GetCapabilities&version=1.0.0"
        self.service_store.save_service(Service(name=unresponsive_id, url=unresponsive_caps))

        resp = self.app.get("/providers?check=False", headers=self.json_headers)
        assert resp.status_code == 200
        assert len(resp.json["providers"]) == 4, "All providers should be returned since no check is requested"

        resp = self.app.get("/providers?check=True&ignore=True", headers=self.json_headers)
        assert resp.status_code == 200
        assert len(resp.json["providers"]) == 2, "Unresponsive provider should have been dropped, but not invalid XML"
        assert resp.json["providers"][0]["id"] == self.remote_provider_name
        assert resp.json["providers"][1]["id"] == recover_id

        # error expected to be caused by 'service_store' service, first bad one in the list
        resp = self.app.get("/providers?check=True&ignore=False", headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 422, "Unprocessable response expected for invalid XML"
        assert unresponsive_id in resp.json["description"]
        assert "not accessible" in resp.json["cause"]
        assert "ConnectionError" in resp.json["error"], "Expected service to have trouble retrieving metadata"

        # remove 'unresponsive' service, and recheck, service 'invalid' should now be the problematic one
        self.service_store.delete_service(unresponsive_id)
        resp = self.app.get("/providers?check=True&ignore=False", headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 422, "Unprocessable response expected for invalid XML"
        assert invalid_id in resp.json["description"]
        assert "attribute" in resp.json["cause"]
        assert "AttributeError" in resp.json["error"], "Expected service to have trouble parsing metadata"

        # remove 'unresponsive' service, and recheck, now all services are valid/recoverable without error
        self.service_store.delete_service(invalid_id)
        resp = self.app.get("/providers?check=True&ignore=False", headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 200, "Valid service and recoverable XML should result in valid response"
        assert len(resp.json["providers"]) == 2

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_register_provider_invalid(self, mock_responses):
        """
        Test registration of a service that is reachable but returning invalid XML GetCapabilities schema.
        """
        invalid_id = self.remote_provider_name + "-invalid"
        invalid_url = resources.TEST_REMOTE_SERVER_URL + "/invalid"
        with open(resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML, mode="r", encoding="utf-8") as xml:
            # inject badly formatted XML in otherwise valid GetCapabilities response
            # following causes 'wps.provider' to be 'None', which raises during metadata link generation (no check)
            invalid_data = xml.read().replace(
                "<ows:ServiceIdentification>",
                "<ows:ServiceIdentification> <ows:Title>Double Title <bad></ows:Title>"
            )
        mocked_remote_server_requests_wps1([invalid_url, invalid_data, []], mock_responses, data=True)

        resp = self.register_provider(clear=True, error=True, data={"id": invalid_id, "url": invalid_url})
        assert resp.status_code == 422
        assert invalid_id in resp.json["description"]
        assert "attribute" in resp.json["cause"]
        assert resp.json["error"] == "AttributeError", "Expected service to have trouble parsing metadata"

    def test_register_provider_unresponsive(self):
        """
        Test registration of a service that is unreachable (cannot obtain XML GetCapabilities because no response).
        """
        unresponsive_id = self.remote_provider_name + "-unresponsive"
        unresponsive_url = resources.TEST_REMOTE_SERVER_URL + "/unresponsive"
        resp = self.register_provider(clear=True, error=True, data={"id": unresponsive_id, "url": unresponsive_url})
        assert resp.status_code == 422, "Unprocessable response expected for invalid XML"
        assert unresponsive_id in resp.json["description"]
        err_msg = "Expected service to have trouble retrieving metadata, error: {} not in {}"
        # different errors/causes are raised first based on requests version, but same issue
        known_causes = ["Connection refused", "Connection aborted", "not accessible"]
        known_errors = ["ConnectionError", "ConnectTimeout", "SSLError"]
        resp_cause = resp.json["cause"]
        resp_error = resp.json["error"]
        assert any(err_cause in resp_cause for err_cause in known_causes), err_msg.format(resp_cause, known_causes)
        assert any(err_class in resp_error for err_class in known_errors), err_msg.format(resp_error, known_errors)

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_register_provider_recoverable(self, mock_responses):
        """
        Test registration of a service that technically has invalid XML GetCapabilities schema, but can be recovered.

        .. seealso::
            - Parameter ``recover`` from instance :data:`weaver.xml_util.XML_PARSER` allows handling partially bad XML.
            - Other test that validates end-to-end definition of recoverable XML provider process.
              :class:`tests.functional.test_wps_provider.WpsProviderTest.test_register_finch_with_invalid_escape_chars`
        """
        recover_id = self.remote_provider_name + "-recover"
        recover_url = resources.TEST_REMOTE_SERVER_URL + "/recover"
        with open(resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML, mode="r", encoding="utf-8") as xml:
            # inject badly formatted XML in otherwise valid GetCapabilities response
            # following causes 'wps.processes' to be unresolvable, but service definition itself works
            recover_data = xml.read().replace(
                "<ows:ProcessOffering>",
                "<ows:ProcessOffering   <wps:random> bad content <!-- -->  <info>  >"
            )
        mocked_remote_server_requests_wps1([recover_url, recover_data, []], mock_responses, data=True)

        resp = self.register_provider(clear=True, error=False, data={"id": recover_id, "url": recover_url})
        assert resp.json["id"] == recover_id
        assert resp.json["url"] == recover_url

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
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
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_register_provider_conflict(self):
        self.register_provider(clear=True, error=False)
        resp = self.register_provider(clear=False, error=True)
        assert resp.status_code == 409

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_get_provider_processes(self):
        self.register_provider()

        path = f"/providers/{self.remote_provider_name}/processes"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
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
            assert ExecuteControlOption.ASYNC in process["jobControlOptions"]
            remote_processes.append(process["id"])
        assert resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID in remote_processes

    @pytest.mark.xfail(condition=LooseVersion(owslib.__version__) <= LooseVersion("0.25.0"),
                       reason="OWSLib fix for retrieval of processVersion from DescribeProcess not yet available "
                              "(https://github.com/geopython/OWSLib/pull/794)")
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_get_provider_process_description_with_version(self):
        """
        Test only the version field which depends on a fix from :mod:`OWSLib`.

        The process description retrieved from a remote WPS-1 DescribeProcess request should provide
        its version converted into JSON schema, for known :data:`weaver.processes.constants.PROCESS_SCHEMAS`
        representations.

        .. seealso::
            - Full description validation (OGC schema): :meth:`test_get_provider_process_description_ogc_schema`
            - Full description validation (OLD schema): :meth:`test_get_provider_process_description_old_schema`
            - Fix in PR `geopython/OWSLib#794 <https://github.com/geopython/OWSLib/pull/794>`_
        """
        self.register_provider()

        path = f"/providers/{self.remote_provider_name}/processes/{resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}"
        resp = self.app.get(path, params={"schema": ProcessSchema.OLD}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        proc = resp.json["process"]

        resp = self.app.get(path, params={"schema": ProcessSchema.OGC}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        desc = resp.json

        assert "version" in proc and isinstance(proc["version"], str) and proc["version"] == "0.5"
        assert "version" in desc and isinstance(desc["version"], str) and desc["version"] == "0.5"

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_get_provider_process_description_old_schema(self):
        self.register_provider()

        query = {"schema": ProcessSchema.OLD}
        path = f"/providers/{self.remote_provider_name}/processes/{resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}"
        resp = self.app.get(path, params=query, headers=self.json_headers)
        body = resp.json
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "process" in resp.json and isinstance(body["process"], dict)
        process = body["process"]
        assert "id" in process and isinstance(process["id"], str)
        assert process["id"] == resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
        assert "title" in process and isinstance(process["title"], str)
        assert "description" in process and isinstance(process["description"], str)
        # evaluated in separate test (test_get_provider_process_description_with_version)
        # assert "version" in process and isinstance(process["version"], str)
        assert "keywords" in process and isinstance(process["keywords"], list)
        assert "metadata" in process and isinstance(process["metadata"], list)
        assert len(body["jobControlOptions"]) == 1
        assert ExecuteControlOption.ASYNC in body["jobControlOptions"]
        assert len(body["outputTransmission"]) == 2
        assert ExecuteTransmissionMode.VALUE in body["outputTransmission"]
        assert "inputs" in process and isinstance(process["inputs"], list)
        assert all(isinstance(p_io, dict) and "id" in p_io for p_io in process["inputs"])
        assert "outputs" in process and isinstance(process["outputs"], list)
        assert all(isinstance(p_io, dict) and "id" in p_io for p_io in process["outputs"])

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_get_provider_process_description_ogc_schema(self):
        self.register_provider()

        path = f"/providers/{self.remote_provider_name}/processes/{resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        assert "process" not in resp.json and isinstance(resp.json, dict)
        process = resp.json
        assert "id" in process and isinstance(process["id"], str)
        assert process["id"] == resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID
        assert "title" in process and isinstance(process["title"], str)
        assert "description" in process and isinstance(process["description"], str)
        # evaluated in separate test (test_get_provider_process_description_with_version)
        # assert "version" in process and isinstance(process["version"], str) and len(process["version"])
        assert "keywords" in process and isinstance(process["keywords"], list)
        assert "metadata" in process and isinstance(process["metadata"], list)
        assert len(process["jobControlOptions"]) == 1
        assert ExecuteControlOption.ASYNC in process["jobControlOptions"]
        assert len(process["outputTransmission"]) == 2
        assert ExecuteTransmissionMode.VALUE in process["outputTransmission"]
        assert "inputs" in process and isinstance(process["inputs"], dict)
        assert all(isinstance(p_io, str) and isinstance(process["inputs"][p_io], dict) for p_io in process["inputs"])
        assert all("id" not in process["inputs"][p_io] for p_io in process["inputs"])
        assert "outputs" in process and isinstance(process["outputs"], dict)
        assert all(isinstance(p_io, str) and isinstance(process["outputs"][p_io], dict) for p_io in process["outputs"])
        assert all("id" not in process["outputs"][p_io] for p_io in process["outputs"])

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.WPS_NO_INPUTS_XML],
    ])
    def test_get_provider_process_no_inputs(self):
        """
        Process that takes no inputs should be permitted and its description must allow generation of empty map/list.
        """
        self.register_provider()

        path = f"/providers/{self.remote_provider_name}/processes/{resources.WPS_NO_INPUTS_ID}"
        resp = self.app.get(path, params={"schema": ProcessSchema.OLD}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        inputs = resp.json["process"]["inputs"]
        assert isinstance(inputs, list) and len(inputs) == 0

        path = f"/providers/{self.remote_provider_name}/processes/{resources.WPS_NO_INPUTS_ID}"
        resp = self.app.get(path, params={"schema": ProcessSchema.OGC}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        inputs = resp.json["inputs"]
        assert isinstance(inputs, dict) and len(inputs) == 0

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,  # don't care
        [resources.WPS_LITERAL_VALUES_IO_XML],
    ])
    def test_get_provider_process_literal_values(self):
        """
        Test conversion of I/O of supported values defined as literal data domains from provider process.
        """
        self.register_provider()
        path = f"/providers/{self.remote_provider_name}/processes/{resources.WPS_LITERAL_VALUES_IO_ID}"
        resp = self.app.get(path, params={"schema": ProcessSchema.OLD}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        inputs = resp.json["process"]["inputs"]
        outputs = resp.json["process"]["outputs"]
        assert isinstance(inputs, list) and len(inputs) == 15
        assert isinstance(outputs, list) and len(outputs) == 2

        # inputs have different combinations of minOccurs/maxOccurs, Allowed/Supported Values, Ranges, Types, etc.
        assert inputs[0]["id"] == "lat"
        assert inputs[0]["title"] == "Latitude"
        assert inputs[0]["minOccurs"] == 1
        assert inputs[0]["maxOccurs"] == 100
        assert "default" not in inputs[0]
        assert "literalDataDomains" in inputs[0] and len(inputs[0]["literalDataDomains"]) == 1
        assert inputs[0]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[0]["literalDataDomains"][0]["valueDefinition"] == {"anyValue": False}
        assert "defaultValue" not in inputs[0]["literalDataDomains"][0]
        assert inputs[1]["id"] == "lon"
        assert inputs[1]["title"] == "Longitude"
        assert inputs[1]["minOccurs"] == 1
        assert inputs[1]["maxOccurs"] == 100
        assert "default" not in inputs[1]
        assert "literalDataDomains" in inputs[1] and len(inputs[1]["literalDataDomains"]) == 1
        assert inputs[1]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[1]["literalDataDomains"][0]["valueDefinition"] == {"anyValue": False}
        assert "defaultValue" not in inputs[1]["literalDataDomains"][0]
        assert inputs[2]["id"] == "start_date"
        assert inputs[2]["title"] == "Initial date"
        assert inputs[2]["minOccurs"] == 0
        assert inputs[2]["maxOccurs"] == 1
        assert "default" not in inputs[2]
        assert "literalDataDomains" in inputs[2] and len(inputs[2]["literalDataDomains"]) == 1
        assert inputs[2]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[2]["literalDataDomains"][0]["valueDefinition"] == {"anyValue": False}
        assert "defaultValue" not in inputs[2]["literalDataDomains"][0]
        assert inputs[3]["id"] == "end_date"
        assert inputs[3]["title"] == "Final date"
        assert inputs[3]["minOccurs"] == 0
        assert inputs[3]["maxOccurs"] == 1
        assert "default" not in inputs[3]
        assert "literalDataDomains" in inputs[3] and len(inputs[3]["literalDataDomains"]) == 1
        assert inputs[3]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[3]["literalDataDomains"][0]["valueDefinition"] == {"anyValue": False}
        assert "defaultValue" not in inputs[3]["literalDataDomains"][0]
        assert inputs[4]["id"] == "ensemble_percentiles"
        assert inputs[4]["title"] == "Ensemble percentiles"
        assert inputs[4]["minOccurs"] == 0
        assert inputs[4]["maxOccurs"] == 1
        assert "default" not in inputs[4]
        assert "literalDataDomains" in inputs[4] and len(inputs[4]["literalDataDomains"]) == 1
        assert inputs[4]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[4]["literalDataDomains"][0]["valueDefinition"] == {"anyValue": False}
        assert inputs[4]["literalDataDomains"][0]["defaultValue"] == "10,50,90"
        assert inputs[5]["id"] == "dataset_name"
        assert inputs[5]["title"] == "Dataset name"
        assert inputs[5]["minOccurs"] == 0
        assert inputs[5]["maxOccurs"] == 1
        assert "default" not in inputs[5]
        assert "literalDataDomains" in inputs[5] and len(inputs[5]["literalDataDomains"]) == 1
        assert inputs[5]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[5]["literalDataDomains"][0]["valueDefinition"] == ["bccaqv2"]
        assert "defaultValue" not in inputs[5]["literalDataDomains"][0]
        assert "allowedValues" not in inputs[5]
        assert inputs[6]["id"] == "rcp"
        assert inputs[6]["title"] == "RCP Scenario"
        assert inputs[6]["minOccurs"] == 1
        assert inputs[6]["maxOccurs"] == 1
        assert "default" not in inputs[6]
        assert "literalDataDomains" in inputs[6] and len(inputs[6]["literalDataDomains"]) == 1
        assert inputs[6]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[6]["literalDataDomains"][0]["valueDefinition"] == ["rcp26", "rcp45", "rcp85"]
        assert "defaultValue" not in inputs[6]["literalDataDomains"][0]
        assert inputs[7]["id"] == "models"
        assert inputs[7]["title"] == "Models to include in ensemble"
        assert inputs[7]["minOccurs"] == 0
        assert inputs[7]["maxOccurs"] == 1000
        assert "default" not in inputs[7]
        assert "literalDataDomains" in inputs[7] and len(inputs[7]["literalDataDomains"]) == 1
        assert inputs[7]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[7]["literalDataDomains"][0]["valueDefinition"] == [
            "24MODELS", "PCIC12", "BNU-ESM", "CCSM4", "CESM1-CAM5", "CNRM-CM5", "CSIRO-Mk3-6-0", "CanESM2",
            "FGOALS-g2", "GFDL-CM3", "GFDL-ESM2G", "GFDL-ESM2M", "HadGEM2-AO", "HadGEM2-ES", "IPSL-CM5A-LR",
            "IPSL-CM5A-MR", "MIROC-ESM-CHEM", "MIROC-ESM", "MIROC5", "MPI-ESM-LR", "MPI-ESM-MR", "MRI-CGCM3",
            "NorESM1-M", "NorESM1-ME", "bcc-csm1-1-m", "bcc-csm1-1"
        ]
        assert inputs[7]["literalDataDomains"][0]["defaultValue"] == "24MODELS"
        assert inputs[8]["id"] == "window"
        assert inputs[8]["title"] == "Window"
        assert inputs[8]["minOccurs"] == 0
        assert inputs[8]["maxOccurs"] == 1
        assert "default" not in inputs[8]
        assert "literalDataDomains" in inputs[8] and len(inputs[8]["literalDataDomains"]) == 1
        assert inputs[8]["literalDataDomains"][0]["dataType"]["name"] == "integer"
        assert inputs[8]["literalDataDomains"][0]["valueDefinition"] == {"anyValue": False}
        assert inputs[8]["literalDataDomains"][0]["defaultValue"] == 6
        assert inputs[9]["id"] == "freq"
        assert inputs[9]["title"] == "Frequency"
        assert inputs[9]["minOccurs"] == 0
        assert inputs[9]["maxOccurs"] == 1
        assert "default" not in inputs[9]
        assert "literalDataDomains" in inputs[9] and len(inputs[9]["literalDataDomains"]) == 1
        assert inputs[9]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[9]["literalDataDomains"][0]["valueDefinition"] == ["YS", "MS", "QS-DEC", "AS-JUL"]
        assert inputs[9]["literalDataDomains"][0]["defaultValue"] == "YS"
        assert inputs[10]["id"] == "check_missing"
        assert inputs[10]["title"] == "Missing value handling method"
        assert inputs[10]["minOccurs"] == 0, "original XML minOccurs=1, but detected defaultValue should correct to 0"
        assert inputs[10]["maxOccurs"] == 1
        assert "default" not in inputs[10]
        assert "literalDataDomains" in inputs[10] and len(inputs[10]["literalDataDomains"]) == 1
        assert inputs[10]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[10]["literalDataDomains"][0]["valueDefinition"] == [
            "any", "wmo", "pct", "at_least_n", "skip", "from_context"
        ]
        assert inputs[10]["literalDataDomains"][0]["defaultValue"] == "any"
        assert inputs[11]["id"] == "missing_options"
        assert inputs[11]["title"] == "Missing method parameters"
        assert inputs[11]["minOccurs"] == 0
        assert inputs[11]["maxOccurs"] == 1
        assert "default" not in inputs[11]
        assert "literalDataDomains" not in inputs[11], "Complex input of the process should not have literal domains"
        assert "formats" in inputs[11] and len(inputs[11]["formats"]) == 1
        assert inputs[11]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert inputs[11]["formats"][0]["default"] is True, \
            "format is specified as default one explicitly, but should be regardless since it is the only one supported"
        # see test 'test_get_provider_process_complex_maximum_megabytes'
        # assert inputs[11]["formats"][0]["maximumMegabytes"] == 200
        assert inputs[12]["id"] == "cf_compliance"
        assert inputs[12]["title"] == "Strictness level for CF-compliance input checks."
        assert inputs[12]["minOccurs"] == 0, "original XML minOccurs=1, but detected defaultValue should correct to 0"
        assert inputs[12]["maxOccurs"] == 1
        assert "default" not in inputs[12]
        assert "literalDataDomains" in inputs[12] and len(inputs[12]["literalDataDomains"]) == 1
        assert inputs[12]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[12]["literalDataDomains"][0]["valueDefinition"] == ["log", "warn", "raise"]
        assert inputs[12]["literalDataDomains"][0]["defaultValue"] == "warn"
        assert inputs[13]["id"] == "data_validation"
        assert inputs[13]["title"] == "Strictness level for data validation input checks."
        assert inputs[13]["minOccurs"] == 0, "original XML minOccurs=1, but detected defaultValue should correct to 0"
        assert inputs[13]["maxOccurs"] == 1
        assert "default" not in inputs[13]
        assert "literalDataDomains" in inputs[13] and len(inputs[13]["literalDataDomains"]) == 1
        assert inputs[13]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[13]["literalDataDomains"][0]["valueDefinition"] == ["log", "warn", "raise"]
        assert inputs[13]["literalDataDomains"][0]["defaultValue"] == "raise"
        assert inputs[14]["id"] == "output_format"
        assert inputs[14]["title"] == "Output format choice"
        assert inputs[14]["minOccurs"] == 0
        assert inputs[14]["maxOccurs"] == 1
        assert "default" not in inputs[14]
        assert "literalDataDomains" in inputs[14] and len(inputs[14]["literalDataDomains"]) == 1
        assert inputs[14]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert inputs[14]["literalDataDomains"][0]["valueDefinition"] == ["netcdf", "csv"]
        assert inputs[14]["literalDataDomains"][0]["defaultValue"] == "netcdf"

        assert outputs[0]["id"] == "output"
        assert len(outputs[0]["formats"]) == 2
        assert outputs[0]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert outputs[0]["formats"][0]["encoding"] == "base64"
        assert outputs[0]["formats"][0]["default"] is True
        assert "maximumMegabytes" not in outputs[0]["formats"][0]  # never applies, even with OWSLib update
        assert outputs[0]["formats"][1]["mediaType"] == ContentType.APP_ZIP
        assert outputs[0]["formats"][1]["encoding"] == "base64"
        assert outputs[0]["formats"][1]["default"] is False
        assert "maximumMegabytes" not in outputs[0]["formats"][1]  # never applies, even with OWSLib update
        assert outputs[1]["id"] == "output_log"
        assert len(outputs[1]["formats"]) == 1
        assert outputs[1]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert "encoding" not in outputs[1]["formats"][0]
        assert outputs[1]["formats"][0]["default"] is True
        assert "maximumMegabytes" not in outputs[1]["formats"][0]  # never applies, even with OWSLib update

    @pytest.mark.xfail(condition=LooseVersion(owslib.__version__) <= LooseVersion("0.25.0"),
                       reason="OWSLib fix for retrieval of maximumMegabytes from ComplexData not yet available "
                              "(https://github.com/geopython/OWSLib/pull/796)")
    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,  # don't care
        [resources.WPS_LITERAL_VALUES_IO_XML],
    ])
    def test_get_provider_process_complex_maximum_megabytes(self):
        """
        Test conversion of I/O of supported values defined as literal data domains from provider process.
        """
        self.register_provider()
        path = f"/providers/{self.remote_provider_name}/processes/{resources.WPS_LITERAL_VALUES_IO_ID}"
        resp = self.app.get(path, params={"schema": ProcessSchema.OLD}, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        inputs = resp.json["process"]["inputs"]
        assert "maximumMegabytes" in inputs[11]["formats"][0]
        assert inputs[11]["formats"][0]["maximumMegabytes"] == 200


# pylint: disable=C0103,invalid-name
class WpsProviderLocalOnlyTest(WpsProviderBase):
    """
    Validate that operations are preemptively forbidden for a local-only instance.
    """
    remote_provider_name = "test-wps-local-only"
    settings = {
        "weaver.url": "https://localhost",
        "weaver.wps_path": "/ows/wps",
        "weaver.configuration": WeaverConfiguration.ADES  # local-only
    }

    def setUp(self):
        """
        Inject service directly in database to ensure errors are not raised by missing entry, but by explicit checks.
        """
        super(WpsProviderLocalOnlyTest, self).setUp()
        self.service_store.clear_services()
        self.job_store.clear_jobs()
        self.service_store.save_service(service=Service({
            "name": self.remote_provider_name,
            "url": resources.TEST_REMOTE_SERVER_URL,
            "public": True
        }), overwrite=True)
        self.job = self.job_store.save_job("test", "fake-process", self.remote_provider_name)

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        []
    ])
    def test_forbidden_register_provider(self):
        resp = self.register_provider(error=True)
        assert resp.status_code == 403, f"\n{resp.json}"

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_forbidden_describe_process(self):
        prov = f"/providers/{self.remote_provider_name}"
        path = f"{prov}/processes/{resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}/jobs"
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403, f"\n{resp.json}"

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_forbidden_execute_process(self):
        prov = f"/providers/{self.remote_provider_name}"
        path = f"{prov}/processes/{resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}/jobs"
        resp = self.app.post_json(path, params={}, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403, f"\n{resp.json}"

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_forbidden_list_jobs(self):
        prov = f"/providers/{self.remote_provider_name}"
        path = f"{prov}/processes/{resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}/jobs"
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403, f"\n{resp.json}"

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        [resources.TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML],
    ])
    def test_forbidden_get_job(self):
        prov = f"/providers/{self.remote_provider_name}"
        path = f"{prov}/processes/{resources.TEST_REMOTE_SERVER_WPS1_PROCESS_ID}/jobs/{self.job.id}"
        resp = self.app.get(path, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 403, f"\n{resp.json}"
