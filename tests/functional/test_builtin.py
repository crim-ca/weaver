import copy

import contextlib
import datetime
import json
import os
import tempfile
from typing import TYPE_CHECKING

import pytest

from tests.functional.utils import WpsConfigBase
from tests.utils import get_settings_from_testapp, mocked_execute_celery, mocked_sub_requests
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import ContentEncoding, ContentType, repr_json
from weaver.processes.builtin import register_builtin_processes
from weaver.status import Status
from weaver.wps.utils import map_wps_output_location
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from weaver.typedefs import ExecutionInputs, ExecutionResults, JSON


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

    def setup_jsonarray2netcdf_inputs(self, stack):
        tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())  # pylint: disable=R1732
        nc_data = "Hello NetCDF!"
        tmp_ncdf = tempfile.NamedTemporaryFile(dir=tmp_dir, mode="w", suffix=".nc")     # pylint: disable=R1732
        tmp_json = tempfile.NamedTemporaryFile(dir=tmp_dir, mode="w", suffix=".json")   # pylint: disable=R1732
        tmp_ncdf = stack.enter_context(tmp_ncdf)  # noqa
        tmp_json = stack.enter_context(tmp_json)  # noqa
        tmp_ncdf.write(nc_data)
        tmp_ncdf.seek(0)
        tmp_json.write(json.dumps([f"file://{os.path.join(tmp_dir, tmp_ncdf.name)}"]))
        tmp_json.seek(0)
        body = {"inputs": [{"id": "input", "href": os.path.join(tmp_dir, tmp_json.name)}]}
        return body, nc_data

    def validate_jsonarray2netcdf_results(self, results, outputs, data, links):
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
            with open(nc_real_path, mode="r", encoding="utf-8") as f:
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
            body, nc_data = self.setup_jsonarray2netcdf_inputs(stack_exec)
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

        output_url = f"{job_url}/outputs"
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{repr_json(resp.text, indent=2)}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(results, outputs, nc_data, None)

    def test_jsonarray2netcdf_execute_async_output_by_reference_dontcare_response_document(self):
        """
        Jobs submitted with ``response=document`` are not impacted by ``transmissionMode``.

        The results schema should always be returned when document is requested.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-document
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_jsonarray2netcdf_inputs(stack_exec)
            body.update({
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
        output_url = f"{job_url}/outputs"
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{resp.text}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(results, outputs, nc_data, result_links)

    def test_jsonarray2netcdf_execute_async_output_by_value_response_raw(self):
        """
        Jobs submitted with ``response=raw`` and single output as ``transmissionMode=value`` must return its raw data.

        .. seealso::
            https://docs.ogc.org/is/18-062r2/18-062r2.html#req_core_process-execute-sync-raw-value-one
        """
        with contextlib.ExitStack() as stack_exec:
            body, nc_data = self.setup_jsonarray2netcdf_inputs(stack_exec)
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
        output_url = f"{job_url}/outputs"
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{resp.text}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(None, outputs, nc_data, result_links)

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
        resp = self.app.get(f"{job_url}/outputs", headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{repr_json(resp.text, indent=2)}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(None, outputs, nc_data, result_links)

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

        output_url = f"{job_url}/outputs"
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, f"Error job outputs:\n{repr_json(resp.text, indent=2)}"
        outputs = resp.json

        self.validate_jsonarray2netcdf_results(results, outputs, nc_data, None)

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
                "href": tmp_feature_collection_geojson.name,
                "type": ContentType.APP_GEOJSON,
                "schema": "https://geojson.org/schema/FeatureCollection.json",
            }
        }
        outputs = {
            "geometryOutput": {
                "mediaType": ContentType.APP_JSON,
                "schema": " http://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/schemas/geometryGeoJSON.yaml"
            },
            "imagesOutput": {
                "mediaType": ContentType.IMAGE_OGC_GEOTIFF,
                "encoding": ContentEncoding.BASE64,
            },
            "featureCollectionOutput": {
                "mediaType": ContentType.APP_GEOJSON,
                "schema": "https://geojson.org/schema/FeatureCollection.json",
            }
        }
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
        """
        with contextlib.ExitStack() as stack:
            body = self.setup_echo_process_execution_body(stack)
            payload = sd.Execute().deserialize(body)
        expect_defaults = {
            "$schema": sd.Execute._schema,
            "mode": ExecuteMode.AUTO,
            "response": ExecuteResponse.DOCUMENT,
            "outputs": {},
        }
        expect_input_defaults = {
            "measureInput": {"mediaType": ContentType.APP_JSON},
            "boundingBoxInput": {"$schema": sd.ExecuteInputInlineBoundingBox._schema},
            "geometryInput": [{"mediaType": ContentType.APP_JSON}, {}],
            "complexObjectInput": {"mediaType": ContentType.APP_JSON},
        }
        body.update(expect_defaults)
        for input_key, input_val in body["inputs"].items():
            if input_key in expect_input_defaults:
                if isinstance(input_val, list):
                    for i in range(len(input_val)):
                        input_val[0].update(expect_input_defaults[input_key][0])
                else:
                    input_val.update(expect_input_defaults[input_key])
        assert payload == body

    def validate_echo_process_results(self, results, inputs):
        # type: (ExecutionResults, ExecutionInputs) -> None
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
            # FIXME: unsupported multi-output cardinality (https://github.com/crim-ca/weaver/issues/25)
            # "arrayOutput",
        ]:
            in_id = out_id.replace("Output", "Input")
            out_val = results[out_id].get("value", results[out_id])
            assert out_val == inputs[in_id]
        # FIXME: unsupported multi-output cardinality (https://github.com/crim-ca/weaver/issues/25)
        assert results["arrayOutput"]["value"] == inputs["arrayInput"][0]

        # special literal/bbox object handling
        for out_id, out_fields_map in [
            (
                "measureOutput",
                [
                    (["value", "measurement"], ["value"]),
                ]
            ),
            (
                "boundingBoxOutput",
                [
                    (["bbox"], ["value", "bbox"]),
                    (["crs"], ["value", "crs"]),
                ]
            ),
        ]:
            in_id = out_id.replace("Output", "Input")
            for field_map in out_fields_map:
                in_val_nested = inputs[in_id]
                out_val_nested = results[out_id]
                for nested_field in field_map[0]:
                    in_val_nested = in_val_nested[nested_field]
                for nested_field in field_map[1]:
                    out_val_nested = out_val_nested[nested_field]
                assert out_val_nested == in_val_nested

        # complex outputs, contents should be the same, but stage-out URL is expected
        for out_id in [
            "complexObjectOutput",
            "geometryOutput",
            "imagesOutput",
            "featureCollectionOutput",
        ]:
            in_id = out_id.replace("Output", "Input")
            in_items = copy.deepcopy(inputs[in_id])
            out_items = copy.deepcopy(results[out_id])
            in_items = [in_items] if isinstance(in_items, dict) else in_items
            out_items = [out_items] if isinstance(out_items, dict) else out_items
            # FIXME: unsupported multi-output cardinality (https://github.com/crim-ca/weaver/issues/25)
            if len(in_items) > 1:
                assert len(out_items) == 1
                in_items = in_items[:1]
            else:
                assert len(in_items) == len(out_items)
            for in_def, out_def in zip(in_items, out_items):
                assert "href" in out_def
                # inputs use local paths (mocked by test for "remote" locations) or literal JSON
                in_path = in_def.pop("href", None)
                out_url = out_def.pop("href")  # compare the rest of the metadata after
                out_path = map_wps_output_location(out_url, self.settings, url=False)
                # use binary comparison since some contents are binary and others not
                with open(out_path, mode="rb") as out_file:
                    out_data = out_file.read()
                in_as_data = not in_path
                if in_as_data:
                    in_data = json.dumps(in_def.pop("value")).encode()
                else:
                    with open(in_path, mode="rb") as in_file:
                        in_data = in_file.read()
                assert out_data == in_data
                # if input was provided directly as JSON, the output can still be provided as reference (return=minimal)
                if in_as_data:
                    if in_def != {}:
                        assert out_def["type"] == in_def["mediaType"], (
                            "Since explicit format was specified, the same is expected as output"
                        )
                    else:
                        assert out_def["type"] == ContentType.APP_JSON, (
                            "Since no explicit format was specified, at least needs to be JSON"
                        )
                else:
                    assert out_def == in_def, f"Remaining complex metadata should match '{in_id}' definition"

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
        # status location link is available for reference as needed
        assert "Location" in resp.headers
        # validate sync was indeed applied (in normal situation, not considering mock test that runs in sync)
        assert resp.headers["Preference-Applied"] == headers["Prefer"]
        # following details should not be available since results are returned in sync instead of async job status
        for field in ["status", "created", "finished", "duration", "progress"]:
            assert field not in resp.json
        results = resp.json
        self.validate_echo_process_results(results, body["inputs"])

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
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}],
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
        self.validate_echo_process_results(results, body["inputs"])
