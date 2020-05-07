import json
import os
import tempfile
import unittest
from time import sleep

import mock
import pyramid.testing
import pytest
import six

from tests.compat import contextlib
from tests.utils import (
    get_settings_from_testapp,
    get_test_weaver_app,
    get_test_weaver_config,
    mocked_execute_process,
    mocked_sub_requests,
    setup_config_with_celery,
    setup_config_with_mongodb,
    setup_config_with_pywps
)
from weaver.database import get_db
from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_NETCDF
from weaver.processes.builtin import register_builtin_processes
from weaver.status import JOB_STATUS_CATEGORIES, STATUS_CATEGORY_RUNNING, STATUS_SUCCEEDED


@pytest.mark.functional
class BuiltinAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}

    def setUp(self):
        settings = {
            "weaver.wps": True,
            "weaver.wps_output": True,
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_dir": "/tmp",  # nosec: B108 # don't care hardcoded for test
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
        }
        config = setup_config_with_mongodb(settings=settings)
        config = setup_config_with_pywps(config)
        config = setup_config_with_celery(config)
        config = get_test_weaver_config(config)
        self.app = get_test_weaver_app(config=config, settings=settings)
        db = get_db(config)
        with mock.patch("weaver.processes.builtin.get_db", return_value=db):
            db._stores = {}  # ensure reset of process store to register builtin processes from scratch
            register_builtin_processes(config)

    def tearDown(self):
        pyramid.testing.tearDown()

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
        with contextlib.ExitStack() as stack_files:
            tmp_ncdf = stack_files.enter_context(tempfile.NamedTemporaryFile(dir=dirname, mode="w", suffix=".nc"))
            tmp_json = stack_files.enter_context(tempfile.NamedTemporaryFile(dir=dirname, mode="w", suffix=".json"))
            tmp_ncdf.write(nc_data)
            tmp_ncdf.seek(0)
            tmp_json.write(json.dumps(["file://{}".format(os.path.join(dirname, tmp_ncdf.name))]))
            tmp_json.seek(0)
            data = {
                "mode": "async",
                "response": "document",
                "inputs": [{"id": "input", "href": os.path.join(dirname, tmp_json.name)}],
                "outputs": [{"id": "output", "transmissionMode": "reference"}],
            }
            with contextlib.ExitStack() as stack_proc:
                for process in mocked_execute_process():
                    stack_proc.enter_context(process)
                path = "/processes/jsonarray2netcdf/jobs"
                resp = mocked_sub_requests(self.app, "post_json", path, params=data, headers=self.json_headers)

            assert resp.status_code == 201
            assert resp.content_type in CONTENT_TYPE_APP_JSON
            job_url = resp.json["location"]
            nc_path = None
            for delay in range(5):
                sleep(delay)
                resp = self.app.get(job_url, headers=self.json_headers)
                if resp.status_code == 200:
                    if resp.json["status"] in JOB_STATUS_CATEGORIES[STATUS_CATEGORY_RUNNING]:
                        continue
                    assert resp.json["status"] == STATUS_SUCCEEDED, \
                        "Process execution failed. Response body:\n{}".format(resp.json)
                    resp = self.app.get("{}/result".format(job_url), headers=self.json_headers)
                    assert resp.status_code == 200
                    assert resp.json["outputs"][0]["id"] == "output"
                    nc_path = resp.json["outputs"][0]["href"]
                    break
            assert isinstance(nc_path, six.string_types) and len(nc_path)
            settings = get_settings_from_testapp(self.app)
            wps_out = "{}{}".format(settings.get("weaver.url"), settings.get("weaver.wps_output_path"))
            nc_real_path = nc_path.replace(wps_out, settings.get("weaver.wps_output_dir"))
            assert nc_path.startswith(wps_out)
            assert os.path.split(nc_real_path)[-1] == os.path.split(nc_path)[-1]
            assert os.path.isfile(nc_real_path)
            with open(nc_real_path, "r") as f:
                assert f.read() == nc_data
