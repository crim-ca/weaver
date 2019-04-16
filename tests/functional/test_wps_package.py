from weaver.formats import (
    CONTENT_TYPE_APP_JSON,
    CONTENT_TYPE_APP_NETCDF,
    CONTENT_TYPE_TEXT_PLAIN,
    CONTENT_TYPE_APP_TAR,
    CONTENT_TYPE_APP_ZIP,
    EDAM_NAMESPACE,
    EDAM_MAPPING,
    get_cwl_file_format,
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
import pytest
import unittest
import six

EDAM_PLAIN = EDAM_NAMESPACE + ":" + EDAM_MAPPING[CONTENT_TYPE_TEXT_PLAIN]
EDAM_NETCDF = EDAM_NAMESPACE + ":" + EDAM_MAPPING[CONTENT_TYPE_APP_NETCDF]


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
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": {
                "url": {
                    "type": "string"
                }
            },
            "outputs": {
                "values": {
                    "type": {
                        "type": "array",
                        "items": "float",
                    }
                }
            }
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                }
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, pkg = self.deploy_process(body)
        assert desc["process"]["id"] == self._testMethodName
        assert desc["process"]["title"] == "some title"
        assert desc["process"]["abstract"] == "this is a test"
        assert isinstance(desc["process"]["inputs"], list)
        assert len(desc["process"]["inputs"]) == 1
        assert desc["process"]["inputs"][0]["id"] == "url"
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "1"
        assert "format" not in desc["process"]["inputs"][0]
        assert isinstance(desc["process"]["outputs"], list)
        assert len(desc["process"]["outputs"]) == 1
        assert desc["process"]["outputs"][0]["id"] == "values"
        assert "minOccurs" not in desc["process"]["outputs"][0]
        assert "maxOccurs" not in desc["process"]["outputs"][0]
        assert "format" not in desc["process"]["outputs"][0]
        expected_fields = {"id", "title", "abstract", "inputs", "outputs", "executeEndpoint"}
        assert len(set(desc["process"].keys()) - expected_fields) == 0

    # FIXME: implement
    @pytest.mark.xfail(reason="not implemented")
    def test_literal_io_from_package_and_offering(self):
        raise NotImplementedError

    def test_complex_io_with_multiple_formats(self):
        # FIXME: multiple output (array) not tested here
        """
        Test validates that different format types are set on different I/O variations simultaneously:
            - input with 1 format, single value, no default
            - input with 1 format, array values, no default
            - input with 1 format, single value, 1 default
            - input with 1 format, array values, 1 default
            - input with many formats, single value, no default
            - input with many formats, array values, no default
            - input with many formats, single value, 1 default
            - input with many formats, array values, 1 default

            - output with 1 format, single value, no default
            - output with 1 format, single value, 1 default
            - output with many formats, single value, no default
            - output with many formats, single value, 1 default

        On addition, the test evaluates that:
            - CWL I/O specified as list preserves the specified ordering
            - partial WPS definition of I/O format to indicate 'default' are resolved with additional CWL I/O formats

        NOTE:
            field 'default' in CWL refers to default "value", in WPS refers to default "format" for complex types
        """
        ns1, type1 = get_cwl_file_format(CONTENT_TYPE_APP_JSON)
        ns2, type2 = get_cwl_file_format(CONTENT_TYPE_TEXT_PLAIN)
        ns3, type3 = get_cwl_file_format(CONTENT_TYPE_APP_NETCDF)
        namespaces = dict(ns1.items() + ns2.items() + ns3.items())
        default_file = "https://server.com/file"
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": [
                {
                    "id": "single_value_single_format",
                    "type": "File",
                    "format": type1,
                },
                {
                    "id": "multi_value_single_format",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    "format": type2,
                },
                {
                    "id": "single_value_single_format_default",
                    "type": "File",
                    "format": type3,
                    "default": default_file,
                },
                {
                    "id": "multi_value_single_format_default",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    "format": type2,
                    "default": default_file,
                },
                {
                    "id": "single_value_multi_format",
                    "type": "File",
                    "format": [type1, type2, type3],
                },
                {
                    "id": "multi_value_multi_format",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    "format": [type1, type2, type3],
                },
                {
                    "id": "single_value_multi_format_default",
                    "type": "File",
                    "format": [type1, type2, type3],
                    "default": default_file,
                },
                {
                    "id": "multi_value_multi_format_default",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    "format": [type1, type2, type3],
                    "default": default_file,
                },
            ],
            "outputs": [
                # FIXME: implement other variations of outputs (see docstring)
                {
                    "id": "values",
                    "type": {
                        "type": "array",
                        "items": "float",
                    }
                }
            ],
            "$namespaces": namespaces
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self.__name__,
                    "title": "some title",
                    "abstract": "this is a test",
                    # only partial inputs provided to fill additional details that cannot be specified with CWL alone
                    # only providing the 'default' format, others auto-resolved/added by CWL definitions
                    "inputs": [
                        {
                            "id": "multi_value_multi_format",
                            "formats": [
                                {
                                    "mimeType": CONTENT_TYPE_APP_JSON,
                                    "default": True,
                                }
                            ]
                        },
                        {
                            "id": "multi_value_multi_format_default",
                            "formats": [
                                {
                                    "mimeType": CONTENT_TYPE_APP_NETCDF,
                                    "default": True,
                                }
                            ]
                        }
                    ]
                },
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, pkg = self.deploy_process(body)

        # process description input validation
        assert desc["process"]["inputs"][0]["id"] == "single_value_single_format"
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "1"
        assert len(desc["process"]["inputs"][0]["formats"]) == 1
        assert desc["process"]["inputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert desc["process"]["inputs"][0]["formats"][0]["default"] is True  # only format available, auto default
        assert desc["process"]["inputs"][1]["id"] == "multi_value_single_format"
        assert desc["process"]["inputs"][1]["minOccurs"] == "1"
        assert desc["process"]["inputs"][1]["maxOccurs"] == "unbounded"
        assert len(desc["process"]["inputs"][1]["formats"]) == 1
        assert desc["process"]["inputs"][1]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][1]["formats"][0]["default"] is True  # only format available, auto default
        assert desc["process"]["inputs"][2]["id"] == "single_value_single_format_default"
        assert desc["process"]["inputs"][2]["minOccurs"] == "0"
        assert desc["process"]["inputs"][2]["maxOccurs"] == "1"
        assert len(desc["process"]["inputs"][2]["formats"]) == 1
        assert desc["process"]["inputs"][2]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["inputs"][2]["formats"][0]["default"] is True  # only format available, auto default
        assert desc["process"]["inputs"][3]["id"] == "multi_value_single_format_default"
        assert desc["process"]["inputs"][3]["minOccurs"] == "0"
        assert desc["process"]["inputs"][3]["maxOccurs"] == "unbounded"
        assert len(desc["process"]["inputs"][3]["formats"]) == 1
        assert desc["process"]["inputs"][3]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][3]["formats"][0]["default"] is True  # only format available, auto default
        assert desc["process"]["inputs"][4]["id"] == "single_value_multi_format"
        assert desc["process"]["inputs"][4]["minOccurs"] == "1"
        assert desc["process"]["inputs"][4]["maxOccurs"] == "1"
        assert len(desc["process"]["inputs"][4]["formats"]) == 3
        assert desc["process"]["inputs"][4]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert desc["process"]["inputs"][4]["formats"][0]["default"] is True  # no explicit default, uses first
        assert desc["process"]["inputs"][4]["formats"][1]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][4]["formats"][1]["default"] is False
        assert desc["process"]["inputs"][4]["formats"][2]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["inputs"][4]["formats"][2]["default"] is False
        assert desc["process"]["inputs"][5]["id"] == "multi_value_multi_format"
        assert desc["process"]["inputs"][5]["minOccurs"] == "1"
        assert desc["process"]["inputs"][5]["maxOccurs"] == "unbounded"
        assert len(desc["process"]["inputs"][5]["formats"]) == 3
        assert desc["process"]["inputs"][5]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert desc["process"]["inputs"][5]["formats"][0]["default"] is True  # specified in process description
        assert desc["process"]["inputs"][5]["formats"][1]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][5]["formats"][1]["default"] is False
        assert desc["process"]["inputs"][5]["formats"][2]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["inputs"][5]["formats"][2]["default"] is False
        assert desc["process"]["inputs"][6]["id"] == "single_value_multi_format_default"
        assert desc["process"]["inputs"][6]["minOccurs"] == "0"
        assert desc["process"]["inputs"][6]["maxOccurs"] == "1"
        assert len(desc["process"]["inputs"][6]["formats"]) == 3
        assert desc["process"]["inputs"][6]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert desc["process"]["inputs"][6]["formats"][0]["default"] is True  # no explicit default, uses first
        assert desc["process"]["inputs"][6]["formats"][1]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][6]["formats"][1]["default"] is False
        assert desc["process"]["inputs"][6]["formats"][2]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["inputs"][6]["formats"][2]["default"] is False
        assert desc["process"]["inputs"][7]["id"] == "multi_value_multi_format_default"
        assert desc["process"]["inputs"][7]["minOccurs"] == "0"
        assert desc["process"]["inputs"][7]["maxOccurs"] == "unbounded"
        assert len(desc["process"]["inputs"][7]["formats"]) == 3
        assert desc["process"]["inputs"][7]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert desc["process"]["inputs"][7]["formats"][0]["default"] is False
        assert desc["process"]["inputs"][7]["formats"][1]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][7]["formats"][1]["default"] is False
        assert desc["process"]["inputs"][7]["formats"][2]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["inputs"][7]["formats"][2]["default"] is True  # specified in process description

        # process description output validation
        # FIXME: implement

        # package input validation
        assert pkg["inputs"]["single_value_single_format"]["format"] == type1
        assert pkg["inputs"]["single_value_single_format"]["type"] == "File"
        assert pkg["inputs"]["multi_value_single_format"]["format"] == type1
        assert pkg["inputs"]["multi_value_single_format"]["type"] == "array"

        # package output validation
        # FIXME: implement

    # FIXME: implement
    @pytest.mark.xfail(reason="not implemented")
    def test_complex_io_from_package(self):
        raise NotImplementedError

    # FIXME: implement
    @pytest.mark.xfail(reason="not implemented")
    def test_complex_io_from_package_and_offering(self):
        raise NotImplementedError

    def test_literal_and_complex_io_from_wps_xml_reference(self):
        body = {
            "processDescription": {"process": {"id": self.__name__}},
            "executionUnit": [{"href": "mock://{}".format(resources.WMS_LITERAL_COMPLEX_IO)}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication"
        }
        desc, pkg = self.deploy_process(body)

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
        assert pkg["inputs"]["tasmax"]["format"] == EDAM_NETCDF
        assert pkg["inputs"]["tasmax"]["type"]["type"] == "array"
        assert pkg["inputs"]["tasmax"]["type"]["items"] == "File"
        assert pkg["inputs"]["freq"]["default"] == "YS"
        assert pkg["inputs"]["freq"]["type"]["type"] == "enum"
        assert pkg["inputs"]["freq"]["type"]["symbols"] == ["YS", "MS", "QS-DEC", "AS-JUL"]
        assert "outputs" in pkg
        assert len(pkg["outputs"]) == 2
        assert pkg["outputs"]["output_netcdf"]["format"] == EDAM_NETCDF
        assert pkg["outputs"]["output_netcdf"]["type"] == "File"
        assert pkg["outputs"]["output_netcdf"]["outputBinding"]["glob"] == "output_netcdf.nc"
        assert pkg["outputs"]["output_log"]["format"] == EDAM_PLAIN
        assert pkg["outputs"]["output_log"]["type"] == "File"
        assert pkg["outputs"]["output_log"]["outputBinding"]["glob"] == "output_log.*"

        # process description I/O validation
        assert len(desc["process"]["inputs"]) == 2
        assert desc["process"]["inputs"][0]["id"] == "tasmax"
        assert desc["process"]["inputs"][0]["title"] == "Resource"
        assert desc["process"]["inputs"][0]["abstract"] == "NetCDF Files or archive (tar/zip) containing netCDF files."
        assert desc["process"]["inputs"][0]["keywords"] == []
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "1000"
        assert len(desc["process"]["inputs"][0]["formats"]) == 1
        assert desc["process"]["inputs"][0]["formats"][0]["default"] is True
        assert desc["process"]["inputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["inputs"][0]["formats"][0]["encoding"] == "base64"
        assert desc["process"]["inputs"][1]["id"] == "freq"
        assert desc["process"]["inputs"][1]["title"] == "Frequency"
        assert desc["process"]["inputs"][1]["abstract"] == "Resampling frequency"
        assert desc["process"]["inputs"][1]["keywords"] == []
        assert desc["process"]["inputs"][1]["minOccurs"] == "0"
        assert desc["process"]["inputs"][1]["maxOccurs"] == "1"
        assert "formats" not in desc["process"]["inputs"][1]
        assert len(desc["process"]["outputs"]) == 2
        assert desc["process"]["outputs"][0]["id"] == "output_netcdf"
        assert desc["process"]["outputs"][0]["title"] == "Function output in netCDF"
        assert desc["process"]["outputs"][0]["abstract"] == "The indicator values computed on the original input grid."
        assert desc["process"]["outputs"][0]["keywords"] == []
        assert "minOccurs" not in desc["process"]["outputs"][0]
        assert "maxOccurs" not in desc["process"]["outputs"][0]
        assert len(desc["process"]["outputs"][0]["formats"]) == 1
        assert desc["process"]["outputs"][0]["formats"][0]["default"] is True
        assert desc["process"]["outputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["outputs"][0]["formats"][0]["encoding"] == "base64"
        assert desc["process"]["outputs"][1]["id"] == "output_log"
        assert desc["process"]["outputs"][1]["title"] == "Logging information"
        assert desc["process"]["outputs"][1]["abstract"] == "Collected logs during process run."
        assert desc["process"]["outputs"][1]["keywords"] == []
        assert "minOccurs" not in desc["process"]["outputs"][1]
        assert "maxOccurs" not in desc["process"]["outputs"][1]
        assert len(desc["process"]["outputs"][1]["formats"]) == 1
        assert desc["process"]["outputs"][1]["formats"][0]["default"] is True
        assert desc["process"]["outputs"][1]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN

    def test_enum_array_and_multi_format_inputs_from_wps_xml_reference(self):
        body = {
            "processDescription": {"process": {"id": self.__name__}},
            "executionUnit": [{"href": "mock://{}".format(resources.WPS_ENUM_ARRAY_IO)}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication"
        }
        desc, pkg = self.deploy_process(body)

        # basic contents validation
        assert "cwlVersion" in pkg
        assert "process" in desc
        assert desc["process"]["id"] == self.__name__

        # package I/O validation
        assert "inputs" in pkg
        assert len(pkg["inputs"]) == 3
        assert pkg["inputs"]["region"]["default"] == "DEU"
        assert pkg["inputs"]["region"]["type"]["type"] == "array"
        assert pkg["inputs"]["region"]["type"]["items"]["type"] == "enum"
        assert isinstance(pkg["inputs"]["region"]["type"]["items"]["symbols"], list)
        assert len(pkg["inputs"]["region"]["type"]["items"]["symbols"]) == 220
        assert all(isinstance(s, six.string_types) for s in pkg["inputs"]["region"]["type"]["items"]["symbols"])
        assert pkg["inputs"]["mosaic"]["default"] == "null"
        assert pkg["inputs"]["mosaic"]["type"] == "boolean"
        assert pkg["inputs"]["resource"]["default"]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert pkg["inputs"]["resource"]["default"]["encoding"] is None
        assert pkg["inputs"]["resource"]["default"]["schema"] is None
        assert pkg["inputs"]["resource"]["format"] == EDAM_NETCDF
        assert pkg["inputs"]["resource"]["type"]["type"] == "array"
        assert pkg["inputs"]["resource"]["type"]["items"] == "File"
        # FIXME: implement (resource input had 3 possible formats)
        #   figure out how to generate the CWL with multi input formats... is it possible?

        # process description I/O validation
        assert len(desc["process"]["inputs"]) == 3
        assert desc["process"]["inputs"][0]["id"] == "region"
        assert desc["process"]["inputs"][0]["title"] == "Region"
        assert desc["process"]["inputs"][0]["abstract"] == "Country code, see ISO-3166-3"
        assert desc["process"]["inputs"][0]["keywords"] == []
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "220"
        assert "formats" not in desc["process"]["inputs"][0]
        assert desc["process"]["inputs"][1]["id"] == "mosaic"
        assert desc["process"]["inputs"][1]["title"] == "Union of multiple regions"
        assert desc["process"]["inputs"][1]["abstract"] == \
               "If True, selected regions will be merged into a single geometry."   # noqa
        assert desc["process"]["inputs"][1]["keywords"] == []
        assert desc["process"]["inputs"][1]["minOccurs"] == "0"
        assert desc["process"]["inputs"][1]["maxOccurs"] == "1"
        assert "formats" not in desc["process"]["inputs"][1]
        assert desc["process"]["inputs"][2]["id"] == "resource"
        assert desc["process"]["inputs"][2]["title"] == "Resource"
        assert desc["process"]["inputs"][2]["abstract"] == "NetCDF Files or archive (tar/zip) containing NetCDF files."
        assert desc["process"]["inputs"][2]["keywords"] == []
        assert desc["process"]["inputs"][2]["minOccurs"] == "1"
        assert desc["process"]["inputs"][2]["maxOccurs"] == "1000"
        assert len(desc["process"]["inputs"][2]["formats"]) == 3
        assert desc["process"]["inputs"][2]["formats"][0]["default"] is True
        assert desc["process"]["inputs"][2]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert "encoding" not in desc["process"]["inputs"][2]["formats"][0]  # none specified, so omitted in response
        assert desc["process"]["inputs"][2]["formats"][1]["default"] is False
        assert desc["process"]["inputs"][2]["formats"][1]["mimeType"] == CONTENT_TYPE_APP_TAR
        assert "encoding" not in desc["process"]["inputs"][2]["formats"][1]  # none specified, so omitted in response
        assert desc["process"]["inputs"][2]["formats"][2]["default"] is False
        assert desc["process"]["inputs"][2]["formats"][2]["mimeType"] == CONTENT_TYPE_APP_ZIP
        assert "encoding" not in desc["process"]["inputs"][2]["formats"][2]  # none specified, so omitted in response

    # FIXME: implement,
    #   need to find a existing WPS with some, or manually write XML
    #   multi-output (with same ID) would be an indirect 1-output with ref to multi (Metalink file)
    #   (https://github.com/crim-ca/weaver/issues/25)
    @pytest.mark.xfail(reason="not implemented")
    def test_multi_outputs_file_from_wps_xml_reference(self):
        raise NotImplementedError
