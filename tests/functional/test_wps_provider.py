import contextlib
from typing import TYPE_CHECKING

import mock
import pytest

from tests import resources
from tests.functional.utils import WpsConfigBase
from tests.utils import mocked_execute_celery, mocked_remote_server_requests_wps1, mocked_sub_requests
from weaver.config import WeaverConfiguration
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import ContentType
from weaver.processes.types import ProcessType
from weaver.processes.wps1_process import Wps1Process

if TYPE_CHECKING:
    from responses import RequestsMock

    from tests.utils import MockPatch


# pylint: disable=C0103,invalid-name
@pytest.mark.functional
class WpsProviderTest(WpsConfigBase):
    settings = {
        # NOTE: important otherwise cannot execute "remote" provider (default local only)
        "weaver.configuration": WeaverConfiguration.HYBRID,
        "weaver.wps_output_dir": "/tmp",  # nosec: B108 # don't care hardcoded for test
        "weaver.wps_output_url": f"{resources.TEST_REMOTE_SERVER_URL}/wps-outputs"
    }

    def setUp(self):
        # rebuild clean db on each test
        self.service_store.clear_services()
        self.process_store.clear_processes()
        self.job_store.clear_jobs()

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
        # register the provider
        remote_provider_name = "test-wps-remote-provider-finch"
        path = "/providers"
        data = {"id": remote_provider_name, "url": resources.TEST_REMOTE_SERVER_URL}
        resp = self.app.post_json(path, params=data, headers=self.json_headers)
        assert resp.status_code == 201

        # validate service capabilities
        path = f"/providers/{remote_provider_name}"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_HUMMINGBIRD_WPS1_GETCAP_XML,
        [resources.TEST_HUMMINGBIRD_DESCRIBE_WPS1_XML],
    ])
    def test_register_describe_execute_ncdump(self, mock_responses):
        # type: (RequestsMock) -> None
        """
        Test the full workflow from remote WPS-1 provider registration, process description, execution and fetch result.

        The complete execution and definitions (XML responses) of the "remote" WPS are mocked.
        Requests and response negotiation between Weaver and that "remote" WPS are effectively executed and validated.

        Validation is accomplished against the same process and mocked server from corresponding test deployment
        server in order to detect early any breaking feature. Responses XML bodies employed to simulate the mocked
        server are pre-generated from real request calls to the actual service that was running on a live platform.

        .. seealso::
            - Reference notebook testing the same process on a live server:
              https://github.com/Ouranosinc/pavics-sdi/blob/master/docs/source/notebook-components/weaver_example.ipynb
            - Evaluate format of submitted Execute body (see `#340 <https://github.com/crim-ca/weaver/issues/340>`_).
        """
        # register the provider
        remote_provider_name = "test-wps-remote-provider-hummingbird"
        path = "/providers"
        data = {"id": remote_provider_name, "url": resources.TEST_REMOTE_SERVER_URL}
        resp = self.app.post_json(path, params=data, headers=self.json_headers)
        assert resp.status_code == 201

        # validate service capabilities
        path = f"/providers/{remote_provider_name}"
        resp = self.app.get(path, headers=self.json_headers)
        assert resp.status_code == 200
        body = resp.json
        assert "id" in body and body["id"] == remote_provider_name
        assert "hummingbird" in body["title"].lower()
        assert body["type"] == ProcessType.WPS_REMOTE

        # validate processes capabilities
        path = f"/providers/{remote_provider_name}/processes"
        resp = self.app.get(path, headers=self.json_headers)
        body = resp.json
        assert resp.status_code == 200
        assert "processes" in body and len(body["processes"]) == len(resources.TEST_HUMMINGBIRD_WPS1_PROCESSES)
        processes = {process["id"]: process for process in body["processes"]}
        assert "ncdump" in processes
        assert processes["ncdump"]["version"] == "4.4.1.1"
        assert processes["ncdump"]["metadata"][0]["rel"] == "birdhouse"
        assert processes["ncdump"]["metadata"][1]["rel"] == "user-guide"
        # keyword 'Hummingbird' in this case is from GetCapabilities ProviderName
        # keyword of the service name within Weaver is also provided, which can be different than provider
        expect_keywords = [ProcessType.WPS_REMOTE, "Hummingbird", remote_provider_name]
        assert all(key in processes["ncdump"]["keywords"] for key in expect_keywords)
        proc_desc_url = processes["ncdump"]["processDescriptionURL"]
        proc_wps1_url = processes["ncdump"]["processEndpointWPS1"]
        proc_exec_url = processes["ncdump"]["executeEndpoint"]
        assert proc_wps1_url.startswith(resources.TEST_REMOTE_SERVER_URL)
        assert proc_desc_url == f"{self.url + path}/ncdump"
        assert proc_exec_url == f"{self.url + path}/ncdump/jobs"

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
        assert body["inputs"]["dataset"]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
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
        assert body["outputs"]["output"]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert "literalDataDomains" not in body["outputs"]["output"]

        assert body["processDescriptionURL"] == proc_desc_url
        assert body["processEndpointWPS1"] == proc_wps1_url
        assert body["executeEndpoint"] == proc_exec_url
        job_exec_url = proc_exec_url.replace("/execution", "/jobs")  # both are aliases, any could be returned
        ogc_exec_url = proc_exec_url.replace("/jobs", "/execution")
        links = {link["rel"].rsplit("/")[-1]: link["href"] for link in body["links"]}
        assert links["execute"] in [job_exec_url, ogc_exec_url]
        assert links["process-meta"] == proc_desc_url
        # WPS-1 URL also includes relevant query parameters to obtain a valid response directly from remote service
        assert links["process-desc"] == proc_wps1_url
        assert links["service-desc"].startswith(resources.TEST_REMOTE_SERVER_URL)
        assert "DescribeProcess" in links["process-desc"]
        assert "GetCapabilities" in links["service-desc"]

        assert ExecuteControlOption.ASYNC in body["jobControlOptions"]
        assert ExecuteTransmissionMode.VALUE in body["outputTransmission"]

        # validate execution submission
        # (don't actually execute because server is mocked, only validate parsing of I/O and job creation)

        # first setup all expected contents and files
        exec_file = "http://localhost.com/dont/care.nc"
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": [{"id": "dataset", "href": exec_file}],
            "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.REFERENCE}]
        }
        status_url = f"{resources.TEST_REMOTE_SERVER_URL}/status.xml"
        output_url = f"{resources.TEST_REMOTE_SERVER_URL}/output.txt"
        with open(resources.TEST_HUMMINGBIRD_STATUS_WPS1_XML, mode="r", encoding="utf-8") as status_file:
            status = status_file.read().format(
                TEST_SERVER_URL=resources.TEST_REMOTE_SERVER_URL,
                LOCATION_XML=status_url,
                OUTPUT_FILE=output_url,
            )

        ncdump_data = "Fake NetCDF Data"
        with contextlib.ExitStack() as stack_exec:
            # mock direct execution bypassing celery
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            # mock responses expected by "remote" WPS-1 Execute request and relevant documents
            mock_responses.add("GET", exec_file, body=ncdump_data, headers={"Content-Type": ContentType.APP_NETCDF})
            mock_responses.add("POST", resources.TEST_REMOTE_SERVER_URL, body=status, headers=self.xml_headers)
            mock_responses.add("GET", status_url, body=status, headers=self.xml_headers)
            mock_responses.add("GET", output_url, body=ncdump_data, headers={"Content-Type": ContentType.TEXT_PLAIN})

            # add reference to specific provider execute class to validate it was called
            # (whole procedure must run even though a lot of parts are mocked)
            real_wps1_process_execute = Wps1Process.execute
            handle_wps1_process_execute = stack_exec.enter_context(
                mock.patch.object(Wps1Process, "execute", side_effect=real_wps1_process_execute, autospec=True)
            )  # type: MockPatch

            # launch job execution and validate
            resp = mocked_sub_requests(self.app, "post_json", proc_exec_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            assert handle_wps1_process_execute.called, "WPS-1 handler should have been called by CWL runner context"

            status_url = resp.json["location"]
            job_id = resp.json["jobID"]
            assert status_url == f"{proc_exec_url}/{job_id}"
            results = self.monitor_job(status_url)
            wps_dir = self.settings["weaver.wps_output_dir"]
            wps_url = self.settings["weaver.wps_output_url"]
            output_url = f"{wps_url}/{job_id}/output/output.txt"
            output_path = f"{wps_dir}/{job_id}/output/output.txt"
            assert results["output"]["type"] == ContentType.TEXT_PLAIN
            assert results["output"]["href"] == output_url
            with open(output_path, mode="r", encoding="utf-8") as out_file:
                data = out_file.read()
            assert data == ncdump_data

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_HUMMINGBIRD_WPS1_GETCAP_XML,
        [resources.TEST_HUMMINGBIRD_DESCRIBE_WPS1_XML],
    ])
    def test_register_describe_execute_ncdump_no_default_format(self, mock_responses):
        """
        Test a remote :term:`WPS` provider that defines an optional input of ``ComplexData`` type with a default format.

        When the ``ComplexData`` input is omitted (allowed by ``minOccurs=0``), the execution parsing must **NOT**
        inject an input due to the detection of the default **format** (rather than default data/reference). If an
        input is erroneously injected, :mod:`pywps` tends to auto-generate an empty file (from the storage linked to
        the input), which yields an explicitly provided empty string value as ``ComplexData`` input.

        An example of such process is the ``ncdump`` that
        takes [0-100] ``ComplexData`` AND/OR [0-100] NetCDF OpenDAP URL strings as ``LiteralData``.
        """
        self.service_store.clear_services()

        # register the provider
        remote_provider_name = "test-wps-remote-provider-hummingbird"
        path = "/providers"
        data = {"id": remote_provider_name, "url": resources.TEST_REMOTE_SERVER_URL}
        resp = self.app.post_json(path, params=data, headers=self.json_headers)
        assert resp.status_code == 201

        exec_path = f"{self.url}/providers/{remote_provider_name}/processes/ncdump/execution"
        exec_file = "http://localhost.com/dont/care.nc"
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": [{"id": "dataset_opendap", "data": exec_file}],
            "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}]
        }
        status_url = f"{resources.TEST_REMOTE_SERVER_URL}/status.xml"
        output_url = f"{resources.TEST_REMOTE_SERVER_URL}/output.txt"
        with open(resources.TEST_HUMMINGBIRD_STATUS_WPS1_XML, mode="r", encoding="utf-8") as status_file:
            status = status_file.read().format(
                TEST_SERVER_URL=resources.TEST_REMOTE_SERVER_URL,
                LOCATION_XML=status_url,
                OUTPUT_FILE=output_url,
            )

        ncdump_data = "Fake NetCDF Data"
        with contextlib.ExitStack() as stack_exec:
            # mock direct execution bypassing celery
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            # mock responses expected by "remote" WPS-1 Execute request and relevant documents
            mock_responses.add("GET", exec_file, body=ncdump_data, headers={"Content-Type": ContentType.APP_NETCDF})
            mock_responses.add("POST", resources.TEST_REMOTE_SERVER_URL, body=status, headers=self.xml_headers)
            mock_responses.add("GET", status_url, body=status, headers=self.xml_headers)
            mock_responses.add("GET", output_url, body=ncdump_data, headers={"Content-Type": ContentType.TEXT_PLAIN})

            # add reference to specific provider class 'dispatch' to validate it was called with expected inputs
            # (whole procedure must run even though a lot of parts are mocked)
            # use the last possible method before sendoff to WPS, since filtering of omitted defaults can happen
            # at the very last moment to accommodate for CWL needing 'null' inputs explicitly in jobs submission
            real_wps1_process_dispatch = Wps1Process.dispatch
            handle_wps1_process_dispatch = stack_exec.enter_context(
                mock.patch.object(Wps1Process, "dispatch", side_effect=real_wps1_process_dispatch, autospec=True)
            )  # type: MockPatch

            # launch job execution and validate
            resp = mocked_sub_requests(self.app, "post_json", exec_path, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            assert handle_wps1_process_dispatch.called, "WPS-1 handler should have been called by CWL runner context"

            wps_exec_params = handle_wps1_process_dispatch.call_args_list[0].args
            wps_exec_inputs = wps_exec_params[1]
            assert isinstance(wps_exec_inputs, list), "WPS Inputs should have been passed for dispatch as 1st argument."
            wps_exec_inputs = dict(wps_exec_inputs)
            assert "dataset_opendap" in wps_exec_inputs, "Explicitly provided WPS inputs should be present."
            assert "dataset" not in wps_exec_inputs, "Omitted WPS input should not be injected in the request."
            assert wps_exec_inputs["dataset_opendap"] == exec_file
