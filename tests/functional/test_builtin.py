import contextlib
import json
import os
import tempfile
from typing import TYPE_CHECKING

import pytest

from tests.functional.utils import WpsConfigBase
from tests.utils import get_settings_from_testapp, mocked_execute_process, mocked_sub_requests
from weaver.execute import (
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_MODE_ASYNC,
    EXECUTE_RESPONSE_DOCUMENT,
    EXECUTE_TRANSMISSION_MODE_REFERENCE
)
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_NETCDF
from weaver.processes.builtin import register_builtin_processes

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
        cls.json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
        super(BuiltinAppTest, cls).setUpClass()

    def setUp(self):
        # register builtin processes from scratch to have clean state
        self.process_store.clear_processes()
        register_builtin_processes(self.settings)

    def test_jsonarray2netcdf_describe_old_schema(self):
        resp = self.app.get("/processes/jsonarray2netcdf?schema=OLD", headers=self.json_headers)
        body = resp.json
        assert resp.status_code == 200
        assert resp.content_type in CONTENT_TYPE_APP_JSON
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
        assert body["process"]["inputs"][0]["formats"][0]["mediaType"] == CONTENT_TYPE_APP_JSON
        assert isinstance(body["process"]["outputs"], list)
        assert len(body["process"]["outputs"]) == 1
        assert body["process"]["outputs"][0]["id"] == "output"
        assert isinstance(body["process"]["outputs"][0]["formats"], list)
        assert len(body["process"]["outputs"][0]["formats"]) == 1
        assert body["process"]["outputs"][0]["formats"][0]["mediaType"] == CONTENT_TYPE_APP_NETCDF
        assert body["jobControlOptions"] == [EXECUTE_CONTROL_OPTION_ASYNC]
        assert body["outputTransmission"] == [EXECUTE_TRANSMISSION_MODE_REFERENCE]

    def test_jsonarray2netcdf_describe_ogc_schema(self):
        resp = self.app.get("/processes/jsonarray2netcdf", headers=self.json_headers)
        body = resp.json
        assert resp.status_code == 200
        assert resp.content_type in CONTENT_TYPE_APP_JSON
        assert body["id"] == "jsonarray2netcdf"
        assert "abstract" not in body, "Deprecated 'abstract' should now be 'description'."
        assert body["description"] not in ["", None]
        assert body["executeEndpoint"] == "https://localhost/processes/jsonarray2netcdf/jobs"
        assert isinstance(body["inputs"], dict)
        assert len(body["inputs"]) == 1 and "input" in body["inputs"]
        assert "id" not in body["inputs"]["input"]
        assert isinstance(body["inputs"]["input"]["formats"], list)
        assert len(body["inputs"]["input"]["formats"]) == 1
        assert body["inputs"]["input"]["formats"][0]["mediaType"] == CONTENT_TYPE_APP_JSON
        assert isinstance(body["outputs"], dict)
        assert len(body["outputs"]) == 1 and "output" in body["outputs"]
        assert "id" not in body["outputs"]["output"]
        assert isinstance(body["outputs"]["output"]["formats"], list)
        assert len(body["outputs"]["output"]["formats"]) == 1
        assert body["outputs"]["output"]["formats"][0]["mediaType"] == CONTENT_TYPE_APP_NETCDF
        assert body["jobControlOptions"] == [EXECUTE_CONTROL_OPTION_ASYNC]
        assert body["outputTransmission"] == [EXECUTE_TRANSMISSION_MODE_REFERENCE]

    def test_jsonarray2netcdf_execute(self):
        dirname = tempfile.gettempdir()
        nc_data = "Hello NetCDF!"
        with contextlib.ExitStack() as stack_exec:
            tmp_ncdf = tempfile.NamedTemporaryFile(dir=dirname, mode="w", suffix=".nc")
            tmp_json = tempfile.NamedTemporaryFile(dir=dirname, mode="w", suffix=".json")
            tmp_ncdf = stack_exec.enter_context(tmp_ncdf)  # noqa
            tmp_json = stack_exec.enter_context(tmp_json)  # noqa
            tmp_ncdf.write(nc_data)
            tmp_ncdf.seek(0)
            tmp_json.write(json.dumps(["file://{}".format(os.path.join(dirname, tmp_ncdf.name))]))
            tmp_json.seek(0)
            data = {
                "mode": EXECUTE_MODE_ASYNC,
                "response": EXECUTE_RESPONSE_DOCUMENT,
                "inputs": [{"id": "input", "href": os.path.join(dirname, tmp_json.name)}],
                "outputs": [{"id": "output", "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE}],
            }

            for mock_exec in mocked_execute_process():
                stack_exec.enter_context(mock_exec)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path,
                                       data=data, headers=self.json_headers, only_local=True)

        assert resp.status_code == 201, "Error: {}".format(resp.json)
        assert resp.content_type in CONTENT_TYPE_APP_JSON
        job_url = resp.json["location"]
        results = self.monitor_job(job_url)

        # first validate format of OGC-API results
        assert "output" in results, "Expected result ID 'output' in response body"
        assert isinstance(results["output"], dict), "Container of result ID 'output' should be a dict"
        assert "href" in results["output"]
        assert "format" in results["output"]
        fmt = results["output"]["format"]  # type: JSON
        assert isinstance(fmt, dict), "Result format should be provided with content details"
        assert "mediaType" in fmt
        assert isinstance(fmt["mediaType"], str), "Result format Content-Type should be a single string definition"
        assert fmt["mediaType"] == CONTENT_TYPE_APP_NETCDF, "Result 'output' format expected to be NetCDF file"
        nc_path = results["output"]["href"]
        assert isinstance(nc_path, str) and len(nc_path)
        settings = get_settings_from_testapp(self.app)
        wps_out = "{}{}".format(settings.get("weaver.url"), settings.get("weaver.wps_output_path"))
        nc_real_path = nc_path.replace(wps_out, settings.get("weaver.wps_output_dir"))
        assert nc_path.startswith(wps_out)
        assert os.path.split(nc_real_path)[-1] == os.path.split(nc_path)[-1]
        assert os.path.isfile(nc_real_path)
        with open(nc_real_path, "r") as f:
            assert f.read() == nc_data

        # if everything was valid for results, validate equivalent but differently formatted outputs response
        output_url = job_url + "/outputs"
        resp = self.app.get(output_url, headers=self.json_headers)
        assert resp.status_code == 200, "Error job outputs:\n{}".format(resp.json)
        outputs = resp.json
        assert outputs["outputs"][0]["id"] == "output"
        nc_path = outputs["outputs"][0]["href"]
        assert isinstance(nc_path, str) and len(nc_path)
        assert nc_path.startswith(wps_out)
        assert os.path.split(nc_real_path)[-1] == os.path.split(nc_path)[-1]
