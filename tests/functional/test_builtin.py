import contextlib
import json
import os
import tempfile
from typing import TYPE_CHECKING

import pytest

from tests.functional.utils import WpsConfigBase
from tests.utils import get_settings_from_testapp, mocked_execute_celery, mocked_sub_requests
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import ContentType
from weaver.processes.builtin import register_builtin_processes
from weaver.status import Status

if TYPE_CHECKING:
    from weaver.typedefs import JSON


@pytest.mark.functional
class BuiltinAppTest(WpsConfigBase):
    @classmethod
    def setUpClass(cls):
        cls.settings = {
            "weaver.wps": True,
            "weaver.wps_output": True,
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_dir": "/tmp",  # nosec: B108 # don't care hardcoded for test
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
        }
        cls.json_headers = {"Accept": ContentType.APP_JSON, "Content-Type": ContentType.APP_JSON}
        super(BuiltinAppTest, cls).setUpClass()

    def setUp(self):
        # register builtin processes from scratch to have clean state
        self.process_store.clear_processes()
        register_builtin_processes(self.settings)

    def test_jsonarray2netcdf_describe_old_schema(self):
        resp = self.app.get("/processes/jsonarray2netcdf?schema=OLD", headers=self.json_headers)
        body = resp.json
        assert resp.status_code == 200
        assert resp.content_type in ContentType.APP_JSON
        assert "process" in body, "OLD schema process description should be nested under 'process' field."
        assert body["process"]["id"] == "jsonarray2netcdf"
        assert "abstract" not in body["process"], "Deprecated 'abstract' should now be 'description'."
        assert body["process"]["description"] not in ["", None]
        assert body["process"]["executeEndpoint"] == "https://localhost/processes/jsonarray2netcdf/jobs"
        assert isinstance(body["process"]["inputs"], list)
        assert len(body["process"]["inputs"]) == 1
        assert body["process"]["inputs"][0]["id"] == "input"
        assert isinstance(body["process"]["inputs"][0]["formats"], list)
        assert len(body["process"]["inputs"][0]["formats"]) == 1
        assert body["process"]["inputs"][0]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert isinstance(body["process"]["outputs"], list)
        assert len(body["process"]["outputs"]) == 1
        assert body["process"]["outputs"][0]["id"] == "output"
        assert isinstance(body["process"]["outputs"][0]["formats"], list)
        assert len(body["process"]["outputs"][0]["formats"]) == 1
        assert body["process"]["outputs"][0]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert body["jobControlOptions"] == [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC]
        assert body["outputTransmission"] == [ExecuteTransmissionMode.REFERENCE, ExecuteTransmissionMode.VALUE]

    def test_jsonarray2netcdf_describe_ogc_schema(self):
        resp = self.app.get("/processes/jsonarray2netcdf", headers=self.json_headers)
        body = resp.json
        assert resp.status_code == 200
        assert resp.content_type in ContentType.APP_JSON
        assert body["id"] == "jsonarray2netcdf"
        assert "abstract" not in body, "Deprecated 'abstract' should now be 'description'."
        assert body["description"] not in ["", None]
        assert body["executeEndpoint"] == "https://localhost/processes/jsonarray2netcdf/jobs"
        assert isinstance(body["inputs"], dict)
        assert len(body["inputs"]) == 1 and "input" in body["inputs"]
        assert "id" not in body["inputs"]["input"]
        assert isinstance(body["inputs"]["input"]["formats"], list)
        assert len(body["inputs"]["input"]["formats"]) == 1
        assert body["inputs"]["input"]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert isinstance(body["outputs"], dict)
        assert len(body["outputs"]) == 1 and "output" in body["outputs"]
        assert "id" not in body["outputs"]["output"]
        assert isinstance(body["outputs"]["output"]["formats"], list)
        assert len(body["outputs"]["output"]["formats"]) == 1
        assert body["outputs"]["output"]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert body["jobControlOptions"] == [ExecuteControlOption.ASYNC, ExecuteControlOption.SYNC]
        assert body["outputTransmission"] == [ExecuteTransmissionMode.REFERENCE, ExecuteTransmissionMode.VALUE]

    def setup_inputs(self, stack):
        dirname = tempfile.gettempdir()
        nc_data = "Hello NetCDF!"
        tmp_ncdf = tempfile.NamedTemporaryFile(dir=dirname, mode="w", suffix=".nc")
        tmp_json = tempfile.NamedTemporaryFile(dir=dirname, mode="w", suffix=".json")
        tmp_ncdf = stack.enter_context(tmp_ncdf)  # noqa
        tmp_json = stack.enter_context(tmp_json)  # noqa
        tmp_ncdf.write(nc_data)
        tmp_ncdf.seek(0)
        tmp_json.write(json.dumps([f"file://{os.path.join(dirname, tmp_ncdf.name)}"]))
        tmp_json.seek(0)
        body = {"inputs": [{"id": "input", "href": os.path.join(dirname, tmp_json.name)}]}
        return body, nc_data

    def validate_results(self, results, outputs, data, links):
        # first validate format of OGC-API results
        if results is not None:
            assert isinstance(results, dict)
            assert "output" in results, "Expected result ID 'output' in response body"
            assert isinstance(results["output"], dict), "Container of result ID 'output' should be a dict"
            assert "href" in results["output"]
            assert "format" in results["output"]
            fmt = results["output"]["format"]  # type: JSON
            assert isinstance(fmt, dict), "Result format should be provided with content details"
            assert "mediaType" in fmt
            assert isinstance(fmt["mediaType"], str), "Result format Content-Type should be a single string definition"
            assert fmt["mediaType"] == ContentType.APP_NETCDF, "Result 'output' format expected to be NetCDF file"
            nc_href = results["output"]["href"]
            assert isinstance(nc_href, str) and len(nc_href)
        elif links:
            assert isinstance(links, list) and len(links) == 1 and isinstance(links[0], tuple)
            assert "rel=\"output\"" in links[0][1]
            assert f"type={ContentType.APP_NETCDF}" in links[0][1]
            nc_link = links[0][1].split(" ")[0]
            assert nc_link.startswith("<") and nc_link.startswith(">")
            nc_href = nc_link[1:-1]
        else:
            nc_href = None

        settings = get_settings_from_testapp(self.app)
        wps_path = settings.get("weaver.wps_output_path")
        wps_dir = settings.get("weaver.wps_output_dir")
        wps_out = settings.get("weaver.url") + wps_path

        # validate results if applicable
        if nc_href is not None:
            nc_real_path = nc_href.replace(wps_out, wps_dir)
            assert nc_href.startswith(wps_out)
            assert os.path.split(nc_real_path)[-1] == os.path.split(nc_href)[-1]
            assert os.path.isfile(nc_real_path)
            with open(nc_real_path, "r") as f:
                assert f.read() == data

        # if everything was valid for results, validate equivalent but differently formatted outputs response
        assert outputs["outputs"][0]["id"] == "output"
        nc_href = outputs["outputs"][0]["href"]
        assert isinstance(nc_href, str) and len(nc_href)
        assert nc_href.startswith(wps_out)
        nc_real_path = nc_href.replace(wps_out, wps_dir)
        assert os.path.split(nc_real_path)[-1] == os.path.split(nc_href)[-1]

    def test_jsonarray2netcdf_execute_async(self):
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_inputs(stack_exec)
            body.update({
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}],
            })
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=self.json_headers, only_local=True)

        assert resp.status_code == 201, f"Error: {resp.json}"
        assert resp.content_type in ContentType.APP_JSON
        # following details not available yet in async, but are in sync
        assert "created" not in resp.json
        assert "finished" not in resp.json
        assert "duration" not in resp.json
        assert "progress" not in resp.json

        job_url = resp.json["location"]
        results = self.monitor_job(job_url)

        output_url = job_url + "/outputs"
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{resp.json}"
        outputs = resp.json

        self.validate_results(results, outputs, nc_data, None)

    def test_jsonarray2netcdf_execute_async_output_by_reference_dontcare_response_document(self):
        """
        Jobs submitted with ``response=document`` are not impacted by ``transmissionMode``.

        The results schema should always be returned when document is requested.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-document
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_inputs(stack_exec)
            body.update({
                "response": ExecuteResponse.DOCUMENT,  # by value/reference don't care because of this
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.REFERENCE}],
            })
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=self.json_headers, only_local=True)

        assert resp.content_type in ContentType.APP_JSON
        assert resp.status_code == 201, f"Error: {resp.json}"
        job_url = resp.json["location"]
        self.monitor_job(job_url, return_status=True)  # don't fetch results automatically

        resp = self.app.get(f"{job_url}/results", headers=self.json_headers)
        assert resp.status_code == 200, f"Error: {resp.text}"
        assert resp.content_type == ContentType.APP_JSON
        result_links = [hdr for hdr in resp.headers if hdr[0].lower() == "link"]
        assert len(result_links) == 0
        results = resp.json

        # even though results are requested by Link reference,
        # Weaver still offers them with document on outputs endpoint
        output_url = job_url + "/outputs"
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{resp.text}"
        outputs = resp.json

        self.validate_results(results, outputs, nc_data, result_links)

    def test_jsonarray2netcdf_execute_async_output_by_value_response_raw(self):
        """
        Jobs submitted with ``response=raw`` and single output as ``transmissionMode=value`` must return its raw data.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-value-one
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_inputs(stack_exec)
            body.update({
                "response": ExecuteResponse.RAW,  # by value/reference important here
                # NOTE: quantity of outputs important as well
                #       since single output, content-type is directly that output (otherwise should be multipart)
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}],  # data dump
            })
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=self.json_headers, only_local=True)

        assert resp.content_type in ContentType.APP_JSON
        assert resp.status_code == 201, f"Error: {resp.json}"
        job_url = resp.json["location"]
        self.monitor_job(job_url, return_status=True)  # don't fetch results automatically

        resp = self.app.get(f"{job_url}/results", headers=self.json_headers)
        assert resp.status_code < 400, f"Error: {resp.text}"
        assert resp.status_code == 200, "Body should contain literal raw data dump"
        assert resp.content_type in ContentType.APP_NETCDF, "raw result by value should be directly the content-type"
        assert resp.text == nc_data, "raw result by value should be directly the data content"
        assert resp.headers
        result_links = [hdr for hdr in resp.headers if hdr[0].lower() == "link"]
        assert len(result_links) == 0

        # even though results are requested by raw data,
        # Weaver still offers them with document on outputs endpoint
        output_url = job_url + "/outputs"
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{resp.text}"
        outputs = resp.json

        self.validate_results(None, outputs, nc_data, result_links)

    def test_jsonarray2netcdf_execute_async_output_by_reference_response_raw(self):
        """
        Jobs submitted with ``response=raw`` and single output as ``transmissionMode=reference`` must a link.

        Contents should be empty, and the reference should be provided with HTTP ``Link`` header.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-ref
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_inputs(stack_exec)
            body.update({
                "response": ExecuteResponse.RAW,  # by value/reference important here
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.REFERENCE}],  # Link header
            })
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=self.json_headers, only_local=True)

        assert resp.content_type in ContentType.APP_JSON
        assert resp.status_code == 201, f"Error: {resp.json}"
        job_url = resp.json["location"]
        self.monitor_job(job_url, return_status=True)  # don't fetch results automatically

        resp = self.app.get(f"{job_url}/results", headers=self.json_headers)
        assert resp.status_code < 400, f"Error: {resp.text}"
        assert resp.status_code == 204, "Body should be empty since all outputs requested by reference (Link header)"
        assert resp.content_type is None
        assert resp.headers
        result_links = [hdr for hdr in resp.headers if hdr[0] == "Link"]

        # even though results are requested by Link reference,
        # Weaver still offers them with document on outputs endpoint
        resp = self.app.get(f"{job_url}/outputs", headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{resp.json}"
        outputs = resp.json

        self.validate_results(None, outputs, nc_data, result_links)

    def test_jsonarray2netcdf_execute_sync(self):
        """
        Job submitted with ``mode=sync`` or ``Prefer`` header for sync should respond directly with the results schema.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#sc_execute_response
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_inputs(stack_exec)
            body.update({
                "response": ExecuteResponse.DOCUMENT,
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}]
            })
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            headers = {"Prefer": "wait=10"}
            headers.update(self.json_headers)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=headers, only_local=True)

        assert resp.status_code == 200, f"Error: {resp.text}"
        assert resp.content_type in ContentType.APP_JSON

        # since sync, results are directly available instead of job status
        # even if results are returned directly (instead of status),
        # status location link is available for reference as needed
        assert "Location" in resp.headers
        # validate sync was indeed applied (in normal situation, not considering mock test that runs in sync)
        assert resp.headers["Preference-Applied"] == headers["Prefer"]
        # following details should not be available since results are returned in sync instead of async job status
        for field in ["status", "created", "finished", "duration", "progress"]:
            assert field not in resp.json

        # validate that job can still be found and its metadata are defined although executed in sync
        job_url = resp.headers["Location"]
        resp = self.app.get(job_url, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        for field in ["status", "created", "finished", "duration", "progress"]:
            assert field in resp.json
        assert resp.json["status"] == Status.SUCCEEDED
        assert resp.json["progress"] == 100

        out_url = f"{job_url}/results"
        resp = self.app.get(out_url, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == ContentType.APP_JSON
        results = resp.json

        output_url = job_url + "/outputs"
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{resp.json}"
        outputs = resp.json

        self.validate_results(results, outputs, nc_data, None)
