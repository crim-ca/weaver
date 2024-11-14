import contextlib
import copy
import datetime
import json
import os
import tempfile
from typing import TYPE_CHECKING

import pytest
from owslib.crs import Crs
from pywps.inout.outputs import MetaFile, MetaLink4

from tests.functional.utils import WpsConfigBase
from tests.utils import (
    FileServer,
    get_settings_from_testapp,
    mocked_execute_celery,
    mocked_file_server,
    mocked_sub_requests
)
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import ContentEncoding, ContentType, get_format, repr_json
from weaver.processes.builtin import file_index_selector, jsonarray2netcdf, metalink2netcdf, register_builtin_processes
from weaver.processes.constants import JobInputsOutputsSchema
from weaver.status import Status
from weaver.utils import create_metalink, fully_qualified_name, get_path_kvp
from weaver.wps.utils import map_wps_output_location
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Any, Tuple

    from weaver.typedefs import ExecutionInputs, ExecutionOutputs, ExecutionResults, JSON, ProcessExecution


@pytest.mark.functional
class BuiltinAppTest(WpsConfigBase):
    file_server = None  # type: FileServer
    """
    File server made available to tests for emulating a remote HTTP location.
    """

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
        super(BuiltinAppTest, cls).setUpClass()

        cls.file_server = FileServer()
        cls.file_server.start()

    @classmethod
    def tearDownClass(cls):
        super(BuiltinAppTest, cls).tearDownClass()
        cls.file_server.teardown()

    def setUp(self):
        # register builtin processes from scratch to have clean state
        self.process_store.clear_processes()
        register_builtin_processes(self.settings)  # type: ignore  # not using registry since pre-configured by test

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

    def setup_jsonarray2netcdf_inputs(self, stack, use_temp_file=False):
        # type: (contextlib.ExitStack[Any], bool) -> Tuple[JSON, str]
        if use_temp_file:
            dir_path = tempfile.gettempdir()
            url_path = f"file://{dir_path}"
        else:
            dir_path = self.file_server.document_root
            url_path = self.file_server.uri
        nc_data = "Hello NetCDF!"
        tmp_ncdf = tempfile.NamedTemporaryFile(dir=dir_path, mode="w", suffix=".nc")     # pylint: disable=R1732
        tmp_json = tempfile.NamedTemporaryFile(dir=dir_path, mode="w", suffix=".json")   # pylint: disable=R1732
        tmp_ncdf = stack.enter_context(tmp_ncdf)  # noqa
        tmp_json = stack.enter_context(tmp_json)  # noqa
        tmp_ncdf.write(nc_data)
        tmp_ncdf.seek(0)
        tmp_json.write(json.dumps([f"{url_path}/{os.path.basename(tmp_ncdf.name)}"]))
        tmp_json.seek(0)
        body = {"inputs": [{"id": "input", "href": f"{url_path}/{os.path.basename(tmp_json.name)}"}]}
        return body, nc_data

    def validate_jsonarray2netcdf_results(self, results, outputs, data, links, exec_body):
        # first validate format of OGC-API results
        if results is not None:
            assert isinstance(results, dict)
            assert "output" in results, "Expected result ID 'output' in response body"
            assert isinstance(results["output"], dict), "Container of result ID 'output' should be a dict"
            assert "format" not in results["output"]  # old format not applied in results anymore
            out_defs = {out["id"]: out for out in exec_body["outputs"]}
            nc_href = None
            if out_defs.get("output", {}).get("transmissionMode") == ExecuteTransmissionMode.VALUE:
                assert "value" in results["output"]
                assert "mediaType" in results["output"]
                assert results["output"]["value"] == data
                assert results["output"]["mediaType"] == ContentType.APP_NETCDF
                assert "href" not in results["output"]
                assert "type" not in results["output"]
            else:
                assert "href" in results["output"]
                assert results["output"]["type"] == ContentType.APP_NETCDF, (
                    "Result 'output' format expected to be NetCDF file"
                )
                nc_href = results["output"]["href"]
                assert isinstance(nc_href, str) and len(nc_href)
                assert "value" not in results["output"]
                assert "mediaType" not in results["output"]
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
            with open(nc_real_path, mode="r", encoding="utf-8") as f:
                assert f.read() == data

        # if everything was valid for results, validate equivalent but differently formatted outputs response
        assert outputs["outputs"][0]["id"] == "output"
        nc_href = outputs["outputs"][0]["href"]
        assert isinstance(nc_href, str) and len(nc_href)
        assert nc_href.startswith(wps_out)
        nc_real_path = nc_href.replace(wps_out, wps_dir)
        assert os.path.split(nc_real_path)[-1] == os.path.split(nc_href)[-1]

    def test_jsonarray2netcdf_execute_invalid_file_local(self):
        """
        Validate that local file path as input is not permitted anymore.
        """
        with contextlib.ExitStack() as stack_exec:
            body, _ = self.setup_jsonarray2netcdf_inputs(stack_exec, use_temp_file=True)
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
        assert resp.status_code == 201

        job_url = resp.json["location"]
        job_res = self.monitor_job(job_url, expect_failed=True, return_status=True)
        assert job_res["status"] == Status.FAILED
        job_logs = self.app.get(f"{job_url}/logs").json
        assert any("ValueError: Not a valid file URL reference" in log for log in job_logs)

    def test_jsonarray2netcdf_execute_async(self):
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_jsonarray2netcdf_inputs(stack_exec)
            body.update({
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.REFERENCE}],
            })
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=self.json_headers, only_local=True)

        assert resp.status_code == 201, f"Error:\n{repr_json(resp.text, indent=2)}"
        assert resp.content_type in ContentType.APP_JSON
        # following details not available yet in async, but are in sync
        assert "created" not in resp.json
        assert "finished" not in resp.json
        assert "duration" not in resp.json
        assert "progress" not in resp.json
        assert "outputs" not in resp.json

        job_url = resp.json["location"]
        assert "Location" in resp.headers
        assert resp.headers["Location"] == job_url
        results = self.monitor_job(job_url)

        output_url = get_path_kvp(f"{job_url}/outputs", schema=JobInputsOutputsSchema.OLD)
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{repr_json(resp.text, indent=2)}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(results, outputs, nc_data, None, body)

    def test_jsonarray2netcdf_execute_async_output_by_reference_response_document(self):
        """
        Jobs submitted with ``response=document`` with ``transmissionMode`` by reference.

        The results schema should always be returned when document is requested.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-document

        .. versionchanged:: 6.0
            Removed the "don't care" aspect of the test, since ``transmissionMode`` is now respected.
            Therefore, ``transmissionMode=reference`` is explicitly requested.
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_jsonarray2netcdf_inputs(stack_exec)
            body.update({
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,  # by value/reference doesn't matter because of this
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.REFERENCE}],
            })
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=self.json_headers, only_local=True)

        assert resp.content_type in ContentType.APP_JSON
        assert resp.status_code == 201, f"Error:\n{repr_json(resp.text, indent=2)}"
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
        output_url = get_path_kvp(f"{job_url}/outputs", schema=JobInputsOutputsSchema.OLD)
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{resp.text}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(results, outputs, nc_data, result_links, body)

    def test_jsonarray2netcdf_execute_async_output_by_value_response_raw(self):
        """
        Jobs submitted with ``response=raw`` and single output as ``transmissionMode=value`` must return its raw data.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-value-one
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_jsonarray2netcdf_inputs(stack_exec)
            body.update({
                "mode": ExecuteMode.ASYNC,
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
        assert resp.status_code == 201, f"Error:\n{repr_json(resp.text, indent=2)}"
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
        output_url = get_path_kvp(f"{job_url}/outputs", schema=JobInputsOutputsSchema.OLD)
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{resp.text}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(None, outputs, nc_data, result_links, body)

    def test_jsonarray2netcdf_execute_async_output_by_reference_response_raw(self):
        """
        Jobs submitted with ``response=raw`` and single output as ``transmissionMode=reference`` must a link.

        Contents should be empty, and the reference should be provided with HTTP ``Link`` header.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-ref
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_jsonarray2netcdf_inputs(stack_exec)
            body.update({
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.RAW,  # by value/reference important here
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.REFERENCE}],  # Link header
            })
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=self.json_headers, only_local=True)

        assert resp.content_type in ContentType.APP_JSON
        assert resp.status_code == 201, f"Error:\n{repr_json(resp.text, indent=2)}"
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
        output_url = get_path_kvp(f"{job_url}/outputs", schema=JobInputsOutputsSchema.OLD)
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{repr_json(resp.text, indent=2)}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(None, outputs, nc_data, result_links, body)

    def test_jsonarray2netcdf_execute_sync(self):
        """
        Job submitted with ``mode=sync`` or ``Prefer`` header for sync should respond directly with the results schema.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#sc_execute_response
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_jsonarray2netcdf_inputs(stack_exec)
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
        # status link is available for reference as needed
        # however, 'Location' header is not provided since there is no need to redirect
        assert "Location" not in resp.headers
        link_headers = [ref for hdr, ref in resp.headerlist if hdr == "Link"]
        link_relations = ["status", "monitor"]
        link_job_status = [link for link in link_headers if any(f"rel=\"{rel}\"" in link for rel in link_relations)]
        assert len(link_job_status) == len(link_relations)
        # validate sync was indeed applied (in normal situation, not considering mock test that runs in sync)
        assert resp.headers["Preference-Applied"] == headers["Prefer"]
        # following details should not be available since results are returned in sync instead of async job status
        for field in ["status", "created", "finished", "duration", "progress"]:
            assert field not in resp.json

        # since sync response is represented as 'document',
        # the 'Content-Location' header must indicate the Job Results endpoint
        # that allows retrieving the same results at a later time
        assert "Content-Location" in resp.headers
        assert resp.headers["Content-Location"].endswith("/results")
        job_results_url = resp.headers["Content-Location"]
        job_url = job_results_url.rsplit("/results", 1)[0]

        # validate that job can still be found and its metadata are defined although executed in sync
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

        output_url = get_path_kvp(f"{job_url}/outputs", schema=JobInputsOutputsSchema.OLD)
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{repr_json(resp.text, indent=2)}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(results, outputs, nc_data, None, body)

    def test_echo_process_describe(self):
        resp = self.app.get("/processes/EchoProcess", headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type in ContentType.APP_JSON
        body = resp.json
        assert list(body["inputs"]) == [
            "stringInput",
            "measureInput",
            "dateInput",
            "doubleInput",
            "arrayInput",
            "complexObjectInput",
            "geometryInput",
            "boundingBoxInput",
            "imagesInput",
            "featureCollectionInput",
        ]
        assert list(body["outputs"]) == [
            "stringOutput",
            "measureOutput",
            "dateOutput",
            "doubleOutput",
            "arrayOutput",
            "complexObjectOutput",
            "geometryOutput",
            "boundingBoxOutput",
            "imagesOutput",
            "featureCollectionOutput",
        ]

    def setup_echo_process_execution_body(self, stack):
        # type: (contextlib.ExitStack[Any]) -> ProcessExecution
        tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())  # pylint: disable=R1732
        tmp_feature_collection_geojson = stack.enter_context(
            tempfile.NamedTemporaryFile(suffix=".geojson", mode="w", dir=tmp_dir)  # pylint: disable=R1732
        )
        json.dump(
            {
                "$schema": "https://geojson.org/schema/FeatureCollection.json",
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "test"},
                        "geometry": {
                            "type": "Point",
                            "coordinates": [1.2, 3.4, 5.6],  # 3D point
                        }
                    }
                ],
            },
            tmp_feature_collection_geojson,
        )
        tmp_feature_collection_geojson.flush()
        tmp_feature_collection_geojson.seek(0)
        inputs = {
            "stringInput": "Value2",
            "dateInput": datetime.datetime.utcnow().isoformat(),
            "doubleInput": 3.1416,
            "arrayInput": [1, 2, 3],
            # all following objects MUST be under 'value' to form a 'qualifiedInputValue' (or nested objects for list)
            # generic 'object' directly provided inline is forbidden (ie: 'inputValueNoObject')
            # https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/inlineOrRefData.yaml
            "complexObjectInput": {
                "value": {
                    "property1": "abc",
                    "property2": "https://example.com",
                    "property3": 1.234,
                    # "property4": "<date-time>",  # omitted on purpose, not required by schema
                    "property5": True,
                }
            },
            "geometryInput": [
                {
                    "value": {"type": "Point", "coordinates": [1, 2]},
                    "mediaType": ContentType.APP_GEOJSON,
                },
                {
                    "value": {
                        "type": "Polygon",
                        "coordinates": [[[1, 2], [3, 4], [5, 6], [7, 8], [9, 1], [1, 2]]]
                    },
                    # purposely not using 'geo+json' here to test format selection, use the 'OGC' GeoJSON
                    # (see the process definition, distinct schema references)
                    "mediaType": ContentType.APP_JSON,
                }
            ],
            # this is also considered a generic 'object' by OGC API that must be provided as 'qualifiedInputValue'
            # however, we have special handling logic in Weaver since those measurements can be mapped to WPS I/O
            # which define similar properties for literal values
            "measureInput": {"value": {"measurement": 9.81, "uom": "m/s²"}},
            # this is a special type known to OGC
            # https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/bbox.yaml
            "boundingBoxInput": {
                "bbox": [51.9, 7., 52., 7.1],
                "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            },
            "imagesInput": [
                {
                    "value": ContentEncoding.encode("random-tiff", ContentEncoding.BASE64),
                    "mediaType": ContentType.IMAGE_OGC_GEOTIFF,
                    "encoding": ContentEncoding.BASE64,
                },
            ],
            "featureCollectionInput": {
                "href": f"file://{tmp_feature_collection_geojson.name}",
                "type": ContentType.APP_GEOJSON,
                "schema": "https://geojson.org/schema/FeatureCollection.json",
            }
        }
        outputs = {
            "geometryOutput": {
                "format": {
                    "mediaType": ContentType.APP_JSON,
                }
            },
            "imagesOutput": {
                "format": {
                    "mediaType": ContentType.IMAGE_OGC_GEOTIFF,
                    "encoding": ContentEncoding.BASE64,
                }
            },
            "featureCollectionOutput": {
                "format": {
                    "mediaType": ContentType.APP_GEOJSON,
                    "schema": "https://geojson.org/schema/FeatureCollection.json",
                }
            }
        }
        # ensure outputs are not filtered, request all explicitly,
        # but auto-resolve transmissionMode/format for missing ones
        missing_outputs = {out.replace("Input", "Output") for out in inputs}
        for out in missing_outputs:
            if out not in outputs:
                outputs[out] = {}
        body = {
            "inputs": inputs,
            "outputs": outputs,
        }
        return body

    def test_echo_process_execute_inputs_valid_schema(self):
        """
        Validate that submitted inputs are properly defined and that schema interprets them correctly for validation.

        .. note::
            This validation serves 2 purposes.

            1. It ensures that expected :term:`OGC` example ``EchoProcess`` formats are supported.
            2. It ensures that :class:`weaver.wps_restapi.swagger_definitions.ExecuteInputValues` deserialization
               behaves correctly. In older versions, some invalid :term:`JSON`-formatted inputs not fulfilling any
               schema validation were silently dropped. Execution could still be aborted due to missing inputs, but
               if the inputs failing schema validation happened to be optional, those could not be propagated correctly.

        .. versionadded:: 4.35
        .. versionadded:: 6.0
            Modified defaults that are not the same anymore to allow alternative request combinations.
        """
        with contextlib.ExitStack() as stack:
            body = self.setup_echo_process_execution_body(stack)
            payload = sd.Execute().deserialize(body)
        expect_defaults = {
            "$schema": sd.Execute._schema,
            "mode": ExecuteMode.AUTO,
            # not auto-default anymore, but default in code if omitted, to allow 'Prefer' override
            # "response": ExecuteResponse.DOCUMENT,
        }
        expect_input_defaults = {
            "measureInput": {"mediaType": ContentType.APP_JSON},
            "boundingBoxInput": {"$schema": sd.ExecuteInputInlineBoundingBox._schema},
            "complexObjectInput": {"mediaType": ContentType.APP_JSON},
        }
        expect_output_defaults = {
            # 'value' is not default anymore, to allow auto-resolution of data/link by result literal/complex type
            "imagesOutput": {},  # {"transmissionMode": ExecuteTransmissionMode.VALUE},
            "geometryOutput": {},  # {"transmissionMode": ExecuteTransmissionMode.VALUE},
            "featureCollectionOutput": {},  # {"transmissionMode": ExecuteTransmissionMode.VALUE},
        }
        body.update(expect_defaults)
        for io_holder, io_defaults in [("inputs", expect_input_defaults), ("outputs", expect_output_defaults)]:
            for io_key, io_val in body[io_holder].items():
                if io_key in io_defaults:
                    if isinstance(io_val, list):
                        for _ in range(len(io_val)):
                            io_val[0].update(io_defaults[io_key][0])
                    else:
                        io_val.update(io_defaults[io_key])
        assert payload == body

    def validate_echo_process_results(self, results, inputs, outputs):
        # type: (ExecutionResults, ExecutionInputs, ExecutionOutputs) -> None
        """
        Validate that the outputs from the example ``EchoProcess``.

        Expect that the results are directly provided, as per OGC-formatted results schema.
        Since this process simply echos the inputs to corresponding outputs, inputs are used to test expected results.
        """
        assert list(results) == [
            "stringOutput",
            "measureOutput",
            "dateOutput",
            "doubleOutput",
            "arrayOutput",
            "complexObjectOutput",
            "geometryOutput",
            "boundingBoxOutput",
            "imagesOutput",
            "featureCollectionOutput",
        ]

        # generic literals should be directly equal
        for out_id in [
            "stringOutput",
            "dateOutput",
            "doubleOutput",
            "arrayOutput",
        ]:
            in_id = out_id.replace("Output", "Input")
            if isinstance(results[out_id], dict) and "value" in results[out_id]:
                res_val = results[out_id].get("value", results[out_id])
            else:
                res_val = results[out_id]
            assert res_val == inputs[in_id]

        # special literal/bbox object handling
        for out_id, res_fields_map in [
            (
                "measureOutput",
                [
                    (["value", "measurement"], []),  # ["value"]),  # now returned directly for literal
                ]
            ),
            (
                "boundingBoxOutput",
                [
                    (["bbox"], ["bbox"]),
                    (Crs(inputs["boundingBoxInput"]["crs"]).getcodeurn(), ["crs"]),
                ]
            ),
        ]:
            in_id = out_id.replace("Output", "Input")
            for field_map in res_fields_map:
                in_val_nested = inputs[in_id]
                res_val_nested = results[out_id]
                if isinstance(field_map[0], list):
                    for nested_field in field_map[0]:
                        in_val_nested = in_val_nested[nested_field]
                else:
                    in_val_nested = field_map[0]
                for nested_field in field_map[1]:
                    res_val_nested = res_val_nested[nested_field]
                assert res_val_nested == in_val_nested

        # complex outputs, contents should be the same, but stage-out URL is expected
        outputs = copy.deepcopy(outputs)
        outputs = {out["id"]: out for out in outputs} if isinstance(outputs, list) else outputs
        for out_id in [
            "complexObjectOutput",
            "geometryOutput",
            "imagesOutput",
            "featureCollectionOutput",
        ]:
            in_id = out_id.replace("Output", "Input")
            in_items = copy.deepcopy(inputs[in_id])
            out_items = copy.deepcopy(outputs[out_id])
            res_items = copy.deepcopy(results[out_id])
            in_items = [in_items] if isinstance(in_items, dict) else in_items
            out_items = [out_items] if isinstance(out_items, dict) else out_items
            res_items = [res_items] if isinstance(res_items, dict) else res_items
            assert len(in_items) == len(res_items)
            for in_def, out_def, res_def in zip(in_items, out_items, res_items):
                # inputs use local paths (mocked by test for "remote" locations) or literal JSON
                in_path = in_def.pop("href", None)
                in_path = in_path[7:] if str(in_path).startswith("file://") else in_path
                in_as_data = not in_path
                if in_as_data:
                    in_data = in_def.pop("value")
                    in_data = (json.dumps(in_data) if isinstance(in_data, dict) else in_data).encode()
                    in_data = ContentEncoding.decode(in_data) if in_def.get("encoding") == "base64" else in_data
                else:
                    with open(in_path, mode="rb") as in_file:
                        in_data = in_file.read()

                # validate output result against requested output transmission mode
                out_mode = out_def.get("transmissionMode", ExecuteTransmissionMode.REFERENCE)
                if out_mode == ExecuteTransmissionMode.REFERENCE:
                    assert "href" in res_def
                    assert "value" not in res_def
                    res_url = res_def.pop("href")  # compare the rest of the metadata after
                    res_path = map_wps_output_location(res_url, self.settings, url=False)
                    # use binary comparison since some contents are binary and others not
                    with open(res_path, mode="rb") as res_file:
                        res_data = res_file.read()
                    assert res_data == in_data
                    # even if the input was provided directly as JSON,
                    # the output will be provided as reference (return=minimal)
                    if in_def != {}:
                        in_type = in_def["mediaType"] if in_as_data else in_def["type"]
                        assert res_def["type"] == in_type, (
                            "Since explicit format was specified, the same is expected as output"
                        )
                    else:
                        assert res_def["type"] == ContentType.APP_JSON, (
                            "Since no explicit format was specified, at least needs to be JSON"
                        )
                else:
                    assert "href" not in res_def
                    assert "value" in res_def
                    res_data = res_def.pop("value")  # compare the rest of the metadata after
                    res_data = (json.dumps(res_data) if isinstance(res_data, dict) else res_data).encode()
                    res_data = ContentEncoding.decode(res_data) if in_def.get("encoding") == "base64" else res_data
                    assert res_data == in_data
                    # even if the input was provided directly as JSON,
                    # the output will be provided as reference (return=minimal)
                    if in_def != {}:
                        in_type = in_def["mediaType"] if in_as_data else in_def["type"]
                        assert res_def["mediaType"] == in_type, (
                            "Since explicit format was specified, the same is expected as output"
                        )
                    else:
                        assert res_def["mediaType"] == ContentType.APP_JSON, (
                            "Since no explicit format was specified, at least needs to be JSON"
                        )

    def test_echo_process_execute_sync(self):
        """
        Job submitted in ``sync`` mode with multiple input/output types.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#sc_execute_response

        .. versionadded:: 4.35
        """
        with contextlib.ExitStack() as stack_exec:
            body = self.setup_echo_process_execution_body(stack_exec)
            body.update({"response": ExecuteResponse.DOCUMENT})
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            headers = {"Prefer": "wait=10"}
            headers.update(self.json_headers)
            path = "/processes/EchoProcess/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=headers, only_local=True)

            assert resp.status_code == 200, f"Error: {resp.text}"
            assert resp.content_type in ContentType.APP_JSON

            # since sync, results are directly available instead of job status
            # even if results are returned directly (instead of status),
            # status link is available for reference as needed
            # however, 'Location' header is not provided since there is no need to redirect
            assert "Location" not in resp.headers
            link_headers = [ref for hdr, ref in resp.headerlist if hdr == "Link"]
            link_relations = ["status", "monitor"]
            link_job_status = [link for link in link_headers if any(f"rel=\"{rel}\"" in link for rel in link_relations)]
            assert len(link_job_status) == len(link_relations)

            # validate sync was indeed applied (in normal situation, not considering mock test that runs in sync)
            assert resp.headers["Preference-Applied"] == headers["Prefer"]
            # following details should not be available since results are returned in sync instead of async job status
            for field in ["status", "created", "finished", "duration", "progress"]:
                assert field not in resp.json
            results = resp.json
            self.validate_echo_process_results(results, body["inputs"], body["outputs"])

    def test_echo_process_execute_async(self):
        """
        Validate the example and builtin ``EchoProcess`` in ``async`` execution mode.

        .. versionadded:: 4.35
        """
        with contextlib.ExitStack() as stack_exec:
            body = self.setup_echo_process_execution_body(stack_exec)
            body.update({
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
            })
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            path = "/processes/EchoProcess/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=body, headers=self.json_headers, only_local=True)

            assert resp.status_code == 201, f"Error:\n{repr_json(resp.text, indent=2)}"
            assert resp.content_type in ContentType.APP_JSON
            # following details not available yet in async, but are in sync
            assert "created" not in resp.json
            assert "finished" not in resp.json
            assert "duration" not in resp.json
            assert "progress" not in resp.json
            assert "outputs" not in resp.json

            job_url = resp.json["location"]
            results = self.monitor_job(job_url)
            self.validate_echo_process_results(results, body["inputs"], body["outputs"])


def test_jsonarray2netcdf_process():
    with contextlib.ExitStack() as stack:
        data = {}
        for idx in range(3):
            tmp_nc = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=".nc"))
            tmp_nc_data = f"data NetCDF {idx}"
            tmp_nc.write(tmp_nc_data)
            tmp_nc.flush()
            tmp_nc.seek(0)
            tmp_nc_href = f"file://{tmp_nc.name}"
            data[tmp_nc_href] = tmp_nc_data
        tmp_json = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=".json"))
        json.dump(list(data), tmp_json, indent=2)
        tmp_json.flush()
        tmp_json.seek(0)
        tmp_out_dir = stack.enter_context(tempfile.TemporaryDirectory())

        with pytest.raises(SystemExit) as err:
            jsonarray2netcdf.main("-i", tmp_json.name, "-o", tmp_out_dir)
        assert err.value.code in [None, 0]

        for nc_file, nc_data in data.items():
            nc_name = os.path.split(nc_file)[-1]
            nc_path = os.path.join(tmp_out_dir, nc_name)
            assert os.path.isfile(nc_path)
            with open(nc_path, mode="r", encoding="utf-8") as nc_ref:
                assert nc_ref.read() == nc_data


@pytest.mark.parametrize(
    "test_data",
    [
        1,
        "",
        "abc",
        {},
        [
            1,
            2,
        ],
        [
            "abc",
            "xyz",
        ],
        [
            "/tmp/does-not-exist/fake-file.txt",  # noqa
            "/tmp/does-not-exist/fake-file.nc",  # noqa
        ],
    ]
)
def test_jsonarray2netcdf_invalid_json(test_data):
    with contextlib.ExitStack() as stack:
        tmp_out_dir = stack.enter_context(tempfile.TemporaryDirectory())
        tmp_file = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=".json"))
        tmp_file.write(repr_json(test_data, force_string=True))
        tmp_file.flush()
        tmp_file.seek(0)

        with pytest.raises(ValueError) as err:
            jsonarray2netcdf.main("-i", tmp_file.name, "-o", tmp_out_dir)
        valid_errors = [
            "Invalid JSON file format, expected a plain array of NetCDF file URL strings.",
            "Invalid file format",
            "Not a valid file URL reference",
        ]
        assert any(error in str(err.value) for error in valid_errors), (
            f"Raised error ({fully_qualified_name(err.value)})[{err.value}] was not expected."
        )


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["-i"],
    ]
)
def test_jsonarray2netcdf_missing_params(args):
    with pytest.raises(SystemExit) as err:
        jsonarray2netcdf.main(*args)
    assert err.value.code == 2


def test_jsonarray2netcdf_invalid_out_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_out_dir = os.path.join(tmp_dir, "random")

        with pytest.raises(ValueError) as err:
            jsonarray2netcdf.main("-i", "", "-o", tmp_out_dir)
        assert "does not exist" in str(err.value)


@pytest.mark.parametrize(
    ["metalink_version", "metalink_ext", "test_index"],
    [
        (3, ".metalink", 2),
        (4, ".meta4", 2)
    ]
)
def test_metalink2netcdf_process(metalink_version, metalink_ext, test_index):
    with contextlib.ExitStack() as stack:
        data = {}
        tmp_src_dir = stack.enter_context(tempfile.TemporaryDirectory())
        tmp_src_host = "http://fake-server.com/data"
        for idx in range(3):
            tmp_nc = stack.enter_context(tempfile.NamedTemporaryFile(dir=tmp_src_dir, mode="w", suffix=".nc"))
            tmp_nc_data = f"data NetCDF {idx}"
            tmp_nc.write(tmp_nc_data)
            tmp_nc.flush()
            tmp_nc.seek(0)
            tmp_meta_href = os.path.join(tmp_src_host, os.path.split(tmp_nc.name)[-1])
            data[idx] = {
                "name": str(idx),
                "file": tmp_nc.name,
                "data": tmp_nc_data,
                "href": tmp_meta_href,
                "type": ContentType.APP_NETCDF,
            }

        metalink = create_metalink(
            files=list(data.values()),  # type: ignore
            version=metalink_version,   # type: ignore
            workdir=tmp_src_dir,
        )
        tmp_meta_xml = metalink.xml
        assert "file://" not in tmp_meta_xml, "Metalink IO handler incorrectly configured to test HTTP remote file."
        tmp_meta = stack.enter_context(tempfile.NamedTemporaryFile(dir=tmp_src_dir, mode="w", suffix=metalink_ext))
        tmp_meta.write(tmp_meta_xml)
        tmp_meta.flush()
        tmp_meta.seek(0)
        tmp_out_dir = stack.enter_context(tempfile.TemporaryDirectory())
        stack.enter_context(mocked_file_server(tmp_src_dir, tmp_src_host, settings={}))

        with pytest.raises(SystemExit) as err:
            metalink2netcdf.main("-i", tmp_meta.name, "-n", str(test_index), "-o", tmp_out_dir)
        assert err.value.code in [None, 0]

        for idx in range(3):
            nc_out_name = os.path.split(data[idx]["file"])[-1]
            nc_out_path = os.path.join(tmp_out_dir, nc_out_name)
            if idx + 1 == test_index:  # index is 1-based in XPath
                assert os.path.isfile(nc_out_path)
                with open(nc_out_path, mode="r", encoding="utf-8") as nc_out_file:
                    nc_out_data = nc_out_file.read()
                os.remove(nc_out_path)
                assert nc_out_data == data[idx]["data"]
            else:
                assert not os.path.isfile(nc_out_path)


def test_metalink2netcdf_reference_not_netcdf():
    with contextlib.ExitStack() as stack:
        metafile = MetaFile(fmt=get_format(ContentType.APP_NETCDF))
        tmp_text = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=".text"))
        tmp_text.write("dont care")
        tmp_text.flush()
        tmp_text.seek(0)
        metafile.file = tmp_text.name
        metalink = MetaLink4(identity="test", workdir=tempfile.gettempdir(), files=tuple([metafile]))
        tmp_meta = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=".meta4"))
        tmp_meta.write(metalink.xml)
        tmp_meta.flush()
        tmp_meta.seek(0)
        tmp_out_dir = stack.enter_context(tempfile.TemporaryDirectory())

        with pytest.raises(ValueError) as err:
            metalink2netcdf.main("-i", tmp_meta.name, "-n", "1", "-o", tmp_out_dir)
        assert "not a valid NetCDF" in str(err.value)


@pytest.mark.parametrize(
    "args",
    [
        ["-i"],
        ["-i", ""],
        ["-n"],
        ["-n", "1"],
    ]
)
def test_metalink2netcdf_missing_params(args):
    with pytest.raises(SystemExit) as err:
        metalink2netcdf.main(*args)
    assert err.value.code == 2


def test_metalink2netcdf_invalid_out_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_out_dir = os.path.join(tmp_dir, "random")

        with pytest.raises(ValueError) as err:
            metalink2netcdf.main("-i", "", "-n", "1", "-o", tmp_out_dir)
        assert "does not exist" in str(err.value)


def test_file_index_selector_process():
    with contextlib.ExitStack() as stack:
        data = {}
        test_files = []
        for idx, ext in enumerate([".txt", ".nc", ".tiff"]):
            tmp_file = stack.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=ext))
            tmp_data = f"data {idx}"
            tmp_file.write(tmp_data)
            tmp_file.flush()
            tmp_file.seek(0)
            tmp_href = f"file://{tmp_file.name}"
            data[idx] = {"name": tmp_file.name, "data": tmp_data, "href": tmp_href}
            test_files.append(tmp_href)
        tmp_out_dir = stack.enter_context(tempfile.TemporaryDirectory())

        test_index = 1
        with pytest.raises(SystemExit) as err:
            file_index_selector.main("-f", *test_files, "-i", str(test_index), "-o", tmp_out_dir)
        assert err.value.code in [None, 0]
        for idx, tmp_info in data.items():
            out_name = os.path.split(tmp_info["name"])[-1]
            out_path = os.path.join(tmp_out_dir, out_name)
            if idx == test_index:
                assert os.path.isfile(out_path)
                with open(out_path, mode="r", encoding="utf-8") as out_file:
                    out_data = out_file.read()
                os.remove(out_path)
                assert out_data == tmp_info["data"]
            else:
                assert not os.path.isfile(out_path)


@pytest.mark.parametrize(
    "args",
    [
        ["-f"],
        ["-f", ""],
        ["-i"],
        ["-i", "1"],
    ]
)
def test_file_index_selector_missing_params(args):
    with pytest.raises(SystemExit) as err:
        file_index_selector.main(*args)
    assert err.value.code == 2


def test_file_index_selector_invalid_out_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_out_dir = os.path.join(tmp_dir, "random")

        with pytest.raises(ValueError) as err:
            file_index_selector.main("-f", "", "-i", "1", "-o", tmp_out_dir)
        assert "does not exist" in str(err.value)
