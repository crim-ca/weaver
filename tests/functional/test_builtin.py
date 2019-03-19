from weaver.formats import CONTENT_TYPE_APP_JSON, CONTENT_TYPE_APP_NETCDF
from weaver.database import get_db
from weaver.processes.builtin import register_builtin_processes
from weaver.status import STATUS_SUCCEEDED
from tests.utils import (
    setup_config_with_mongodb,
    setup_config_with_pywps,
    setup_config_with_celery,
    get_test_weaver_config,
    get_test_weaver_app,
)
from tempfile import NamedTemporaryFile
from time import sleep
# noinspection PyPackageRequirements
import mock
# noinspection PyPackageRequirements
import pytest
import unittest
import pyramid.testing
import os


@pytest.mark.functional
class BuiltinAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}

    def setUp(self):
        settings = {
            "weaver.wps": True,
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
        }
        config = get_test_weaver_config(settings=settings)
        config = setup_config_with_mongodb(config)
        config = setup_config_with_pywps(config)
        config = setup_config_with_celery(config)
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

    # FIXME: fails with connection error...
    @pytest.mark.xfail(reason="process working on live server, but fails here")
    def test_jsonarray2netcdf_execute(self):
        dirname = "/tmp"
        ncdf_data = "Hello NetCDF!"
        with NamedTemporaryFile(dir=dirname) as ncdf_file, NamedTemporaryFile(dir=dirname) as json_file:
            ncdf_file.write(ncdf_data)
            ncdf_file.seek(0)
            json_file.write('["{}"]'.format(os.path.join(dirname, ncdf_file.name)))
            json_file.seek(0)
            data = {
                "mode": "async",
                "response": "document",
                "inputs": [{"id": "input", "href": os.path.join(dirname, json_file.name)}],
                "outputs": [{"id": "output", "transmissionMode": "reference"}],
            }
            # FIXME: fails with connection error...
            resp = self.app.post_json("/processes/jsonarray2netcdf/jobs", params=data, headers=self.json_headers)
            assert resp.status_code == 201
            assert resp.content_type in CONTENT_TYPE_APP_JSON
            job_url = resp.json["location"]
            ncdf_path = None
            for i in range(5):
                sleep(1)
                resp = self.app.get(job_url, headers=self.json_headers)
                if resp.status_code == 200 and resp.json["status"] == STATUS_SUCCEEDED:
                    resp = self.app.get("{}/result".format(job_url), headers=self.json_headers)
                    assert resp.status_code == 200
                    assert resp.json["outputs"][0]["id"] == "output"
                    ncdf_path = resp.json["outputs"][0]["href"]
                    break
            assert ncdf_path is not None
            assert os.path.isfile(ncdf_path)
            with open(ncdf_path, 'r') as f:
                assert f.read() == ncdf_data
