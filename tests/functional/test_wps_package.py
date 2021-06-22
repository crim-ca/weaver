"""
Functional tests of operations implemented by :mod:`weaver.processes.wps_package`.

Validates that CWL package definitions are parsed and executes the process as intended.
Local test web application is employed to run operations by mocking external requests.

.. seealso::
    - :mod:`tests.processes.wps_package`.
"""
import contextlib
import json
import logging
import os
from inspect import cleandoc

import colander
import pytest
from pyramid.httpexceptions import HTTPBadRequest

from tests import resources
from tests.functional.utils import WpsPackageConfigBase
from tests.utils import (
    MOCK_AWS_REGION,
    mocked_aws_credentials,
    mocked_aws_s3,
    mocked_aws_s3_bucket_test_file,
    mocked_execute_process,
    mocked_file_test,
    mocked_http_test_file,
    mocked_sub_requests
)
from weaver.execute import EXECUTE_MODE_ASYNC, EXECUTE_RESPONSE_DOCUMENT, EXECUTE_TRANSMISSION_MODE_REFERENCE
from weaver.formats import (
    CONTENT_TYPE_APP_JSON,
    CONTENT_TYPE_APP_NETCDF,
    CONTENT_TYPE_APP_TAR,
    CONTENT_TYPE_APP_ZIP,
    CONTENT_TYPE_TEXT_PLAIN,
    EDAM_MAPPING,
    EDAM_NAMESPACE,
    IANA_NAMESPACE,
    get_cwl_file_format
)
from weaver.processes.constants import CWL_REQUIREMENT_APP_BUILTIN, CWL_REQUIREMENT_INIT_WORKDIR
from weaver.utils import get_any_value

EDAM_PLAIN = EDAM_NAMESPACE + ":" + EDAM_MAPPING[CONTENT_TYPE_TEXT_PLAIN]
EDAM_NETCDF = EDAM_NAMESPACE + ":" + EDAM_MAPPING[CONTENT_TYPE_APP_NETCDF]
# note: x-tar cannot be mapped during CWL format resolution (not official schema),
#       it remains explicit tar definition in WPS context
IANA_TAR = IANA_NAMESPACE + ":" + CONTENT_TYPE_APP_TAR  # noqa # pylint: disable=unused-variable
IANA_ZIP = IANA_NAMESPACE + ":" + CONTENT_TYPE_APP_ZIP  # noqa # pylint: disable=unused-variable

KNOWN_PROCESS_DESCRIPTION_FIELDS = {
    "id", "title", "abstract", "keywords", "metadata", "inputs", "outputs", "executeEndpoint", "visibility"
}
# intersection of fields in InputType and specific sub-schema LiteralInputType
KNOWN_PROCESS_DESCRIPTION_INPUT_DATA_FIELDS = {
    "id", "title", "abstract", "keywords", "metadata", "links", "literalDataDomains", "additionalParameters",
    "minOccurs", "maxOccurs"
}
# corresponding schemas of input, but min/max occurs not expected
KNOWN_PROCESS_DESCRIPTION_OUTPUT_DATA_FIELDS = KNOWN_PROCESS_DESCRIPTION_INPUT_DATA_FIELDS - {"minOccurs", "maxOccurs"}

LOGGER = logging.getLogger(__name__)


@pytest.mark.functional
class WpsPackageAppTest(WpsPackageConfigBase):
    @classmethod
    def setUpClass(cls):
        cls.settings = {
            "weaver.wps": True,
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
            "weaver.wps_output_dir": "/tmp",  # nosec: B108 # don't care hardcoded for test
        }
        super(WpsPackageAppTest, cls).setUpClass()

    def test_cwl_label_as_process_title(self):
        title = "This process title comes from the CWL label"
        cwl = {
            "cwlVersion": "v1.0",
            "label": title,
            "class": "CommandLineTool",
            "inputs": {"url": {"type": "string"}},
            "outputs": {"values": {"type": "float"}}
        }
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, pkg = self.deploy_process(body)
        assert desc["process"]["title"] == title
        assert pkg["label"] == title

    def test_literal_io_from_package(self):
        """
        Test validates that literal I/O definitions *only* defined in the `CWL` package as `JSON` within the
        deployment body generates expected `WPS` process description I/O with corresponding formats and values.
        """
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
        desc, _ = self.deploy_process(body)

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
        assert len(set(desc["process"].keys()) - KNOWN_PROCESS_DESCRIPTION_FIELDS) == 0
        # make sure that deserialization of literal fields did not produce over-verbose metadata
        for p_input in desc["process"]["inputs"]:
            assert len(set(p_input) - KNOWN_PROCESS_DESCRIPTION_INPUT_DATA_FIELDS) == 0
        for p_output in desc["process"]["outputs"]:
            assert len(set(p_output) - KNOWN_PROCESS_DESCRIPTION_OUTPUT_DATA_FIELDS) == 0

    def test_literal_io_from_package_and_offering(self):
        """
        Test validates that literal I/O definitions simultaneously defined in *both* (but not necessarily for each
        one and exhaustively) `CWL` and `WPS` payloads are correctly resolved. More specifically, verifies that:

            - `WPS` I/O that don't match any `CWL` I/O by ID are removed completely.
            - `WPS` I/O that were omitted are added with minimal detail requirements using corresponding `CWL` I/O
            - `WPS` I/O complementary details are added to corresponding `CWL` I/O (no duplication of IDs)

        .. seealso::
            - :func:`weaver.processes.wps_package._merge_package_io`
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": [
                {
                    "id": "literal_input_only_cwl_minimal",
                    "type": "string"
                },
                {
                    "id": "literal_input_both_cwl_and_wps",
                    "type": "string"
                },
            ],
            "outputs": [
                {
                    "id": "literal_output_only_cwl_minimal",
                    "type": {
                        "type": "array",
                        "items": "float",
                    }
                },
                {
                    "id": "literal_output_both_cwl_and_wps",
                    "type": "float"
                }
            ]
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                    "inputs": [
                        {
                            "id": "literal_input_only_wps_removed",
                        },
                        {
                            "id": "literal_input_both_cwl_and_wps",
                            "title": "Extra detail for I/O both in CWL and WPS"
                        }
                    ],
                    "outputs": [
                        {
                            "id": "literal_output_only_wps_removed"
                        },
                        {
                            "id": "literal_output_both_cwl_and_wps",
                            "title": "Additional detail only within WPS output"
                        }
                    ]
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
        assert len(desc["process"]["inputs"]) == 2
        assert desc["process"]["inputs"][0]["id"] == "literal_input_only_cwl_minimal"
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "1"
        assert desc["process"]["inputs"][1]["id"] == "literal_input_both_cwl_and_wps"
        assert desc["process"]["inputs"][1]["minOccurs"] == "1"
        assert desc["process"]["inputs"][1]["maxOccurs"] == "1"
        assert desc["process"]["inputs"][1]["title"] == "Extra detail for I/O both in CWL and WPS", \
            "Additional details defined only in WPS matching CWL I/O by ID should be preserved"
        assert isinstance(desc["process"]["outputs"], list)
        assert len(desc["process"]["outputs"]) == 2
        assert desc["process"]["outputs"][0]["id"] == "literal_output_only_cwl_minimal"
        assert desc["process"]["outputs"][1]["id"] == "literal_output_both_cwl_and_wps"
        assert desc["process"]["outputs"][1]["title"] == "Additional detail only within WPS output", \
            "Additional details defined only in WPS matching CWL I/O by ID should be preserved"

        assert len(pkg["inputs"]) == 2
        assert pkg["inputs"][0]["id"] == "literal_input_only_cwl_minimal"
        assert pkg["inputs"][1]["id"] == "literal_input_both_cwl_and_wps"
        # FIXME:
        #   https://github.com/crim-ca/weaver/issues/31
        #   https://github.com/crim-ca/weaver/issues/50
        # assert pkg["inputs"][1]["label"] == "Extra detail for I/O both in CWL and WPS", \
        #     "WPS I/O title should be converted to CWL label of corresponding I/O from additional details"
        assert len(pkg["outputs"]) == 2
        assert pkg["outputs"][0]["id"] == "literal_output_only_cwl_minimal"
        assert pkg["outputs"][1]["id"] == "literal_output_both_cwl_and_wps"
        # FIXME:
        #   https://github.com/crim-ca/weaver/issues/31
        #   https://github.com/crim-ca/weaver/issues/50
        # assert pkg["outputs"][1]["label"] == "Additional detail only within WPS output", \
        #     "WPS I/O title should be converted to CWL label of corresponding I/O from additional details"

    def test_complex_io_format_references(self):
        """
        Test validates that known `WPS` I/O formats (i.e.: `MIME-type`) considered as valid, but not corresponding
        to any *real* `IANA/EDAM` reference for `CWL` are preserved on the `WPS` side and dropped on `CWL` side to
        avoid validation error.

        We also validate a `MIME-type` that should be found for both `CWL` and `WPS` formats to make sure that `CWL`
        formats are only dropped when necessary.
        """
        ns_json, type_json = get_cwl_file_format(CONTENT_TYPE_APP_JSON, must_exist=True)
        assert "iana" in ns_json  # just to make sure
        ct_not_exists = "x-ogc-dods"    # OpenDAP, still doesn't exist at moment of test creation
        ns_not_exists, _ = get_cwl_file_format(ct_not_exists, must_exist=False)
        assert "iana" in ns_not_exists
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "inputs": [
                        {
                            "id": "wps_only_format_exists",
                            "formats": [
                                {
                                    "mimeType": CONTENT_TYPE_APP_JSON,
                                    "default": True,
                                }
                            ]
                        },
                        {
                            "id": "wps_only_format_not_exists",
                            "formats": [
                                {
                                    "mimeType": ct_not_exists,
                                    "default": True,
                                }
                            ]
                        },
                        {
                            "id": "wps_only_format_both",
                            "formats": [
                                {"mimeType": CONTENT_TYPE_APP_JSON},
                                {"mimeType": ct_not_exists, "default": True},
                            ]
                        }
                    ],
                    # NOTE:
                    #   Don't care about outputs here since we cannot have an array of formats
                    #   as CWL output, so there isn't much to compare against from the WPS list.
                },
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": {
                "cwlVersion": "v1.0",
                "class": "CommandLineTool",
                "inputs": {
                    # minimal info only to match IDs, check that formats are added only when CWL can resolve references
                    # FIXME: no format is back-propagated from WPS format to CWL at the moment
                    #  (https://github.com/crim-ca/weaver/issues/50)
                    "wps_only_format_exists": "File",
                    "wps_only_format_not_exists": "File",
                    "wps_only_format_both": "File",
                    "cwl_only_format_exists": {"type": "File", "format": type_json},
                    # non-existing schema references should not be provided directly in CWL
                    # since these would enforce raising the validation error directly...
                    # "cwl_only_format_not_exists": {"type": "File", "format": ct_not_exists}
                },
                "outputs": {"dont_care": "File"},
                "$namespaces": dict(list(ns_json.items()))
            }}],
        }
        desc, pkg = self.deploy_process(body)

        assert desc["process"]["inputs"][0]["id"] == "wps_only_format_exists"
        assert len(desc["process"]["inputs"][0]["formats"]) == 1
        assert desc["process"]["inputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert pkg["inputs"][0]["id"] == "wps_only_format_exists"
        assert pkg["inputs"][0]["type"] == "File"
        # FIXME: back-propagate WPS format to CWL without format specified
        #  (https://github.com/crim-ca/weaver/issues/50)
        # assert pkg["inputs"][0]["format"] == type_json

        assert desc["process"]["inputs"][1]["id"] == "wps_only_format_not_exists"
        assert len(desc["process"]["inputs"][1]["formats"]) == 1
        assert desc["process"]["inputs"][1]["formats"][0]["mimeType"] == ct_not_exists
        assert pkg["inputs"][1]["id"] == "wps_only_format_not_exists"
        assert pkg["inputs"][1]["type"] == "File"
        assert "format" not in pkg["inputs"][1], "Non-existing CWL format reference should have been dropped."

        assert desc["process"]["inputs"][2]["id"] == "wps_only_format_both"
        assert len(desc["process"]["inputs"][2]["formats"]) == 2
        assert desc["process"]["inputs"][2]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert desc["process"]["inputs"][2]["formats"][1]["mimeType"] == ct_not_exists
        assert pkg["inputs"][2]["id"] == "wps_only_format_both"
        assert pkg["inputs"][2]["type"] == "File"
        # FIXME: for now we don't even back-propagate, but if we did, must be none because one is unknown reference
        #   (https://github.com/crim-ca/weaver/issues/50)
        assert "format" not in pkg["inputs"][2], "Any non-existing CWL format reference should drop all entries."

        assert desc["process"]["inputs"][3]["id"] == "cwl_only_format_exists"
        assert len(desc["process"]["inputs"][3]["formats"]) == 1
        assert desc["process"]["inputs"][3]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert pkg["inputs"][3]["id"] == "cwl_only_format_exists"
        assert pkg["inputs"][3]["type"] == "File"
        assert pkg["inputs"][3]["format"] == type_json

    def test_complex_io_with_multiple_formats_and_defaults(self):
        """
        Test validates that different format types are set on different input variations simultaneously:
            - input with 1 format, single value, no default value
            - input with 1 format, array values, no default value
            - input with 1 format, single value, 1 default value
            - input with 1 format, array values, 1 default value
            - input with many formats, single value, no default value
            - input with many formats, array values, no default value
            - input with many formats, single value, 1 default value
            - input with many formats, array values, 1 default value

        In the case of outputs, CWL 'format' refers to 'applied' format instead of 'supported' format.
        Therefore, 'format' field is omitted if >1 supported format is specified in WPS to avoid incompatibilities.
            - output with 1 format, single value (has format in CWL and WPS)
            - output with 1 format, array values (has format in CWL and WPS)
            - output with many formats, single value (no format in CWL, WPS formats must be provided)
            - output with many formats, array values (no format in CWL, WPS formats must be provided)

        In addition, the test evaluates that:
            - CWL I/O specified as list preserves the specified ordering
            - CWL 'default' "value" doesn't interfere with WPS 'default' "format" and vice-versa
            - partial WPS definition of I/O format to indicate 'default' are resolved with additional CWL I/O formats
            - min/max occurrences are solved accordingly to single/array values and 'default' if not overridden by WPS

        NOTE:
            field 'default' in CWL refers to default "value", in WPS refers to default "format" for complex inputs
        """
        ns_json, type_json = get_cwl_file_format(CONTENT_TYPE_APP_JSON)
        ns_text, type_text = get_cwl_file_format(CONTENT_TYPE_TEXT_PLAIN)
        ns_ncdf, type_ncdf = get_cwl_file_format(CONTENT_TYPE_APP_NETCDF)
        namespaces = dict(list(ns_json.items()) + list(ns_text.items()) + list(ns_ncdf.items()))
        default_file = "https://server.com/file"
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": [
                {
                    "id": "single_value_single_format",
                    "type": "File",
                    "format": type_json,
                },
                {
                    "id": "multi_value_single_format",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    "format": type_text,
                },
                {
                    "id": "single_value_single_format_default",
                    "type": "File",
                    "format": type_ncdf,
                    "default": default_file,
                },
                {
                    "id": "multi_value_single_format_default",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    "format": type_text,
                    "default": default_file,
                },
                {
                    "id": "single_value_multi_format",
                    "type": "File",
                    "format": [type_json, type_text, type_ncdf],
                },
                {
                    "id": "multi_value_multi_format",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    "format": [type_ncdf, type_text, type_json],
                },
                {
                    "id": "single_value_multi_format_default",
                    "type": "File",
                    "format": [type_json, type_text, type_ncdf],
                    "default": default_file,
                },
                {
                    "id": "multi_value_multi_format_default",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    "format": [type_json, type_text, type_ncdf],
                    "default": default_file,
                },
            ],
            "outputs": [
                {
                    "id": "single_value_single_format",
                    "type": "File",
                    "format": type_json,
                },
                {
                    "id": "single_value_multi_format",
                    "type": "File",
                    # NOTE:
                    #   not valid to have array of format for output as per:
                    #   https://github.com/common-workflow-language/common-workflow-language/issues/482
                    #   WPS payload must specify them
                    # "format": [type_json, type2, type3]
                },
                # FIXME: multiple output (array) not implemented (https://github.com/crim-ca/weaver/issues/25)
                # {
                #    "id": "multi_value_single_format",
                #    "type": {
                #        "type": "array",
                #        "items": "File",
                #    },
                #    "format": type3,
                # },
                # {
                #     "id": "multi_value_multi_format",
                #     "type": {
                #         "type": "array",
                #         "items": "File",
                #     },
                #     # NOTE:
                #     #   not valid to have array of format for output as per:
                #     #   https://github.com/common-workflow-language/common-workflow-language/issues/482
                #     #   WPS payload must specify them
                #     "format": [type3, type2, type_json],
                # },
            ],
            "$namespaces": namespaces
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                    # only partial inputs provided to fill additional details that cannot be specified with CWL alone
                    # only providing the 'default' format, others auto-resolved/added by CWL definitions
                    "inputs": [
                        {
                            "id": "multi_value_multi_format",
                            "formats": [
                                {
                                    "mimeType": CONTENT_TYPE_TEXT_PLAIN,
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
                    ],
                    # explicitly specify supported formats when many are allowed because CWL cannot support it
                    "outputs": [
                        {
                            "id": "single_value_multi_format",
                            "formats": [
                                {"mimeType": CONTENT_TYPE_APP_JSON},
                                {"mimeType": CONTENT_TYPE_TEXT_PLAIN},
                                {"mimeType": CONTENT_TYPE_APP_NETCDF},
                            ]
                        },
                        # FIXME: multiple output (array) not implemented (https://github.com/crim-ca/weaver/issues/25)
                        # {
                        #     "id": "multi_value_multi_format",
                        #     "formats": [
                        #         {"mimeType": CONTENT_TYPE_APP_NETCDF},
                        #         {"mimeType": CONTENT_TYPE_TEXT_PLAIN},
                        #         {"mimeType": CONTENT_TYPE_APP_JSON},
                        #     ]
                        # }
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
        assert desc["process"]["inputs"][5]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["inputs"][5]["formats"][0]["default"] is False
        assert desc["process"]["inputs"][5]["formats"][1]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][5]["formats"][1]["default"] is True  # specified in process description
        assert desc["process"]["inputs"][5]["formats"][2]["mimeType"] == CONTENT_TYPE_APP_JSON
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
        assert isinstance(desc["process"]["outputs"], list)
        assert len(desc["process"]["outputs"]) == 2  # FIXME: adjust output count when issue #25 is implemented
        for output in desc["process"]["outputs"]:
            for field in ["minOccurs", "maxOccurs", "default"]:
                assert field not in output
            for format_spec in output["formats"]:
                # FIXME: not breaking for now, but should be fixed eventually (doesn't make sense to have defaults)
                #   https://github.com/crim-ca/weaver/issues/17
                #   https://github.com/crim-ca/weaver/issues/50
                if "default" in format_spec:
                    LOGGER.warning("Output [%s] has 'default' key but shouldn't (non-breaking).", output["id"])
                # assert "default" not in format_spec
        assert desc["process"]["outputs"][0]["id"] == "single_value_single_format"
        assert len(desc["process"]["outputs"][0]["formats"]) == 1
        assert desc["process"]["outputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert desc["process"]["outputs"][0]["formats"][0]["default"] is True
        assert desc["process"]["outputs"][1]["id"] == "single_value_multi_format"
        assert len(desc["process"]["outputs"][1]["formats"]) == 3
        assert desc["process"]["outputs"][1]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_JSON
        assert desc["process"]["outputs"][1]["formats"][1]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["outputs"][1]["formats"][2]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["outputs"][1]["formats"][0]["default"] is True   # mandatory
        assert desc["process"]["outputs"][1]["formats"][1].get("default", False) is False  # omission is allowed
        assert desc["process"]["outputs"][1]["formats"][2].get("default", False) is False  # omission is allowed
        # FIXME: enable when issue #25 is implemented
        # assert desc["process"]["outputs"][2]["id"] == "multi_value_single_format"
        # assert len(desc["process"]["outputs"][2]["formats"]) == 1
        # assert desc["process"]["outputs"][2]["formats"][0] == CONTENT_TYPE_APP_NETCDF
        # assert desc["process"]["outputs"][3]["id"] == "multi_value_multi_format"
        # assert len(desc["process"]["outputs"][3]["formats"]) == 3
        # assert desc["process"]["outputs"][3]["formats"][0] == CONTENT_TYPE_APP_NETCDF
        # assert desc["process"]["outputs"][3]["formats"][1] == CONTENT_TYPE_TEXT_PLAIN
        # assert desc["process"]["outputs"][3]["formats"][2] == CONTENT_TYPE_APP_JSON

        # package input validation
        assert pkg["inputs"][0]["id"] == "single_value_single_format"
        assert pkg["inputs"][0]["type"] == "File"
        assert pkg["inputs"][0]["format"] == type_json
        assert "default" not in pkg["inputs"][0]
        assert pkg["inputs"][1]["id"] == "multi_value_single_format"
        assert pkg["inputs"][1]["type"]["type"] == "array"
        assert pkg["inputs"][1]["type"]["items"] == "File"
        assert pkg["inputs"][1]["format"] == type_text
        assert "default" not in pkg["inputs"][1]
        assert pkg["inputs"][2]["id"] == "single_value_single_format_default"
        assert pkg["inputs"][2]["type"] == "File"
        assert pkg["inputs"][2]["format"] == type_ncdf
        assert pkg["inputs"][2]["default"] == default_file
        assert pkg["inputs"][3]["id"] == "multi_value_single_format_default"
        assert pkg["inputs"][3]["type"]["type"] == "array"
        assert pkg["inputs"][3]["type"]["items"] == "File"
        assert pkg["inputs"][3]["format"] == type_text
        assert pkg["inputs"][3]["default"] == default_file
        assert pkg["inputs"][4]["id"] == "single_value_multi_format"
        assert pkg["inputs"][4]["type"] == "File"
        assert pkg["inputs"][4]["format"] == [type_json, type_text, type_ncdf]
        assert "default" not in pkg["inputs"][4]
        assert pkg["inputs"][5]["id"] == "multi_value_multi_format"
        assert pkg["inputs"][5]["type"]["type"] == "array"
        assert pkg["inputs"][5]["type"]["items"] == "File"
        assert pkg["inputs"][5]["format"] == [type_ncdf, type_text, type_json]
        assert "default" not in pkg["inputs"][5]
        assert pkg["inputs"][6]["id"] == "single_value_multi_format_default"
        assert pkg["inputs"][6]["type"] == "File"
        assert pkg["inputs"][6]["format"] == [type_json, type_text, type_ncdf]
        assert pkg["inputs"][6]["default"] == default_file
        assert pkg["inputs"][7]["id"] == "multi_value_multi_format_default"
        assert pkg["inputs"][7]["type"]["type"] == "array"
        assert pkg["inputs"][7]["type"]["items"] == "File"
        assert pkg["inputs"][7]["format"] == [type_json, type_text, type_ncdf]
        assert pkg["inputs"][7]["default"] == default_file

        # package output validation
        for output in desc["process"]["outputs"]:
            assert "default" not in output
        assert pkg["outputs"][0]["id"] == "single_value_single_format"
        assert pkg["outputs"][0]["type"] == "File"
        assert pkg["outputs"][0]["format"] == type_json
        assert pkg["outputs"][1]["id"] == "single_value_multi_format"
        assert pkg["outputs"][1]["type"] == "File"
        assert "format" not in pkg["outputs"][1], "CWL format array not allowed for outputs."
        # FIXME: enable when issue #25 is implemented
        # assert pkg["outputs"][2]["id"] == "multi_value_single_format"
        # assert pkg["outputs"][2]["type"] == "array"
        # assert pkg["outputs"][2]["items"] == "File"
        # assert pkg["outputs"][2]["format"] == type_ncdf
        # assert pkg["outputs"][3]["id"] == "multi_value_multi_format"
        # assert pkg["outputs"][3]["type"] == "array"
        # assert pkg["outputs"][3]["items"] == "File"
        # assert "format" not in pkg["outputs"][3], "CWL format array not allowed for outputs."

    def test_resolution_io_min_max_occurs(self):
        """
        Test validates that various merging/resolution strategies of I/O definitions are properly applied for
        corresponding ``minOccurs`` and ``maxOccurs`` fields across `CWL` and `WPS` payloads. Also, fields that
        can help infer ``minOccurs`` and ``maxOccurs`` values such as ``default`` and ``type`` are tested.

        Following cases are evaluated:

            1. ``minOccurs=0`` is automatically added or corrected to `WPS` if ``default`` value is provided in `CWL`
            2. ``minOccurs=0`` is automatically added or corrected to `WPS` if `CWL` ``type`` specifies it with various
               formats (shortcut or explicit definition)
            3. ``minOccurs=1`` is automatically added or corrected to `WPS` if both ``default`` and ``minOccurs`` are
               not defined within the `CWL`
            4. ``maxOccurs=1`` is automatically added or corrected in `WPS` if `CWL` ``type`` corresponds to a single
               value (not an array)
            5. ``maxOccurs="unbounded"`` is automatically added in `WPS` if `CWL` ``type`` corresponds to an array
               and ``maxOccurs`` was not specified in `WPS`
            6. ``maxOccurs=<value>`` is preserved if specified in `WPS` and `CWL` ``type`` corresponds to an array.
            7. ``maxOccurs>1`` or ``maxOccurs="unbounded"`` defined in `WPS` converts the `CWL` type to a corresponding
               array definition as required (ex: ``string`` becomes ``string[]``)
            8. ``default=null`` is automatically added to `CWL` if ``minOccurs=0`` is provided in `WPS` and
               ``default`` is not explicitly defined in `CWL` nor `WPS`.
            9. ``default=<value>`` is automatically added to `CWL` if ``default=<value>`` is provided in `WPS` and
               ``default`` is not explicitly defined in `CWL`.
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": [
                # although types are parsed in multiple ways to compare default/null/array/minOccurs/maxOccurs
                # values, the original definitions here are preserved when there are no complementary WPS details
                {"id": "required_literal", "type": "string"},
                {"id": "required_literal_default", "type": "string", "default": "test"},
                {"id": "optional_literal_shortcut", "type": "string?"},
                {"id": "optional_literal_explicit", "type": ["null", "string"]},
                {"id": "required_array_shortcut", "type": "string[]"},
                {"id": "required_array_explicit", "type": {"type": "array", "items": "string"}},
                {"id": "optional_array_shortcut", "type": "string[]?"},
                {"id": "optional_array_explicit", "type": ["null", {"type": "array", "items": "string"}]},
                # types with complementary WPS details might change slightly depending on combinations encountered
                {"id": "required_literal_min_fixed_by_wps", "type": "string?"},         # string? => string    (min=1)
                {"id": "optional_literal_min_fixed_by_wps", "type": "string"},          # string  => string?   (min=0)
                {"id": "required_array_min_fixed_by_wps", "type": "string"},            # string  => string[]  (min>1)
                {"id": "required_array_min_optional_fixed_by_wps", "type": "string?"},  # string? => string[]  (min>1)
                {"id": "required_array_max_fixed_by_wps", "type": "string"},            # string  => string[]  (max>1)
                {"id": "optional_array_max_fixed_by_wps", "type": "string?"},           # string? => string[]? (max>1)
                {"id": "optional_array_min_max_fixed_by_wps", "type": "string"},        # string  => string[]? (0..>1)
            ],
            "outputs": {
                "values": {"type": "float"}
            }
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                    "inputs": [
                        {"id": "required_literal_min_fixed_by_wps", "minOccurs": "1"},
                        {"id": "optional_literal_min_fixed_by_wps", "minOccurs": "0"},
                        {"id": "required_array_min_fixed_by_wps", "minOccurs": "2"},
                        {"id": "required_array_min_optional_fixed_by_wps", "minOccurs": "2"},
                        {"id": "required_array_max_fixed_by_wps", "maxOccurs": "10"},
                        {"id": "optional_array_max_fixed_by_wps", "minOccurs": "0", "maxOccurs": "10"},
                        {"id": "optional_array_min_max_fixed_by_wps", "minOccurs": "0", "maxOccurs": "10"},
                    ]
                }
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, pkg = self.deploy_process(body)

        assert desc["process"]["inputs"][0]["id"] == "required_literal"
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "1"
        assert desc["process"]["inputs"][1]["id"] == "required_literal_default"
        assert desc["process"]["inputs"][1]["minOccurs"] == "0"
        assert desc["process"]["inputs"][1]["maxOccurs"] == "1"
        assert desc["process"]["inputs"][2]["id"] == "optional_literal_shortcut"
        assert desc["process"]["inputs"][2]["minOccurs"] == "0"
        assert desc["process"]["inputs"][2]["maxOccurs"] == "1"
        assert desc["process"]["inputs"][3]["id"] == "optional_literal_explicit"
        assert desc["process"]["inputs"][3]["minOccurs"] == "0"
        assert desc["process"]["inputs"][3]["maxOccurs"] == "1"
        assert desc["process"]["inputs"][4]["id"] == "required_array_shortcut"
        assert desc["process"]["inputs"][4]["minOccurs"] == "1"
        assert desc["process"]["inputs"][4]["maxOccurs"] == "unbounded"
        assert desc["process"]["inputs"][5]["id"] == "required_array_explicit"
        assert desc["process"]["inputs"][5]["minOccurs"] == "1"
        assert desc["process"]["inputs"][5]["maxOccurs"] == "unbounded"
        assert desc["process"]["inputs"][6]["id"] == "optional_array_shortcut"
        assert desc["process"]["inputs"][6]["minOccurs"] == "0"
        assert desc["process"]["inputs"][6]["maxOccurs"] == "unbounded"
        assert desc["process"]["inputs"][7]["id"] == "optional_array_explicit"
        assert desc["process"]["inputs"][7]["minOccurs"] == "0"
        assert desc["process"]["inputs"][7]["maxOccurs"] == "unbounded"
        assert desc["process"]["inputs"][8]["id"] == "required_literal_min_fixed_by_wps"
        assert desc["process"]["inputs"][8]["minOccurs"] == "1"
        assert desc["process"]["inputs"][8]["maxOccurs"] == "1"
        assert desc["process"]["inputs"][9]["id"] == "optional_literal_min_fixed_by_wps"
        assert desc["process"]["inputs"][9]["minOccurs"] == "0"
        assert desc["process"]["inputs"][9]["maxOccurs"] == "1"
        assert desc["process"]["inputs"][10]["id"] == "required_array_min_fixed_by_wps"
        # FIXME: https://github.com/crim-ca/weaver/issues/50
        #   `maxOccurs=1` not updated to `maxOccurs="unbounded"` as it is evaluated as a single value,
        #   but it should be considered an array since `minOccurs>1`
        #   (see: https://github.com/crim-ca/weaver/issues/17)
        assert desc["process"]["inputs"][10]["minOccurs"] == "2"
        # assert desc["process"]["inputs"][10]["maxOccurs"] == "unbounded"
        assert desc["process"]["inputs"][11]["id"] == "required_array_min_optional_fixed_by_wps"
        assert desc["process"]["inputs"][11]["minOccurs"] == "2"
        # assert desc["process"]["inputs"][11]["maxOccurs"] == "unbounded"
        assert desc["process"]["inputs"][12]["id"] == "required_array_max_fixed_by_wps"
        assert desc["process"]["inputs"][12]["minOccurs"] == "1"
        assert desc["process"]["inputs"][12]["maxOccurs"] == "10"
        assert desc["process"]["inputs"][13]["id"] == "optional_array_max_fixed_by_wps"
        assert desc["process"]["inputs"][13]["minOccurs"] == "0"
        assert desc["process"]["inputs"][13]["maxOccurs"] == "10"

        assert pkg["inputs"][0]["id"] == "required_literal"
        assert pkg["inputs"][0]["type"] == "string"
        assert pkg["inputs"][1]["id"] == "required_literal_default"
        assert pkg["inputs"][1]["type"] == "string"
        assert pkg["inputs"][1]["default"] == "test"
        assert pkg["inputs"][2]["id"] == "optional_literal_shortcut"
        assert pkg["inputs"][2]["type"] == "string?"
        assert pkg["inputs"][3]["id"] == "optional_literal_explicit"
        assert pkg["inputs"][3]["type"][0] == "null"
        assert pkg["inputs"][3]["type"][1] == "string"
        assert pkg["inputs"][4]["id"] == "required_array_shortcut"
        assert pkg["inputs"][4]["type"] == "string[]"
        assert pkg["inputs"][5]["id"] == "required_array_explicit"
        assert pkg["inputs"][5]["type"]["type"] == "array"
        assert pkg["inputs"][5]["type"]["items"] == "string"
        assert pkg["inputs"][6]["id"] == "optional_array_shortcut"
        assert pkg["inputs"][6]["type"] == "string[]?"
        assert pkg["inputs"][7]["id"] == "optional_array_explicit"
        assert pkg["inputs"][7]["type"][0] == "null"
        assert pkg["inputs"][7]["type"][1]["type"] == "array"
        assert pkg["inputs"][7]["type"][1]["items"] == "string"
        # FIXME:
        #   Although WPS minOccurs/maxOccurs' specifications are applied, they are not back-ported to CWL package
        #   definition in order to preserve the same logic. CWL types should be overridden by complementary details.
        #   - https://github.com/crim-ca/weaver/issues/17
        #   - https://github.com/crim-ca/weaver/issues/50
        assert pkg["inputs"][8]["id"] == "required_literal_min_fixed_by_wps"
        # assert pkg["inputs"][8]["type"] == "string"
        assert pkg["inputs"][9]["id"] == "optional_literal_min_fixed_by_wps"
        # assert pkg["inputs"][9]["type"] == "string?"
        assert pkg["inputs"][10]["id"] == "required_array_min_fixed_by_wps"
        # assert pkg["inputs"][10]["type"] == "string[]"
        assert pkg["inputs"][11]["id"] == "required_array_min_optional_fixed_by_wps"
        # assert pkg["inputs"][11]["type"] == "string[]?"
        assert pkg["inputs"][12]["id"] == "required_array_max_fixed_by_wps"
        # assert pkg["inputs"][12]["type"] == "string[]"
        assert pkg["inputs"][13]["id"] == "optional_array_max_fixed_by_wps"
        # assert pkg["inputs"][13]["type"] == "string[]?"

    # FIXME: https://github.com/crim-ca/weaver/issues/50
    #   'unbounded' value should not override literal 2/'2'
    @pytest.mark.xfail(reason="MinOccurs/MaxOccurs values in response should be preserved as defined in deploy body")
    def test_valid_io_min_max_occurs_as_str_or_int(self):
        """
        Test validates that I/O definitions with ``minOccurs`` and/or ``maxOccurs`` are permitted as both integer
        and string definitions in order to support (1, "1", "unbounded") variations.

        .. seealso::
            - :meth:`test_invalid_io_min_max_occurs_wrong_format`
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": [
                {"id": "io_min_int_max_int", "type": "string"},
                {"id": "io_min_int_max_str", "type": "string"},
                {"id": "io_min_str_max_int", "type": "string"},
                {"id": "io_min_str_max_str", "type": "string"},
                {"id": "io_min_int_max_unbounded", "type": "string"},
                {"id": "io_min_str_max_unbounded", "type": "string"},
            ],
            "outputs": {"values": {"type": "string"}}
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                },
                "inputs": [
                    {"id": "io_min_int_max_int", "minOccurs": 1, "maxOccurs": 2},
                    {"id": "io_min_int_max_str", "minOccurs": 1, "maxOccurs": "2"},
                    {"id": "io_min_str_max_int", "minOccurs": "1", "maxOccurs": 2},
                    {"id": "io_min_str_max_str", "minOccurs": "1", "maxOccurs": "2"},
                    {"id": "io_min_int_max_unbounded", "minOccurs": 1, "maxOccurs": "unbounded"},
                    {"id": "io_min_str_max_unbounded", "minOccurs": "1", "maxOccurs": "unbounded"},
                ]
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        try:
            desc, _ = self.deploy_process(body)
        except colander.Invalid:
            self.fail("MinOccurs/MaxOccurs values defined as valid int/str should not raise an invalid schema error")

        inputs = body["processDescription"]["inputs"]
        assert isinstance(desc["process"]["inputs"], list)
        assert len(desc["process"]["inputs"]) == len(inputs)
        for i, process_input in enumerate(inputs):
            assert desc["process"]["inputs"][i]["id"] == process_input["id"]
            for field in ["minOccurs", "maxOccurs"]:
                proc_in_res = desc["process"]["inputs"][i][field]
                proc_in_exp = process_input[field]
                assert proc_in_res in (proc_in_exp, str(proc_in_exp)), \
                    "Field '{}' of input '{}'({}) is expected to be '{}' but was '{}'" \
                    .format(field, process_input, i, proc_in_exp, proc_in_res)

    @mocked_aws_credentials
    @mocked_aws_s3
    def test_execute_job_with_array_input(self):
        """
        The test validates job can receive an array as input and process it as expected
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": ["python3", "script.py"],
            "inputs":
            {
                "test_int_array": {"type": {"type": "array", "items": "int"}},
                "test_float_array": {"type": {"type": "array", "items": "float"}},
                "test_string_array": {"type": {"type": "array", "items": "string"}},
                "test_reference_array": {"type": {"type": "array", "items": "File"}},
                "test_int_value": "int",
                "test_float_value": "float",
                "test_string_value": "string",
                "test_reference_http_value": "File",
                "test_reference_file_value": "File",
                "test_reference_s3_value": "File"
            },
            "requirements": {
                CWL_REQUIREMENT_INIT_WORKDIR: {
                    "listing": [
                        {
                            "entryname": "script.py",
                            "entry": cleandoc("""
                                import json
                                import os
                                input = $(inputs)
                                for key, value in input.items():
                                    if isinstance(value, list):
                                        if all(isinstance(val, int) for val in value):
                                            value = map(lambda v: v+1, value)
                                        elif all(isinstance(val, float) for val in value):
                                            value = map(lambda v: v+0.5, value)
                                        elif all(isinstance(val, bool) for val in value):
                                            value = map(lambda v: not v, value)
                                        elif all(isinstance(val, str) for val in value):
                                            value = map(lambda v: v.upper(), value)
                                        elif all(isinstance(val, dict) for val in value):
                                            def tmp(value):
                                                path_ = value.get('path')
                                                if path_ and os.path.exists(path_):
                                                    with open (path_, 'r') as file_:
                                                        filedata = file_.read()
                                                return filedata.upper()
                                            value = map(tmp, value)
                                        input[key] = ";".join(map(str, value))
                                    elif isinstance(value, dict):
                                        path_ = value.get('path')
                                        if path_ and os.path.exists(path_):
                                            with open (path_, 'r') as file_:
                                                filedata = file_.read()
                                            input[key] = filedata.upper()
                                    elif isinstance(value, str):
                                        input[key] = value.upper()
                                    elif isinstance(value, bool):
                                        input[key] = not value
                                    elif isinstance(value, int):
                                        input[key] = value+1
                                    elif isinstance(value, float):
                                        input[key] = value+0.5
                                json.dump(input, open("tmp.txt","w"))
                                """)
                        }
                    ]
                }
            },
            "outputs": [{"id": "output_test", "type": "File", "outputBinding": {"glob": "tmp.txt"}}],
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                },
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        try:
            desc, _ = self.deploy_process(body)
        except colander.Invalid:
            self.fail("Test")

        assert desc["process"] is not None

        test_bucket_ref = mocked_aws_s3_bucket_test_file(
            "wps-process-test-bucket",
            "input_file_s3.txt",
            "This is a generated file for s3 test"
        )

        test_http_ref = mocked_http_test_file(
            self.settings["weaver.wps_output_dir"],
            "http://localhost/input_file_http.txt",
            "This is a generated file for http test"
        )

        test_file_ref = mocked_file_test(
            self.settings["weaver.wps_output_dir"],
            "input_file_ref.txt",
            "This is a generated file for file test"
        )

        exec_body = {
            "mode": EXECUTE_MODE_ASYNC,
            "response": EXECUTE_RESPONSE_DOCUMENT,
            "inputs":
            [
                {"id": "test_int_array", "value": [10, 20, 30, 40, 50]},
                {"id": "test_float_array", "value": [10.03, 20.03, 30.03, 40.03, 50.03]},
                {"id": "test_string_array", "value": ["this", "is", "a", "test"]},
                {"id": "test_reference_array",
                 "value": [{"href": test_file_ref},
                           {"href": test_http_ref},
                           {"href": test_bucket_ref}
                           ]
                 },
                {"id": "test_int_value", "value": 2923},
                {"id": "test_float_value", "value": 389.73},
                {"id": "test_string_value", "value": "stringtest"},
                {"id": "test_reference_http_value", "href": test_http_ref},
                {"id": "test_reference_file_value", "href": test_file_ref},
                {"id": "test_reference_s3_value", "href": test_bucket_ref}
            ],
            "outputs": [
                {"id": "output_test", "type": "File"},
            ]
        }

        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_process():
                stack_exec.enter_context(mock_exec)
            proc_url = "/processes/{}/jobs".format(self._testMethodName)
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], "Failed with: [{}]\nReason:\n{}".format(resp.status_code, resp.json)
            status_url = resp.json.get("location")

        results = self.monitor_job(status_url)

        job_output_file = results.get("output_test")["href"].split("/", 3)[-1]
        tmpfile = "{}/{}".format(self.settings["weaver.wps_output_dir"], job_output_file)

        try:
            processed_values = json.load(open(tmpfile, "r"))
        except FileNotFoundError:
            self.fail("Output file [{}] was not found where it was expected to resume test".format(tmpfile))
        except Exception as exception:
            self.fail("An error occured during the reading of the file: {}".format(exception))
        assert processed_values["test_int_array"] == "11;21;31;41;51"
        assert processed_values["test_float_array"] == "10.53;20.53;30.53;40.53;50.53"
        assert processed_values["test_string_array"] == "THIS;IS;A;TEST"
        assert processed_values["test_reference_array"] == ("THIS IS A GENERATED FILE FOR FILE TEST;"
                                                            "THIS IS A GENERATED FILE FOR HTTP TEST;"
                                                            "THIS IS A GENERATED FILE FOR S3 TEST")
        assert processed_values["test_int_value"] == 2924
        assert processed_values["test_float_value"] == 390.23
        assert processed_values["test_string_value"] == "STRINGTEST"
        assert processed_values["test_reference_s3_value"] == "THIS IS A GENERATED FILE FOR S3 TEST"
        assert processed_values["test_reference_http_value"] == "THIS IS A GENERATED FILE FOR HTTP TEST"
        assert processed_values["test_reference_file_value"] == "THIS IS A GENERATED FILE FOR FILE TEST"

    # FIXME: test not working
    #   same payloads sent directly to running weaver properly raise invalid schema -> bad request error
    #   somehow they don't work within this test (not raised)...
    @pytest.mark.xfail(reason="MinOccurs/MaxOccurs somehow fail validation here, but s")
    def test_invalid_io_min_max_occurs_wrong_format(self):
        """
        Test verifies that ``minOccurs`` and/or ``maxOccurs`` definitions other than allowed formats are
        raised as invalid schemas.

        .. seealso::
            - :meth:`test_valid_io_min_max_occurs_as_str_or_int`
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": [{}],   # updated after
            "outputs": {"values": {"type": "string"}}
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                },
                "inputs": [{}]    # updated after
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }

        # replace by invalid min/max and check that it raises
        cwl["inputs"][0] = {"id": "test", "type": {"type": "array", "items": "string"}}
        body["processDescription"]["inputs"][0] = {"id": "test", "minOccurs": [1], "maxOccurs": 1}
        with self.assertRaises(colander.Invalid):
            self.deploy_process(body)
            self.fail("Invalid input minOccurs schema definition should have been raised")

        cwl["inputs"][0] = {"id": "test", "type": {"type": "array", "items": "string"}}
        body["processDescription"]["inputs"][0] = {"id": "test", "minOccurs": 1, "maxOccurs": 3.1416}
        with self.assertRaises(HTTPBadRequest):
            self.deploy_process(body)
            self.fail("Invalid input maxOccurs schema definition should have been raised")

    def test_complex_io_from_package(self):
        """
        Test validates that complex I/O definitions *only* defined in the `CWL` package as `JSON` within the
        deployment body generates expected `WPS` process description I/O with corresponding formats and values.
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": {
                "url": {
                    "type": "File"
                }
            },
            "outputs": {
                "files": {
                    "type": {
                        "type": "array",
                        "items": "File",
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
        desc, _ = self.deploy_process(body)
        assert desc["process"]["id"] == self._testMethodName
        assert desc["process"]["title"] == "some title"
        assert desc["process"]["abstract"] == "this is a test"
        assert isinstance(desc["process"]["inputs"], list)
        assert len(desc["process"]["inputs"]) == 1
        assert desc["process"]["inputs"][0]["id"] == "url"
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "1"
        assert isinstance(desc["process"]["inputs"][0]["formats"], list)
        assert len(desc["process"]["inputs"][0]["formats"]) == 1
        assert isinstance(desc["process"]["inputs"][0]["formats"][0], dict)
        assert desc["process"]["inputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][0]["formats"][0]["default"] is True
        assert isinstance(desc["process"]["outputs"], list)
        assert len(desc["process"]["outputs"]) == 1
        assert desc["process"]["outputs"][0]["id"] == "files"
        assert "minOccurs" not in desc["process"]["outputs"][0]
        assert "maxOccurs" not in desc["process"]["outputs"][0]
        assert isinstance(desc["process"]["outputs"][0]["formats"], list)
        assert len(desc["process"]["outputs"][0]["formats"]) == 1
        assert isinstance(desc["process"]["outputs"][0]["formats"][0], dict)
        assert desc["process"]["outputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["outputs"][0]["formats"][0]["default"] is True
        assert len(set(desc["process"].keys()) - KNOWN_PROCESS_DESCRIPTION_FIELDS) == 0

    def test_complex_io_from_package_and_offering(self):
        """
        Test validates that complex I/O definitions simultaneously defined in *both* (but not necessarily for each
        one and exhaustively) `CWL` and `WPS` payloads are correctly resolved. More specifically, verifies that:

            - `WPS` I/O that don't match any `CWL` I/O by ID are removed completely.
            - `WPS` I/O that were omitted are added with minimal detail requirements using corresponding `CWL` I/O
            - `WPS` I/O complementary details are added to corresponding `CWL` I/O (no duplication of IDs)

        .. seealso::
            - :func:`weaver.processes.wps_package._merge_package_io`
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": [
                {
                    "id": "complex_input_only_cwl_minimal",
                    "label": "Complex Input Only CWL Minimal",
                    "type": "File"
                },
                {
                    "id": "complex_input_both_cwl_and_wps",
                    "label": "Complex Input Both CWL and WPS - From CWL",
                    "type": "File"
                },
            ],
            "outputs": [
                {
                    "id": "complex_output_only_cwl_minimal",
                    "label": "Complex Output Only CWL Minimal",
                    "type": "File",
                },
                {
                    "id": "complex_output_both_cwl_and_wps",
                    "type": "File"
                }
            ]
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                    "inputs": [
                        {
                            "id": "complex_input_only_wps_removed",
                        },
                        {
                            "id": "complex_input_both_cwl_and_wps",
                            "title": "Extra detail for I/O both in CWL and WPS"
                        }
                    ],
                    "outputs": [
                        {
                            "id": "complex_output_only_wps_removed"
                        },
                        {
                            "id": "complex_output_both_cwl_and_wps",
                            "title": "Additional detail only within WPS output"
                        }
                    ]
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
        assert len(desc["process"]["inputs"]) == 2
        assert desc["process"]["inputs"][0]["id"] == "complex_input_only_cwl_minimal"
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "1"
        assert len(desc["process"]["inputs"][0]["formats"]) == 1, \
            "Default format should be added to process definition when omitted from both CWL and WPS"
        assert desc["process"]["inputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][0]["formats"][0]["default"] is True
        assert desc["process"]["inputs"][1]["id"] == "complex_input_both_cwl_and_wps"
        assert desc["process"]["inputs"][1]["minOccurs"] == "1"
        assert desc["process"]["inputs"][1]["maxOccurs"] == "1"
        assert len(desc["process"]["inputs"][1]["formats"]) == 1, \
            "Default format should be added to process definition when omitted from both CWL and WPS"
        assert desc["process"]["inputs"][1]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["inputs"][1]["formats"][0]["default"] is True
        assert desc["process"]["inputs"][1]["title"] == "Extra detail for I/O both in CWL and WPS", \
            "Additional details defined only in WPS matching CWL I/O by ID should be preserved"
        assert isinstance(desc["process"]["outputs"], list)
        assert len(desc["process"]["outputs"]) == 2
        assert desc["process"]["outputs"][0]["id"] == "complex_output_only_cwl_minimal"
        assert len(desc["process"]["outputs"][0]["formats"]) == 1, \
            "Default format should be added to process definition when omitted from both CWL and WPS"
        assert desc["process"]["outputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["outputs"][0]["formats"][0]["default"] is True
        assert desc["process"]["outputs"][1]["id"] == "complex_output_both_cwl_and_wps"
        assert len(desc["process"]["outputs"][1]["formats"]) == 1, \
            "Default format should be added to process definition when omitted from both CWL and WPS"
        assert desc["process"]["outputs"][1]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN
        assert desc["process"]["outputs"][1]["formats"][0]["default"] is True
        assert desc["process"]["outputs"][1]["title"] == "Additional detail only within WPS output", \
            "Additional details defined only in WPS matching CWL I/O by ID should be preserved"

        assert len(pkg["inputs"]) == 2
        assert pkg["inputs"][0]["id"] == "complex_input_only_cwl_minimal"
        assert "format" not in pkg["inputs"][0], "Omitted formats in CWL and WPS I/O definitions during deployment" \
                                                 "should not add them to the generated CWL package definition"
        assert pkg["inputs"][1]["id"] == "complex_input_both_cwl_and_wps"
        # FIXME:
        #   https://github.com/crim-ca/weaver/issues/31
        #   https://github.com/crim-ca/weaver/issues/50
        # assert pkg["inputs"][1]["label"] == "Extra detail for I/O both in CWL and WPS", \
        #     "WPS I/O title should be converted to CWL label of corresponding I/O from additional details"
        assert "format" not in pkg["inputs"][1], "Omitted formats in CWL and WPS I/O definitions during deployment" \
                                                 "should not add them to the generated CWL package definition"
        assert len(pkg["outputs"]) == 2
        assert pkg["outputs"][0]["id"] == "complex_output_only_cwl_minimal"
        assert "format" not in pkg["outputs"][0], "Omitted formats in CWL and WPS I/O definitions during deployment" \
                                                  "should not add them to the generated CWL package definition"
        assert pkg["outputs"][1]["id"] == "complex_output_both_cwl_and_wps"
        # FIXME:
        #   https://github.com/crim-ca/weaver/issues/31
        #   https://github.com/crim-ca/weaver/issues/50
        # assert pkg["outputs"][1]["label"] == "Additional detail only within WPS output", \
        #     "WPS I/O title should be converted to CWL label of corresponding I/O from additional details"
        assert "format" not in pkg["outputs"][1], "Omitted formats in CWL and WPS I/O definitions during deployment" \
                                                  "should not add them to the generated CWL package definition"

    def test_literal_and_complex_io_from_wps_xml_reference(self):
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "executionUnit": [{"href": "mock://{}".format(resources.WPS_LITERAL_COMPLEX_IO)}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication"
        }
        desc, pkg = self.deploy_process(body)

        # basic contents validation
        assert "cwlVersion" in pkg
        assert "process" in desc
        assert desc["process"]["id"] == self._testMethodName

        # package I/O validation
        assert "inputs" in pkg
        assert len(pkg["inputs"]) == 2
        assert isinstance(pkg["inputs"], list)
        assert pkg["inputs"][0]["id"] == "tasmax"
        assert "default" not in pkg["inputs"][0]
        assert pkg["inputs"][0]["format"] == EDAM_NETCDF
        assert isinstance(pkg["inputs"][0]["type"], list), "since minOccurs=1, single value non-array must be allowed"
        assert len(pkg["inputs"][0]["type"]) == 2, "single type and array type of same base"
        assert pkg["inputs"][0]["type"][0] == "File", "since minOccurs=1, should be type directly"
        assert pkg["inputs"][0]["type"][1]["type"] == "array"
        assert pkg["inputs"][0]["type"][1]["items"] == "File", "since maxOccurs>1, same base type must array"
        assert pkg["inputs"][1]["id"] == "freq"
        assert pkg["inputs"][1]["default"] == "YS"
        assert isinstance(pkg["inputs"][1]["type"], list), "since minOccurs=0, should be a list with 'null' type"
        assert len(pkg["inputs"][1]["type"]) == 2
        assert pkg["inputs"][1]["type"][0] == "null"
        assert pkg["inputs"][1]["type"][1]["type"] == "enum"
        assert pkg["inputs"][1]["type"][1]["symbols"] == ["YS", "MS", "QS-DEC", "AS-JUL"]
        assert "outputs" in pkg
        assert len(pkg["outputs"]) == 2
        assert isinstance(pkg["outputs"], list)
        assert pkg["outputs"][0]["id"] == "output_netcdf"
        assert "default" not in pkg["outputs"][0]
        assert pkg["outputs"][0]["format"] == EDAM_NETCDF
        assert pkg["outputs"][0]["type"] == "File"
        assert pkg["outputs"][0]["outputBinding"]["glob"] == "output_netcdf.nc"
        assert pkg["outputs"][1]["id"] == "output_log"
        assert "default" not in pkg["outputs"][1]
        assert pkg["outputs"][1]["format"] == EDAM_PLAIN
        assert pkg["outputs"][1]["type"] == "File"
        assert pkg["outputs"][1]["outputBinding"]["glob"] == "output_log.*"

        # process description I/O validation
        assert len(desc["process"]["inputs"]) == 2
        assert desc["process"]["inputs"][0]["id"] == "tasmax"
        assert desc["process"]["inputs"][0]["title"] == "Resource"
        assert desc["process"]["inputs"][0]["abstract"] == "NetCDF Files or archive (tar/zip) containing netCDF files."
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "1000"
        assert len(desc["process"]["inputs"][0]["formats"]) == 1
        assert desc["process"]["inputs"][0]["formats"][0]["default"] is True
        assert desc["process"]["inputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["inputs"][0]["formats"][0]["encoding"] == "base64"
        assert desc["process"]["inputs"][1]["id"] == "freq"
        assert desc["process"]["inputs"][1]["title"] == "Frequency"
        assert desc["process"]["inputs"][1]["abstract"] == "Resampling frequency"
        assert desc["process"]["inputs"][1]["minOccurs"] == "0"
        assert desc["process"]["inputs"][1]["maxOccurs"] == "1"
        assert "formats" not in desc["process"]["inputs"][1]
        assert len(desc["process"]["outputs"]) == 2
        assert desc["process"]["outputs"][0]["id"] == "output_netcdf"
        assert desc["process"]["outputs"][0]["title"] == "Function output in netCDF"
        assert desc["process"]["outputs"][0]["abstract"] == "The indicator values computed on the original input grid."
        assert "minOccurs" not in desc["process"]["outputs"][0]
        assert "maxOccurs" not in desc["process"]["outputs"][0]
        assert len(desc["process"]["outputs"][0]["formats"]) == 1
        assert desc["process"]["outputs"][0]["formats"][0]["default"] is True
        assert desc["process"]["outputs"][0]["formats"][0]["mimeType"] == CONTENT_TYPE_APP_NETCDF
        assert desc["process"]["outputs"][0]["formats"][0]["encoding"] == "base64"
        assert desc["process"]["outputs"][1]["id"] == "output_log"
        assert desc["process"]["outputs"][1]["title"] == "Logging information"
        assert desc["process"]["outputs"][1]["abstract"] == "Collected logs during process run."
        assert "minOccurs" not in desc["process"]["outputs"][1]
        assert "maxOccurs" not in desc["process"]["outputs"][1]
        assert len(desc["process"]["outputs"][1]["formats"]) == 1
        assert desc["process"]["outputs"][1]["formats"][0]["default"] is True
        assert desc["process"]["outputs"][1]["formats"][0]["mimeType"] == CONTENT_TYPE_TEXT_PLAIN

    def test_enum_array_and_multi_format_inputs_from_wps_xml_reference(self):
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "executionUnit": [{"href": "mock://{}".format(resources.WPS_ENUM_ARRAY_IO)}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication"
        }
        desc, pkg = self.deploy_process(body)

        # basic contents validation
        assert "cwlVersion" in pkg
        assert "process" in desc
        assert desc["process"]["id"] == self._testMethodName

        # package I/O validation
        assert "inputs" in pkg
        assert len(pkg["inputs"]) == 3
        assert isinstance(pkg["inputs"], list)
        assert pkg["inputs"][0]["id"] == "region"
        assert pkg["inputs"][0]["default"] == "DEU"
        # first input
        assert "format" not in pkg["inputs"][0]
        assert isinstance(pkg["inputs"][0]["type"], list)
        # single entry of enum allowed values
        assert len(pkg["inputs"][0]["type"]) == 2, "single type and array type of same base"
        assert isinstance(pkg["inputs"][0]["type"][0], dict), "enum base type expected since allowed values"
        assert pkg["inputs"][0]["type"][0]["type"] == "enum"
        assert isinstance(pkg["inputs"][0]["type"][0]["symbols"], list)
        assert len(pkg["inputs"][0]["type"][0]["symbols"]) == 220
        assert all(isinstance(s, str) for s in pkg["inputs"][0]["type"][0]["symbols"])
        # array type of same enum allowed values
        assert pkg["inputs"][0]["type"][1]["type"] == "array"
        assert pkg["inputs"][0]["type"][1]["items"]["type"] == "enum"
        assert isinstance(pkg["inputs"][0]["type"][1]["items"]["symbols"], list)
        assert len(pkg["inputs"][0]["type"][1]["items"]["symbols"]) == 220
        assert all(isinstance(s, str) for s in pkg["inputs"][0]["type"][1]["items"]["symbols"])
        # second input
        assert pkg["inputs"][1]["id"] == "mosaic"
        assert pkg["inputs"][1]["default"] == "null"
        assert "format" not in pkg["inputs"][1]
        assert isinstance(pkg["inputs"][1]["type"], list), "default 'null' result type formed with it"
        assert len(pkg["inputs"][1]["type"]) == 2
        assert pkg["inputs"][1]["type"][0] == "null"
        assert pkg["inputs"][1]["type"][1] == "boolean"
        assert pkg["inputs"][2]["id"] == "resource"
        assert "default" not in pkg["inputs"][2]
        assert isinstance(pkg["inputs"][2]["type"], list), "single and array File"
        assert len(pkg["inputs"][2]["type"]) == 2
        assert pkg["inputs"][2]["type"][0] == "File", "single File type"
        assert pkg["inputs"][2]["type"][1]["type"] == "array"
        assert pkg["inputs"][2]["type"][1]["items"] == "File", "corresponding base type for array type"
        # FIXME: TAR cannot be resolved in the CWL context (not official, disable mapping to GZIP)
        #        this makes all formats to not be resolved (see code: wps_package.any2cwl_io)
        #        (see issue: https://github.com/crim-ca/weaver/issues/50)
        assert "format" not in pkg["inputs"][2], \
            "CWL formats should all be dropped because (x-tar) cannot be resolved to an existing schema reference"
        # assert isinstance(pkg["inputs"][2]["format"], list)
        # assert len(pkg["inputs"][2]["format"]) == 3
        # assert pkg["inputs"][2]["format"][0] == EDAM_NETCDF
        # assert pkg["inputs"][2]["format"][1] == IANA_TAR
        # assert pkg["inputs"][2]["format"][2] == IANA_ZIP

        # process description I/O validation
        assert len(desc["process"]["inputs"]) == 3
        assert desc["process"]["inputs"][0]["id"] == "region"
        assert desc["process"]["inputs"][0]["title"] == "Region"
        assert desc["process"]["inputs"][0]["abstract"] == "Country code, see ISO-3166-3"
        assert desc["process"]["inputs"][0]["minOccurs"] == "1"
        assert desc["process"]["inputs"][0]["maxOccurs"] == "220"
        assert "formats" not in desc["process"]["inputs"][0]
        assert desc["process"]["inputs"][1]["id"] == "mosaic"
        assert desc["process"]["inputs"][1]["title"] == "Union of multiple regions"
        assert desc["process"]["inputs"][1]["abstract"] == \
               "If True, selected regions will be merged into a single geometry."   # noqa
        assert desc["process"]["inputs"][1]["minOccurs"] == "0"
        assert desc["process"]["inputs"][1]["maxOccurs"] == "1"
        assert "formats" not in desc["process"]["inputs"][1]
        assert desc["process"]["inputs"][2]["id"] == "resource"
        assert desc["process"]["inputs"][2]["title"] == "Resource"
        assert desc["process"]["inputs"][2]["abstract"] == "NetCDF Files or archive (tar/zip) containing NetCDF files."
        assert desc["process"]["inputs"][2]["minOccurs"] == "1"
        assert desc["process"]["inputs"][2]["maxOccurs"] == "1000"
        # note: TAR should remain as literal format in the WPS context (not mapped/added as GZIP when resolved for CWL)
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
    @pytest.mark.skip(reason="not implemented")
    def test_multi_outputs_file_from_wps_xml_reference(self):
        raise NotImplementedError


@pytest.mark.functional
class WpsPackageAppWithS3BucketTest(WpsPackageConfigBase):
    @classmethod
    def setUpClass(cls):
        cls.settings = {
            "weaver.wps": True,
            "weaver.wps_output": True,
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_dir": "/tmp",  # nosec: B108 # don't care hardcoded for test
            "weaver.wps_output_s3_bucket": "wps-output-test-bucket",
            "weaver.wps_output_s3_region": MOCK_AWS_REGION,  # must match exactly, or mock will not work
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
        }
        super(WpsPackageAppWithS3BucketTest, cls).setUpClass()

    @mocked_aws_credentials
    @mocked_aws_s3
    def test_execute_application_package_process_with_bucket(self):
        """
        Test validates:
            - Both S3 bucket and HTTP file references can be used simultaneously as inputs.
            - Process results are uploaded to the configured S3 bucket.
            - Process results are not accessible locally (not referenced as WPS-outputs URL, but as S3 reference).

        .. note::
            Input resolution will be different in case of `Workflow Process`, see :ref:`File Type References`.
            This test is intended for `Application Process` executed locally as `CWL` package (script).
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": "echo",
            "arguments": ["$(runtime.outdir)"],
            "requirements": {
                CWL_REQUIREMENT_INIT_WORKDIR: {
                    # directly copy files to output dir in order to retrieve them by glob
                    "listing": [
                        {"entry": "$(inputs.input_with_http)"},
                        {"entry": "$(inputs.input_with_s3)"},
                    ]
                }
            },
            "hints": {CWL_REQUIREMENT_APP_BUILTIN: {
                # ensure remote files are downloaded prior to CWL execution
                "process": self._testMethodName,
            }},
            "inputs": [
                # regardless of reference type, they must be fetched as file before CWL call
                {"id": "input_with_http", "type": "File"},
                {"id": "input_with_s3", "type": "File"},
            ],
            "outputs": [
                # both process result references will be S3 buckets, but CWL will see them as file on disk after fetch
                # we simply forward the input to outputs using the same name for this test
                # it is Weaver that does the S3 upload after process completed successfully
                {"id": "output_from_http", "type": "File",
                 "outputBinding": {"glob": "$(inputs.input_with_http.basename)"}},
                {"id": "output_from_s3", "type": "File",
                 "outputBinding": {"glob": "$(inputs.input_with_s3.basename)"}}
            ]
        }
        body = {
            "processDescription": {
                "process": {"id": self._testMethodName}
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        self.deploy_process(body)

        input_file_s3 = "input-s3.txt"
        input_file_http = "media-types.txt"  # use some random HTTP location that actually exists (will be fetched)
        test_http_ref = "https://www.iana.org/assignments/media-types/{}".format(input_file_http)
        test_bucket_ref = mocked_aws_s3_bucket_test_file("wps-process-test-bucket", input_file_s3)
        exec_body = {
            "mode": EXECUTE_MODE_ASYNC,
            "response": EXECUTE_RESPONSE_DOCUMENT,
            "inputs": [
                {"id": "input_with_http", "href": test_http_ref},
                {"id": "input_with_s3", "href": test_bucket_ref},
            ],
            "outputs": [
                {"id": "output_from_http", "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE},
                {"id": "output_from_s3", "transmissionMode": EXECUTE_TRANSMISSION_MODE_REFERENCE},
            ]
        }
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_process():
                stack_exec.enter_context(mock_exec)
            proc_url = "/processes/{}/jobs".format(self._testMethodName)
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], "Failed with: [{}]\nReason:\n{}".format(resp.status_code, resp.json)
            status_url = resp.json["location"]
            job_id = resp.json["jobID"]

        results = self.monitor_job(status_url)
        outputs = self.get_outputs(status_url)

        assert "output_from_http" in results
        assert "output_from_s3" in results

        # check that outputs are S3 bucket references
        output_values = {out["id"]: get_any_value(out) for out in outputs["outputs"]}
        output_bucket = self.settings["weaver.wps_output_s3_bucket"]
        wps_uuid = self.job_store.fetch_by_id(job_id).wps_id
        for out_key, out_file in [("output_from_s3", input_file_s3), ("output_from_http", input_file_http)]:
            output_ref = "{}/{}/{}".format(output_bucket, wps_uuid, out_file)
            output_ref_abbrev = "s3://{}".format(output_ref)
            output_ref_full = "https://s3.{}.amazonaws.com/{}".format(MOCK_AWS_REGION, output_ref)
            output_ref_any = [output_ref_abbrev, output_ref_full]  # allow any variant weaver can parse
            # validation on outputs path
            assert output_values[out_key] in output_ref_any
            # validation on results path
            assert results[out_key]["href"] in output_ref_any

        # FIXME:
        #   can validate manually that files exists in output bucket, but cannot seem to retrieve it here
        #   problem due to fixture setup or moto limitation via boto3.resource interface used by pywps?
        # check that outputs are indeed stored in S3 buckets
        import boto3
        mocked_s3 = boto3.client("s3", region_name=MOCK_AWS_REGION)
        resp_json = mocked_s3.list_objects_v2(Bucket=output_bucket)
        bucket_file_keys = [obj["Key"] for obj in resp_json["Contents"]]
        for out_file in [input_file_s3, input_file_http]:
            out_key = "{}/{}".format(job_id, out_file)
            assert out_key in bucket_file_keys

        # check that outputs are NOT copied locally, but that XML status does exist
        # counter validate path with file always present to ensure outputs are not 'missing' just because of wrong dir
        wps_outdir = self.settings["weaver.wps_output_dir"]
        for out_file in [input_file_s3, input_file_http]:
            assert not os.path.exists(os.path.join(wps_outdir, out_file))
            assert not os.path.exists(os.path.join(wps_outdir, job_id, out_file))
            assert not os.path.exists(os.path.join(wps_outdir, wps_uuid, out_file))
        assert os.path.isfile(os.path.join(wps_outdir, "{}.xml".format(job_id)))
