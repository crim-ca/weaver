from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_NETCDF
from weaver.database import get_db
from weaver.processes.builtin import register_builtin_processes
from weaver.status import STATUS_SUCCEEDED, STATUS_CATEGORY_RUNNING, job_status_categories
from tests.utils import (
    ignore_deprecated_nested_warnings,
    setup_config_with_mongodb,
    setup_config_with_pywps,
    setup_config_with_celery,
    get_test_weaver_config,
    get_test_weaver_app,
    get_settings_from_testapp,
    mocked_execute_process,
    mocked_sub_requests,
)
from tempfile import NamedTemporaryFile
from time import sleep
from contextlib import ExitStack
import mock
import pytest
import unittest
import pyramid.testing
import json
import six
import os


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

    @ignore_deprecated_nested_warnings
    def test_jsonarray2netcdf_execute(self):
        dirname = "/tmp"
        nc_data = "Hello NetCDF!"
        with NamedTemporaryFile(dir=dirname, mode="w", suffix=".nc") as nf, \
             NamedTemporaryFile(dir=dirname, mode="w", suffix=".json") as jf:
            nf.write(nc_data)
            nf.seek(0)
            jf.write(json.dumps(["file://{}".format(os.path.join(dirname, nf.name))]))  # app expects list of URL
            jf.seek(0)
            data = {
                "mode": "async",
                "response": "document",
                "inputs": [{"id": "input", "href": os.path.join(dirname, jf.name)}],
                "outputs": [{"id": "output", "transmissionMode": "reference"}],
            }
            # noinspection PyDeprecation
            with ExitStack() as stack:
                for process in mocked_execute_process():
                    stack.enter_context(process)
                path = "/processes/jsonarray2netcdf/jobs"
                resp = mocked_sub_requests(self.app, "post_json", path, params=data, headers=self.json_headers)

            assert resp.status_code == 201
            assert resp.content_type in CONTENT_TYPE_APP_JSON
            job_url = resp.json["location"]
            nc_path = None
            for i in range(5):
                sleep(1)
                resp = self.app.get(job_url, headers=self.json_headers)
                if resp.status_code == 200:
                    if resp.json["status"] in job_status_categories[STATUS_CATEGORY_RUNNING]:
                        continue
                    assert resp.json["status"] == STATUS_SUCCEEDED
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
            with open(nc_real_path, 'r') as f:
                assert f.read() == nc_data
