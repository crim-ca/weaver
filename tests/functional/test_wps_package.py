from weaver.formats import (
    CONTENT_TYPE_APP_JSON,
    CONTENT_TYPE_APP_NETCDF,
    CONTENT_TYPE_TEXT_PLAIN,
    EDAM_NAMESPACE,
    EDAM_MAPPING,
)
from weaver.visibility import VISIBILITY_PUBLIC
from tests.utils import (
    get_test_weaver_config,
    get_test_weaver_app,
    setup_config_with_mongodb,
    setup_config_with_pywps,
    setup_mongodb_processstore,
    mocked_sub_requests,
)
from tests import resources
# noinspection PyPackageRequirements
import pytest
import unittest


@pytest.mark.functional
class WpsPackageAppTest(unittest.TestCase):
    def setUp(self):
        settings = {
            "weaver.wps": True,
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
        }
        config = setup_config_with_mongodb(settings=settings)
        config = setup_config_with_pywps(config)
        config = get_test_weaver_config(config)
        setup_mongodb_processstore(config)  # force reset
        self.app = get_test_weaver_app(config=config, settings=settings)

    def deploy_process(self, payload):
        """
        Deploys a process with ``payload``.
        :returns: resulting (process-description, package) JSON responses.
        """
        json_headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
        resp = mocked_sub_requests(self.app, "post_json", "/processes", params=payload, headers=json_headers)
        assert resp.status_code == 200  # TODO: status should be 201 when properly modified to match API conformance
        path = resp.json["processSummary"]["processDescriptionURL"]
        body = {"value": VISIBILITY_PUBLIC}
        resp = self.app.put_json("{}/visibility".format(path), params=body, headers=json_headers)
        assert resp.status_code == 200
        info = []
        for p in [path, "{}/package".format(path)]:
            resp = self.app.get(p, headers=json_headers)
            assert resp.status_code == 200
            info.append(resp.json)
        return info

    def test_literal_io_from_package(self):
        cwl = {

        }
        body = {
            "processDescription": {
                "process": {
                    "id": self.__name__,
                    "title": "some title",
                    "abstract": "this is a test",
                }
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, pkg = self.deploy_process(body)
        assert False

    def test_literal_io_from_package_and_offering(self):
        raise NotImplementedError

    def test_complex_io_from_package(self):
        raise NotImplementedError

    def test_complex_io_from_package_and_offering(self):
        raise NotImplementedError

    def test_literal_and_complex_io_from_wps_xml_reference(self):
        body = {
            "processDescription": {"process": {"id": self.__name__}},
            "executionUnit": [{"href": "mock://{}".format(resources.WMS_LITERAL_COMPLEX_IO)}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication"
        }
        desc, pkg = self.deploy_process(body)
        edam_plain = EDAM_NAMESPACE + ":" + EDAM_MAPPING[CONTENT_TYPE_TEXT_PLAIN]
        edam_netcdf = EDAM_NAMESPACE + ":" + EDAM_MAPPING[CONTENT_TYPE_APP_NETCDF]

        # basic contents validation
        assert "cwlVersion" in pkg
        assert "process" in desc
        assert desc["process"]["id"] == self.__name__

        # package I/O validation
        assert "inputs" in pkg
        assert len(pkg["inputs"]) == 2
        assert pkg["inputs"]["tasmax"]["default"]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert pkg["inputs"]["tasmax"]["default"]["encoding"] == "base64"
        assert pkg["inputs"]["tasmax"]["default"]["schema"] is None
        assert pkg["inputs"]["tasmax"]["format"] == edam_netcdf
        assert pkg["inputs"]["tasmax"]["type"]["type"] == "array"
        assert pkg["inputs"]["tasmax"]["type"]["items"] == "File"
        assert pkg["inputs"]["freq"]["default"] == "YS"
        assert pkg["inputs"]["freq"]["type"]["type"] == "enum"
        assert pkg["inputs"]["freq"]["type"]["symbols"] == ["YS", "MS", "QS-DEC", "AS-JUL"]
        assert "outputs" in pkg
        assert len(pkg["outputs"]) == 2
        assert pkg["outputs"]["output_netcdf"]["format"] == edam_netcdf
        assert pkg["outputs"]["output_netcdf"]["type"] == "File"
        assert pkg["outputs"]["output_netcdf"]["outputBinding"]["glob"] == "output_netcdf.nc"
        assert pkg["outputs"]["output_log"]["format"] == edam_plain
        assert pkg["outputs"]["output_log"]["type"] == "File"
        assert pkg["outputs"]["output_log"]["outputBinding"]["glob"] == "output_log.*"

        # process description I/O validation
        assert len(desc["process"]["inputs"]) == 2
        assert desc["process"]["inputs"][0]["id"] == "tasmax"
        assert desc["process"]["inputs"][0]["title"] == "Resource"  # FIXME: returns 'tasmax' should use <Title>='Resource' field value
        assert desc["process"]["inputs"][0]["abstract"] == "NetCDF Files or archive (tar/zip) containing netCDF files."
        assert desc["process"]["inputs"][0]["keywords"] == []
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "1000"
        assert desc["process"]["inputs"][0]["formats"][0]["default"] is True  # FIXME: returns false, should be true because has <Default> section
        assert desc["process"]["inputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["inputs"][0]["formats"][0]["encoding"] == "base64"
        assert desc["process"]["inputs"][1]["id"] == "freq"
        assert desc["process"]["inputs"][1]["title"] == "Frequency"
        assert desc["process"]["inputs"][1]["abstract"] == "Resampling frequency"
        assert desc["process"]["inputs"][1]["keywords"] == []
        assert desc["process"]["inputs"][1]["minOccurs"] == "0"
        assert desc["process"]["inputs"][1]["maxOccurs"] == "1"
        # FIXME: we should probably not return 'formats' section for data literal
        assert desc["process"]["inputs"][1]["formats"][0]["default"] is True  # FIXME: returns false, should be true because has <Default> section
        assert desc["process"]["inputs"][1]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert "encoding" not in desc["process"]["inputs"][1]["formats"][0]
        assert len(desc["process"]["outputs"]) == 2
        assert desc["process"]["outputs"][0]["id"] == "output_netcdf"
        assert desc["process"]["outputs"][0]["title"] == "output_netcdf"
        assert desc["process"]["outputs"][0]["abstract"] == "The indicator values computed on the original input grid."
        assert desc["process"]["outputs"][0]["keywords"] == []
        assert desc["process"]["outputs"][0]["minOccurs"] == "1"
        assert desc["process"]["outputs"][0]["maxOccurs"] == "1"
        assert desc["process"]["outputs"][0]["formats"][0]["default"] is True  # FIXME: returns false, should be true because has <Default> section
        assert desc["process"]["outputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["outputs"][0]["formats"][0]["encoding"] == "base64"
        assert desc["process"]["outputs"][1]["id"] == "output_log"
        assert desc["process"]["outputs"][1]["title"] == "output_log"
        assert desc["process"]["outputs"][1]["abstract"] == "Collected logs during process run."
        assert desc["process"]["outputs"][1]["keywords"] == []
        assert desc["process"]["outputs"][1]["minOccurs"] == "1"
        assert desc["process"]["outputs"][1]["maxOccurs"] == "1"
        assert desc["process"]["outputs"][1]["formats"][0]["default"] is True  # FIXME: returns false, should be true because has <Default> section
        assert desc["process"]["outputs"][1]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
