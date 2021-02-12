import contextlib
import json
import os
import tempfile

import pytest

from tests.functional.utils import WpsPackageConfigBase
from tests.utils import get_settings_from_testapp, mocked_execute_process, mocked_sub_requests
from weaver.execute import EXECUTE_TRANSMISSION_MODE_REFERENCE
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_NETCDF
from weaver.processes.builtin import register_builtin_processes


@pytest.mark.functional
class BuiltinAppTest(WpsPackageConfigBase):
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

    def test_jsonarray2netcdf_describe(self):
        resp = self.app.get("/processes/jsonarray2netcdf", headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type in CONTENT_TYPE_APP_JSON
        assert resp.json["process"]["id"] == "jsonarray2netcdf"
        assert resp.json["process"]["abstract"] not in ["", None]
        assert resp.json["process"]["executeEndpoint"] == "https://localhost/processes/jsonarray2netcdf/jobs"
        assert isinstance(resp.json["process"]["inputs"], list)
        assert len(resp.json["process"]["inputs"]) == 1
        assert resp.json["process"]["inputs"][0]["id"] == "input"
        assert isinstance(resp.json["process"]["inputs"][0]["formats"], list)
        assert len(resp.json["process"]["inputs"][0]["formats"]) == 1
        assert resp.json["process"]["inputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert isinstance(resp.json["process"]["outputs"], list)
        assert len(resp.json["process"]["outputs"]) == 1
        assert resp.json["process"]["outputs"][0]["id"] == "output"
        assert isinstance(resp.json["process"]["outputs"][0]["formats"], list)
        assert len(resp.json["process"]["outputs"][0]["formats"]) == 1
        assert resp.json["process"]["outputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF

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
                "mode": "async",
                "response": "document",
                "inputs": [{"id": "input", "href": os.path.join(dirname, tmp_json.name)}],
                "outputs": [{"id": "output", "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE}],
            }

            for mock_exec in mocked_execute_process():
                stack_exec.enter_context(mock_exec)
            path = "/processes/jsonarray2netcdf/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path, data=data, headers=self.json_headers)

        assert resp.status_code == 201, "Error: {}".format(resp.json)
        assert resp.content_type in CONTENT_TYPE_APP_JSON
        job_url = resp.json["location"]
        results = self.monitor_job(job_url)
        assert results["outputs"][0]["id"] == "output"
        nc_path = results["outputs"][0]["href"]
        assert isinstance(nc_path, str) and len(nc_path)
        settings = get_settings_from_testapp(self.app)
        wps_out = "{}{}".format(settings.get("weaver.url"), settings.get("weaver.wps_output_path"))
        nc_real_path = nc_path.replace(wps_out, settings.get("weaver.wps_output_dir"))
        assert nc_path.startswith(wps_out)
        assert os.path.split(nc_real_path)[-1] == os.path.split(nc_path)[-1]
        assert os.path.isfile(nc_real_path)
        with open(nc_real_path, "r") as f:
            assert f.read() == nc_data
