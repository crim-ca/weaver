"""
Functional tests of operations implemented by :mod:`weaver.processes.wps_package`.

Validates that CWL package definitions are parsed and executes the process as intended.
Local test web application is employed to run operations by mocking external requests.

.. seealso::
    - :mod:`tests.processes.wps_package`.
"""

import contextlib
import copy
import inspect
import json
import logging
import os
import re
import shutil
import tempfile
from typing import TYPE_CHECKING

import boto3
import colander
import mock
import pytest
import responses
import yaml
from parameterized import parameterized

from tests import resources
from tests.functional import TEST_DATA_ROOT
from tests.functional.utils import ResourcesUtil, WpsConfigBase
from tests.utils import (
    MOCK_AWS_REGION,
    MOCK_HTTP_REF,
    mocked_aws_config,
    mocked_aws_s3,
    mocked_aws_s3_bucket_test_file,
    mocked_dismiss_process,
    mocked_execute_celery,
    mocked_file_server,
    mocked_http_file,
    mocked_reference_test_file,
    mocked_remote_server_requests_wps1,
    mocked_sub_requests,
    mocked_wps_output,
    setup_aws_s3_bucket
)
from weaver.execute import (
    ExecuteCollectionFormat,
    ExecuteControlOption,
    ExecuteMode,
    ExecuteResponse,
    ExecuteReturnPreference,
    ExecuteTransmissionMode
)
from weaver.formats import (
    EDAM_MAPPING,
    EDAM_NAMESPACE,
    IANA_NAMESPACE,
    OGC_MAPPING,
    OGC_NAMESPACE,
    AcceptLanguage,
    ContentType,
    get_cwl_file_format,
    repr_json
)
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_INIT_WORKDIR,
    CWL_REQUIREMENT_INLINE_JAVASCRIPT,
    CWL_REQUIREMENT_RESOURCE,
    CWL_REQUIREMENT_SECRETS,
    JobInputsOutputsSchema,
    ProcessSchema
)
from weaver.processes.types import ProcessType
from weaver.status import Status
from weaver.utils import fetch_file, get_any_value, get_header, get_path_kvp, is_uuid, load_file, parse_kvp
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url, map_wps_output_location
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import List

    from responses import RequestsMock

    from weaver.typedefs import (
        CWL_AnyRequirements,
        CWL_RequirementsDict,
        JSON,
        Number,
        ProcessOfferingListing,
        ProcessOfferingMapping
    )

EDAM_PLAIN = f"{EDAM_NAMESPACE}:{EDAM_MAPPING[ContentType.TEXT_PLAIN]}"
OGC_NETCDF = f"{OGC_NAMESPACE}:{OGC_MAPPING[ContentType.APP_NETCDF]}"
# note: x-tar cannot be mapped during CWL format resolution (not official schema),
#       it remains explicit tar definition in WPS context
IANA_TAR = f"{IANA_NAMESPACE}:{ContentType.APP_TAR}"  # noqa # pylint: disable=unused-variable
IANA_ZIP = f"{IANA_NAMESPACE}:{ContentType.APP_ZIP}"  # noqa # pylint: disable=unused-variable

KNOWN_PROCESS_DESCRIPTION_FIELDS = {
    "id", "title", "description", "mutable", "version", "keywords", "metadata", "inputs", "outputs",
    "executeEndpoint", "processDescriptionURL", "processEndpointWPS1", "visibility"
}
# intersection of fields in InputType and specific sub-schema LiteralInputType
KNOWN_PROCESS_DESCRIPTION_INPUT_DATA_FIELDS = {
    "id", "title", "description", "keywords", "metadata", "links", "literalDataDomains", "additionalParameters",
    "minOccurs", "maxOccurs", "schema"
}
# corresponding schemas of input, but min/max occurs not expected
KNOWN_PROCESS_DESCRIPTION_OUTPUT_DATA_FIELDS = KNOWN_PROCESS_DESCRIPTION_INPUT_DATA_FIELDS - {"minOccurs", "maxOccurs"}

LOGGER = logging.getLogger(__name__)


@pytest.mark.functional
class WpsPackageAppTest(WpsConfigBase, ResourcesUtil):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = {
            "weaver.wps": True,
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_url": "http://localhost/wpsoutputs",
            "weaver.wps_output_dir": "/tmp/weaver-test/wps-outputs",  # nosec: B108 # don't care hardcoded for test
        }
        super(WpsPackageAppTest, cls).setUpClass()

    def setUp(self) -> None:
        self.process_store.clear_processes()

    def test_deploy_cwl_label_as_process_title(self):
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
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        assert desc["title"] == title
        assert pkg["label"] == title

    def test_deploy_ogc_schema(self):
        title = "This process title comes from the CWL label"
        cwl = {
            "cwlVersion": "v1.0",
            "label": title,
            "class": "CommandLineTool",
            "inputs": {"url": {"type": "string"}},
            "outputs": {"values": {"type": "float"}}
        }
        body = {
            "processDescription": {"id": self._testMethodName},  # not nested under 'process'
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        assert "inputs" in pkg and isinstance(pkg["inputs"], list) and len(pkg["inputs"]) == 1
        assert "outputs" in pkg and isinstance(pkg["outputs"], list) and len(pkg["outputs"]) == 1
        assert pkg["inputs"][0]["id"] == "url"
        assert pkg["outputs"][0]["id"] == "values"

        assert "inputs" in desc and isinstance(desc["inputs"], dict) and len(desc["inputs"]) == 1
        assert "outputs" in desc and isinstance(desc["outputs"], dict) and len(desc["outputs"]) == 1
        assert "url" in desc["inputs"]
        assert "values" in desc["outputs"]

        # even if deployed as OGC schema, OLD schema can be converted back
        desc = self.describe_process(self._testMethodName, ProcessSchema.OLD)
        proc = desc["process"]  # type: ProcessOfferingListing
        assert "inputs" in proc and isinstance(proc["inputs"], list) and len(proc["inputs"]) == 1
        assert "outputs" in proc and isinstance(proc["outputs"], list) and len(proc["outputs"]) == 1
        assert proc["inputs"][0]["id"] == "url"
        assert proc["outputs"][0]["id"] == "values"

    def test_deploy_ogc_with_io_oas_definitions(self):
        """
        Validate deployment when :term:`Process` definition includes I/O with OpenAPI ``schema`` fields.

        When provided during deployment, I/O ``schema`` definitions should be kept as-is because they *should*
        be more precise for the intended usage by the application then what `Weaver` can resolve by itself.

        Using provided I/O ``schema`` definitions, `Weaver` should backport all corresponding information that
        can be used to form other similar fields (for ``OLD`` representation and other backward compatibility).

        .. seealso::
            Files for ``EchoProcess`` use reference :term:`OGC` definitions. See links in contents.
        """
        ref = self.retrieve_payload("EchoProcess", "describe", local=True)
        cwl = self.retrieve_payload("EchoProcess", "package", local=True)
        body = {
            "processDescription": ref,
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            "executionUnit": [{"unit": cwl}],
        }

        desc, _ = self.deploy_process(body, process_id=self._testMethodName, describe_schema=ProcessSchema.OGC)
        assert "inputs" in desc and isinstance(desc["inputs"], dict) and len(desc["inputs"]) == len(ref["inputs"])
        assert "outputs" in desc and isinstance(desc["outputs"], dict) and len(desc["outputs"]) == len(ref["outputs"])
        assert all(isinstance(val, dict) and isinstance(val.get("schema"), dict) for val in desc["inputs"].values())
        assert all(isinstance(val, dict) and isinstance(val.get("schema"), dict) for val in desc["outputs"].values())

        # NOTE:
        #   Schema definitions are slightly modified when compatible information is detected from other CWL/WPS sources
        #   to improve their validation. For example, min/max occurs can help define singe/multi-value/array type.
        # check obtained/extended schemas case by case based on expected merging of definitions
        assert desc["inputs"]["arrayInput"]["schema"] == ref["inputs"]["arrayInput"]["schema"]  # no change
        assert desc["inputs"]["boundingBoxInput"]["schema"] == {
            "oneOf": [
                {
                    # what is referenced by $ref, converted to $id after retrieval
                    "type": "object",
                    "properties": {
                        "crs": {
                            "type": "string",
                            "format": "uri",
                            "default": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                            "enum": [
                                "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                                "http://www.opengis.net/def/crs/OGC/0/CRS84h",
                            ]
                        },
                        "bbox": {
                            "type": "array",
                            "items": "number",
                            "oneOf": [
                                {"minItems": 4, "maxItems": 4},
                                {"minItems": 6, "maxItems": 6},
                            ]
                        }
                    },
                    "required": ["bbox"],
                    # merged:
                    "format": sd.OGC_API_BBOX_FORMAT,
                    # added:
                    "$id": sd.OGC_API_BBOX_SCHEMA,
                },
                {
                    "type": "string",
                    "format": sd.OGC_API_BBOX_FORMAT,
                    "contentSchema": sd.OGC_API_BBOX_SCHEMA,
                }
            ]
        }
        assert desc["inputs"]["complexObjectInput"]["schema"] == {
            "oneOf": [
                # extended raw-data
                {"type": "string", "contentMediaType": "application/json"},
                # original definition
                ref["inputs"]["complexObjectInput"]["schema"]
            ]
        }
        assert desc["inputs"]["dateInput"]["schema"] == ref["inputs"]["dateInput"]["schema"]  # no change
        assert desc["inputs"]["doubleInput"]["schema"] == ref["inputs"]["doubleInput"]["schema"]  # no change
        assert desc["inputs"]["featureCollectionInput"]["schema"]["oneOf"][:2] == [
            # same as reference
            {
                "type": "string",
                "contentMediaType": "application/gml+xml; version=3.2"
            },
            {
                "type": "string",
                "contentMediaType": "application/vnd.google-earth.kml+xml",
                "contentSchema": "https://schemas.opengis.net/kml/2.3/ogckml23.xsd"
            },
        ]
        # extended contentMediaType using the provided JSON object $ref
        assert desc["inputs"]["featureCollectionInput"]["schema"]["oneOf"][2] == {
            "type": "string",
            "contentMediaType": "application/json",
            "contentSchema": "https://geojson.org/schema/FeatureCollection.json",
        }
        # extended and simplified from allOf/$ref
        assert desc["inputs"]["featureCollectionInput"]["schema"]["oneOf"][3]["allOf"][0]["format"] == (
            "geojson-feature-collection"
        )
        assert desc["inputs"]["featureCollectionInput"]["schema"]["oneOf"][3]["allOf"][1]["$ref"] == (
            "https://geojson.org/schema/FeatureCollection.json"
        )
        # check that actual full definition of $ref is not included (big JSON)
        assert all(
            field not in desc["inputs"]["featureCollectionInput"]["schema"]["oneOf"][3]
            for field in ["type", "properties"]
        )
        # min/max occurs detected => schema converted to array-only since minOccurs=2
        assert desc["inputs"]["geometryInput"]["schema"] == {
            "type": "array",
            "items": {"oneOf": [
                ref["inputs"]["geometryInput"]["schema"]["oneOf"][0],
                # extended from allOf/$ref
                {
                    "type": "string",
                    # FIXME: format not forwarded, but not really needed since specific contentSchema is provided
                    # "format": "geojson-geometry",
                    "contentMediaType": "application/json",
                    "contentSchema": (
                        "http://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/schemas/geometryGeoJSON.yaml"
                    )
                },
                # same as original allOf/$ref
                ref["inputs"]["geometryInput"]["schema"]["oneOf"][1],
            ]},
            "minItems": ref["inputs"]["geometryInput"]["minOccurs"],
            "maxItems": ref["inputs"]["geometryInput"]["maxOccurs"],
        }
        assert desc["inputs"]["imagesInput"]["schema"] == {
            "oneOf": [
                # same as original (except added 'format' for consistency)
                {
                    "type": "string", "format": "binary",
                    "contentEncoding": "binary", "contentMediaType": "image/tiff; application=geotiff"},
                {
                    "type": "string", "format": "binary",
                    "contentEncoding": "binary", "contentMediaType": "image/jp2"
                },
                # extended from minOccurs/maxOccurs detection
                {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 150,
                    "items": {
                        # equivalent to above single-value oneOf
                        "oneOf": [
                            {
                                "type": "string", "format": "binary",
                                "contentEncoding": "binary", "contentMediaType": "image/tiff; application=geotiff"
                            },
                            {
                                "type": "string", "format": "binary",
                                "contentEncoding": "binary", "contentMediaType": "image/jp2"
                            },
                        ]
                    }
                }
            ]
        }
        assert desc["inputs"]["measureInput"]["schema"] == {
            "oneOf": [
                # same as original definition with UoM requirements
                ref["inputs"]["measureInput"]["schema"],
                # extended additional "simple" representation of literal data directly provided
                {"type": "number", "format": "float"},
            ]
        }
        assert desc["inputs"]["stringInput"]["schema"] == ref["inputs"]["stringInput"]["schema"]  # no change

        # NOTE:
        #   although conversion is possible, min/max occurs not allowed in outputs WPS representation
        #   because of this, they will also be omitted in the OpenAPI schema definition following merge
        #   *everything else* should be identical to inputs
        assert desc["outputs"]["arrayOutput"]["schema"] == ref["outputs"]["arrayOutput"]["schema"]  # no change
        assert desc["outputs"]["boundingBoxOutput"]["schema"] == {
            "oneOf": [
                {
                    # what is referenced by $ref, converted to $id after retrieval
                    "type": "object",
                    "properties": {
                        "crs": {
                            "type": "string",
                            "format": "uri",
                            "default": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                            "enum": [
                                "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                                "http://www.opengis.net/def/crs/OGC/0/CRS84h",
                            ]
                        },
                        "bbox": {
                            "type": "array",
                            "items": "number",
                            "oneOf": [
                                {"minItems": 4, "maxItems": 4},
                                {"minItems": 6, "maxItems": 6},
                            ]
                        }
                    },
                    "required": ["bbox"],
                    # merged:
                    "format": sd.OGC_API_BBOX_FORMAT,
                    # added:
                    "$id": sd.OGC_API_BBOX_SCHEMA,
                },
                {
                    "type": "string",
                    "format": sd.OGC_API_BBOX_FORMAT,
                    "contentSchema": sd.OGC_API_BBOX_SCHEMA,
                }
            ]
        }
        assert desc["outputs"]["complexObjectOutput"]["schema"] == {
            "oneOf": [
                # extended raw-data
                {"type": "string", "contentMediaType": "application/json"},
                # original definition
                ref["outputs"]["complexObjectOutput"]["schema"]
            ]
        }
        assert desc["outputs"]["dateOutput"]["schema"] == ref["outputs"]["dateOutput"]["schema"]  # no change
        assert desc["outputs"]["doubleOutput"]["schema"] == ref["outputs"]["doubleOutput"]["schema"]  # no change
        assert desc["outputs"]["featureCollectionOutput"]["schema"]["oneOf"][:2] == [
            # same as reference
            {
                "type": "string",
                "contentMediaType": "application/gml+xml; version=3.2"
            },
            {
                "type": "string",
                "contentMediaType": "application/vnd.google-earth.kml+xml",
                "contentSchema": "https://schemas.opengis.net/kml/2.3/ogckml23.xsd"
            },
        ]
        # extended contentMediaType using the provided JSON object $ref
        assert desc["outputs"]["featureCollectionOutput"]["schema"]["oneOf"][2] == {
            "type": "string",
            "contentMediaType": "application/json",
            "contentSchema": "https://geojson.org/schema/FeatureCollection.json",
        }
        # extended and simplified from allOf/$ref
        assert desc["outputs"]["featureCollectionOutput"]["schema"]["oneOf"][3]["allOf"][0]["format"] == (
            "geojson-feature-collection"
        )
        assert desc["outputs"]["featureCollectionOutput"]["schema"]["oneOf"][3]["allOf"][1]["$ref"] == (
            "https://geojson.org/schema/FeatureCollection.json"
        )
        # check that actual full definition of $ref is not included (big JSON)
        assert all(
            field not in desc["outputs"]["featureCollectionOutput"]["schema"]["oneOf"][3]
            for field in ["type", "properties"]
        )
        # contrary to 'geometryInput', there is no min/max occurs since not available for outputs
        # because they are missing, there is no auto-expansion of 'oneOf' into *only* array items
        assert desc["outputs"]["geometryOutput"]["schema"] == {
            "oneOf": [
                ref["outputs"]["geometryOutput"]["schema"]["oneOf"][0],
                # extended from allOf/$ref
                {
                    "type": "string",
                    # FIXME: format not forwarded, but not really needed since specific contentSchema is provided
                    # "format": "geojson-geometry",
                    "contentMediaType": "application/json",
                    "contentSchema": (
                        "http://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/schemas/geometryGeoJSON.yaml"
                    )
                },
                # same as original allOf/$ref
                ref["outputs"]["geometryOutput"]["schema"]["oneOf"][1],
            ],
        }
        # contrary to 'imagesInput', there is no min/max occurs since not available for outputs
        # because they are missing, there is no auto-expansion of 'oneOf' into single + array items combinations
        # only single dimension are preserved
        assert desc["outputs"]["imagesOutput"]["schema"] == {
            "oneOf": [
                # same as original (except added 'format' for consistency)
                {
                    "type": "string", "format": "binary",
                    "contentEncoding": "binary", "contentMediaType": "image/tiff; application=geotiff"},
                {
                    "type": "string", "format": "binary",
                    "contentEncoding": "binary", "contentMediaType": "image/jp2"
                }
            ]
        }
        assert desc["outputs"]["measureOutput"]["schema"] == {
            "oneOf": [
                # same as original definition with UoM requirements
                ref["outputs"]["measureOutput"]["schema"],
                # extended additional "simple" representation of literal data directly provided
                {"type": "number", "format": "float"},
            ]
        }
        assert desc["outputs"]["stringOutput"]["schema"] == ref["outputs"]["stringOutput"]["schema"]  # no change

        # check detection of array min/max items => min/max occurs
        assert "minOccurs" in desc["inputs"]["arrayInput"]
        assert isinstance(desc["inputs"]["arrayInput"]["schema"]["minItems"], int)
        assert desc["inputs"]["arrayInput"]["minOccurs"] == desc["inputs"]["arrayInput"]["schema"]["minItems"]
        assert "maxOccurs" in desc["inputs"]["arrayInput"]
        assert isinstance(desc["inputs"]["arrayInput"]["schema"]["maxItems"], int)
        assert desc["inputs"]["arrayInput"]["maxOccurs"] == desc["inputs"]["arrayInput"]["schema"]["maxItems"]

        # contentMediaType => supported formats
        assert desc["inputs"]["complexObjectInput"]["formats"] == [
            {"default": True, "mediaType": "application/json"},  # represents the generic JSON complex properties
        ]
        assert desc["inputs"]["featureCollectionInput"]["formats"] == [
            {"default": True, "mediaType": "application/gml+xml; version=3.2"},
            {"default": False, "mediaType": "application/vnd.google-earth.kml+xml",
             "schema": "https://schemas.opengis.net/kml/2.3/ogckml23.xsd"},
            {"default": False, "mediaType": "application/json",
             "schema": "https://geojson.org/schema/FeatureCollection.json"}  # $ref in allOf => schema
        ]

    def test_deploy_process_io_no_format_default(self):
        """
        Validate resolution of ``default`` format field during deployment.

        Omitted ``default`` field in formats during deployment must only add them later on during process description.

        .. versionchanged:: 4.11
            Previously, ``default: False`` would be added automatically *during deployment parsing*
            (from :mod:`colander` deserialization) when omitted in the submitted payload.
            This caused comparison between submitted ``inputs`` and ``outputs`` against their parsed counterparts
            to differ, failing deployment. Newer versions do not add the missing ``default`` during deployment, but
            adds them as needed for following *process description parsing*, as they are then required in the schema.

        .. seealso::
            :func:`tests.test_schemas.test_format_variations`
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": {"file": {"type": "File"}},
            "outputs": {"file": {"type": "File"}}
        }
        body = {
            "processDescription": {
                "id": self._testMethodName,
                "inputs": {
                    "file": {
                        "formats": [
                            # no explicit defaults for any entry
                            {"mediaType": ContentType.APP_JSON},  # first should resolve as default
                            {"mediaType": ContentType.TEXT_PLAIN}
                        ]
                    }
                },
                "outputs": {
                    "file": {
                        "formats": [
                            # explicit defaults are respected
                            {"mediaType": ContentType.IMAGE_PNG, "default": False},
                            {"mediaType": ContentType.IMAGE_JPEG, "default": True},  # must respect even if not first
                            # and can be mixed with omitted that must resolve as non default
                            {"mediaType": ContentType.IMAGE_GEOTIFF},
                        ]
                    }
                }
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OGC)

        # add fields that are generated inline by the process description
        expect_inputs = body["processDescription"]["inputs"]  # type: JSON
        expect_outputs = body["processDescription"]["outputs"]  # type: JSON
        expect_inputs["file"].update({"title": "file", "minOccurs": 1, "maxOccurs": 1})
        expect_inputs["file"]["formats"][0]["default"] = True
        expect_inputs["file"]["formats"][1]["default"] = False
        expect_inputs["file"]["schema"] = {
            "oneOf": [
                {"type": "string", "contentMediaType": ContentType.APP_JSON},
                {"type": "string", "contentMediaType": ContentType.TEXT_PLAIN},
                {"type": "object", "additionalProperties": True},  # auto added from JSON detection
            ]
        }
        expect_outputs["file"].update({"title": "file"})  # no min/max occurs for outputs
        expect_outputs["file"]["formats"][0]["default"] = False
        expect_outputs["file"]["formats"][1]["default"] = True
        expect_outputs["file"]["formats"][2]["default"] = False
        expect_outputs["file"]["schema"] = {
            "oneOf": [
                {"type": "string", "format": "binary",
                 "contentMediaType": ContentType.IMAGE_PNG, "contentEncoding": "base64"},
                {"type": "string", "format": "binary",
                 "contentMediaType": ContentType.IMAGE_JPEG, "contentEncoding": "base64"},
                {"type": "string", "format": "binary",
                 "contentMediaType": ContentType.IMAGE_GEOTIFF, "contentEncoding": "base64"},
            ]
        }

        assert desc["inputs"] == expect_inputs
        assert desc["outputs"] == expect_outputs

    def test_deploy_merge_literal_io_from_package(self):
        """
        Test validates that literal I/O definitions *only* defined in the `CWL` package as `JSON` within the deployment
        body generates expected `WPS` process description I/O with corresponding formats and values.
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
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        proc = desc["process"]  # type: ProcessOfferingListing

        assert proc["id"] == self._testMethodName
        assert proc["title"] == "some title"
        assert proc["description"] == "this is a test"
        assert isinstance(proc["inputs"], list)
        assert len(proc["inputs"]) == 1
        assert proc["inputs"][0]["id"] == "url"
        assert proc["inputs"][0]["minOccurs"] == 1
        assert proc["inputs"][0]["maxOccurs"] == 1
        assert "format" not in proc["inputs"][0]
        assert isinstance(proc["outputs"], list)
        assert len(proc["outputs"]) == 1
        assert proc["outputs"][0]["id"] == "values"
        assert "minOccurs" not in proc["outputs"][0]
        assert "maxOccurs" not in proc["outputs"][0]
        assert "format" not in proc["outputs"][0]
        expect = KNOWN_PROCESS_DESCRIPTION_FIELDS
        fields = set(proc.keys()) - expect
        assert len(fields) == 0, f"Unexpected fields found:\n  Unknown: {fields}\n  Expected: {expect}"
        # make sure that deserialization of literal fields did not produce over-verbose metadata
        for p_input in proc["inputs"]:
            expect = KNOWN_PROCESS_DESCRIPTION_INPUT_DATA_FIELDS
            fields = set(p_input) - expect
            assert len(fields) == 0, f"Unexpected fields found:\n  Unknown: {fields}\n  Expected: {expect}"
        for p_output in proc["outputs"]:
            expect = KNOWN_PROCESS_DESCRIPTION_OUTPUT_DATA_FIELDS
            fields = set(p_output) - expect
            assert len(fields) == 0, f"Unexpected fields found:\n  Unknown: {fields}\n  Expected: {expect}"

    def test_deploy_merge_literal_io_from_package_and_offering(self):
        """
        Test validates that literal I/O definitions simultaneously defined in *both* (but not necessarily for each one
        and exhaustively) `CWL` and `WPS` payloads are correctly resolved. More specifically, verifies that:

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
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        proc = desc["process"]  # type: ProcessOfferingListing

        assert proc["id"] == self._testMethodName
        assert proc["title"] == "some title"
        assert proc["description"] == "this is a test"
        assert isinstance(proc["inputs"], list)
        assert len(proc["inputs"]) == 2
        assert proc["inputs"][0]["id"] == "literal_input_only_cwl_minimal"
        assert proc["inputs"][0]["minOccurs"] == 1
        assert proc["inputs"][0]["maxOccurs"] == 1
        assert proc["inputs"][1]["id"] == "literal_input_both_cwl_and_wps"
        assert proc["inputs"][1]["minOccurs"] == 1
        assert proc["inputs"][1]["maxOccurs"] == 1
        assert proc["inputs"][1]["title"] == "Extra detail for I/O both in CWL and WPS", \
            "Additional details defined only in WPS matching CWL I/O by ID should be preserved"
        assert isinstance(proc["outputs"], list)
        assert len(proc["outputs"]) == 2
        assert proc["outputs"][0]["id"] == "literal_output_only_cwl_minimal"
        assert proc["outputs"][1]["id"] == "literal_output_both_cwl_and_wps"
        assert proc["outputs"][1]["title"] == "Additional detail only within WPS output", \
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

        desc = self.describe_process(self._testMethodName, describe_schema=ProcessSchema.OGC)
        assert desc["id"] == self._testMethodName
        assert desc["title"] == "some title"
        assert desc["description"] == "this is a test"
        assert isinstance(desc["inputs"], dict)
        assert len(desc["inputs"]) == 2
        assert desc["inputs"]["literal_input_only_cwl_minimal"]["minOccurs"] == 1
        assert desc["inputs"]["literal_input_only_cwl_minimal"]["maxOccurs"] == 1
        assert desc["inputs"]["literal_input_both_cwl_and_wps"]["minOccurs"] == 1
        assert desc["inputs"]["literal_input_both_cwl_and_wps"]["maxOccurs"] == 1
        assert isinstance(desc["outputs"], dict)
        assert len(desc["outputs"]) == 2
        assert "title" not in desc["outputs"]["literal_output_only_cwl_minimal"], \
            "No additional title provided should make the field to be omitted completely."
        assert desc["outputs"]["literal_output_both_cwl_and_wps"]["title"] == \
            "Additional detail only within WPS output", \
            "Additional details defined only in WPS matching CWL I/O by ID should be preserved."

    def test_deploy_resolve_complex_io_format_directory_input(self):
        """
        Test that directory complex type is resolved from CWL.

        .. versionadded:: 4.27
        """
        body = self.retrieve_payload("DirectoryListingProcess", "deploy", local=True)
        pkg = self.retrieve_payload("DirectoryListingProcess", "package", local=True)
        # remove definitions in deploy body to evaluate auto-resolution from CWL 'type: Directory'
        body["processDescription"].pop("inputs")
        body["executionUnit"] = [{"unit": pkg}]
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        assert desc["inputs"]["input_dir"]["formats"][0]["mediaType"] == ContentType.APP_DIR

    def test_deploy_resolve_complex_io_format_directory_output(self):
        """
        Test that directory complex type is resolved from CWL.

        .. versionadded:: 4.27
        """
        body = self.retrieve_payload("DirectoryMergingProcess", "deploy", local=True)
        pkg = self.retrieve_payload("DirectoryMergingProcess", "package", local=True)
        # remove definitions in deploy body to evaluate auto-resolution from CWL 'type: Directory'
        body["processDescription"].pop("outputs")
        body["executionUnit"] = [{"unit": pkg}]
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        assert desc["outputs"]["output_dir"]["formats"][0]["mediaType"] == ContentType.APP_DIR

    def test_deploy_merge_complex_io_format_references(self):
        """
        Test validates that known `WPS` I/O formats (i.e.: `MIME-type`) considered as valid, but not corresponding to
        any *real* `IANA/EDAM` reference for `CWL` are preserved on the `WPS` side and dropped on `CWL` side to avoid
        validation error.

        We also validate a `MIME-type` that should be found for both `CWL` and `WPS` formats to make sure that `CWL`
        formats are only dropped when necessary.
        """
        ns_json, type_json = get_cwl_file_format(ContentType.APP_JSON, must_exist=True)
        assert "iana" in ns_json  # just to make sure
        # even if IANA media-type does not exist, it must still be well-formed (type/sub-type)
        # otherwise, schema 'MediaType' will raise because of invalid string pattern
        ct_not_exists = "application/x-ogc-dods"    # OpenDAP, still doesn't exist at moment of test creation
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
                                    "mimeType": ContentType.APP_JSON,
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
                                {"mimeType": ContentType.APP_JSON},
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
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        proc = desc["process"]  # type: ProcessOfferingListing

        assert proc["inputs"][0]["id"] == "wps_only_format_exists"
        assert len(proc["inputs"][0]["formats"]) == 1
        assert proc["inputs"][0]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert pkg["inputs"][0]["id"] == "wps_only_format_exists"
        assert pkg["inputs"][0]["type"] == "File"
        # FIXME: back-propagate WPS format to CWL without format specified
        #  (https://github.com/crim-ca/weaver/issues/50)
        # assert pkg["inputs"][0]["format"] == type_json

        assert proc["inputs"][1]["id"] == "wps_only_format_not_exists"
        assert len(proc["inputs"][1]["formats"]) == 1
        assert proc["inputs"][1]["formats"][0]["mediaType"] == ct_not_exists
        assert pkg["inputs"][1]["id"] == "wps_only_format_not_exists"
        assert pkg["inputs"][1]["type"] == "File"
        assert "format" not in pkg["inputs"][1], "Non-existing CWL format reference should have been dropped."

        assert proc["inputs"][2]["id"] == "wps_only_format_both"
        assert len(proc["inputs"][2]["formats"]) == 2
        assert proc["inputs"][2]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["inputs"][2]["formats"][1]["mediaType"] == ct_not_exists
        assert pkg["inputs"][2]["id"] == "wps_only_format_both"
        assert pkg["inputs"][2]["type"] == "File"
        # FIXME: for now we don't even back-propagate, but if we did, must be none because one is unknown reference
        #   (https://github.com/crim-ca/weaver/issues/50)
        assert "format" not in pkg["inputs"][2], "Any non-existing CWL format reference should drop all entries."

        assert proc["inputs"][3]["id"] == "cwl_only_format_exists"
        assert len(proc["inputs"][3]["formats"]) == 1
        assert proc["inputs"][3]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert pkg["inputs"][3]["id"] == "cwl_only_format_exists"
        assert pkg["inputs"][3]["type"] == "File"
        assert pkg["inputs"][3]["format"] == type_json

        desc = self.describe_process(self._testMethodName, describe_schema=ProcessSchema.OGC)
        assert len(desc["inputs"]["wps_only_format_exists"]["formats"]) == 1
        assert desc["inputs"]["wps_only_format_exists"]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert len(desc["inputs"]["wps_only_format_not_exists"]["formats"]) == 1
        assert desc["inputs"]["wps_only_format_not_exists"]["formats"][0]["mediaType"] == ct_not_exists
        assert len(desc["inputs"]["wps_only_format_both"]["formats"]) == 2
        assert desc["inputs"]["wps_only_format_both"]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert desc["inputs"]["wps_only_format_both"]["formats"][1]["mediaType"] == ct_not_exists

    def test_deploy_merge_mediatype_io_format_references(self):
        """
        Test to validate ``mimeType`` is replaced by ``mediaType`` for all descriptions.

        Also, we validate that processes that use ``mimeType`` or ``mediaType`` can be deployed successfully.
        """
        ns_json, type_json = get_cwl_file_format(ContentType.APP_JSON)
        namespaces = dict(list(ns_json.items()))
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                    "inputs": [
                        {
                            "id": "wps_format_mimeType",
                            "formats": [
                                {
                                    "mimeType": ContentType.APP_JSON,
                                    "default": True,
                                }
                            ]
                        },
                        {
                            "id": "wps_format_mediaType",
                            "formats": [
                                {
                                    "mediaType": ContentType.APP_JSON,
                                    "default": True,
                                }
                            ]
                        },
                    ],
                    "outputs": [
                        {
                            "id": "wps_format_mimeType",
                            "formats": [{"mediaType": ContentType.APP_JSON}],
                        },
                        {
                            "id": "wps_format_mediaType",
                            "formats": [{"mediaType": ContentType.APP_JSON}],
                        },
                    ],
                },
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{
                "unit": {
                    "cwlVersion": "v1.0",
                    "class": "CommandLineTool",
                    "inputs": [
                        {
                            "id": "wps_format_mimeType",
                            "type": "File",
                            "format": type_json,
                        },
                        {
                            "id": "wps_format_mediaType",
                            "type": "File",
                            "format": type_json,
                        },
                    ],
                    "outputs": [
                        {
                            "id": "wps_format_mimeType",
                            "type": "File",
                            "format": type_json,
                        },
                        {
                            "id": "wps_format_mediaType",
                            "type": "File",
                            "format": type_json,
                        },
                    ],
                    "$namespaces": namespaces
                }
            }]
        }
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        proc = desc["process"]  # type: ProcessOfferingListing
        assert proc["inputs"][0]["id"] == "wps_format_mimeType"
        assert proc["inputs"][0]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["inputs"][1]["id"] == "wps_format_mediaType"
        assert proc["inputs"][1]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["outputs"][0]["id"] == "wps_format_mimeType"
        assert proc["outputs"][0]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["outputs"][1]["id"] == "wps_format_mediaType"
        assert proc["outputs"][1]["formats"][0]["mediaType"] == ContentType.APP_JSON

        desc = self.describe_process(self._testMethodName, describe_schema=ProcessSchema.OGC)
        assert desc["inputs"]["wps_format_mimeType"]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert desc["inputs"]["wps_format_mediaType"]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert desc["outputs"]["wps_format_mimeType"]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert desc["outputs"]["wps_format_mediaType"]["formats"][0]["mediaType"] == ContentType.APP_JSON

    def test_deploy_cwl_with_secrets(self):
        """
        Ensure that a process deployed with secrets as :term:`CWL` hints remains defined in the result.
        """
        cwl = self.retrieve_payload("EchoSecrets", "package", local=True)
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        _, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        assert "hints" in pkg
        assert pkg["hints"] == {CWL_REQUIREMENT_SECRETS: {"secrets": ["message"]}}

    def test_execute_file_type_io_format_references(self):
        """
        Test to validate :term:`OGC` compliant ``type`` directly provided as ``mediaType`` for execution file reference.
        """
        body = self.retrieve_payload("CatFile", "deploy", local=True)
        body["processDescription"]["process"].update({
            "id": self._testMethodName,
            "inputs": {
                "file": {
                    "formats": [
                        {"mediaType": ContentType.APP_YAML, "default": True},
                        {"mediaType": ContentType.APP_JSON, "default": False}
                    ]
                }
            }
        })
        self.deploy_process(body)
        data = self.retrieve_payload("CatFile", ref_name="Execute_CatFile_ogc_mapping_schema.yml", local=True)
        data.update({
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "outputs": {"output": {"transmissionMode": ExecuteTransmissionMode.VALUE}}
        })
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            stack_exec.enter_context(mocked_wps_output(self.settings))
            out_dir = self.settings["weaver.wps_output_dir"]
            out_url = self.settings["weaver.wps_output_url"]
            tmp_file = stack_exec.enter_context(tempfile.NamedTemporaryFile(mode="w", dir=out_dir, suffix="test.yml"))
            yaml.safe_dump({"test": "test"}, tmp_file)
            tmp_file.flush()
            tmp_file.seek(0)
            tmp_href = tmp_file.name.replace(out_dir, out_url, 1)

            # if 'type' is not properly detected, the input would assume no format is provided
            # in such case, the default YAML format (defined in above deploy) would be used and execution would succeed
            # if it fails, it means 'type' was properly detected as unsupported format for the input and was rejected
            # NOTE:
            #   execution request itself succeeds *submission*, but fails running it
            #   since async exec is mocked, we can check failure with the status directly after
            proc_url = f"/processes/{self._testMethodName}/jobs"
            data["inputs"]["file"] = {"href": tmp_href, "type": ContentType.IMAGE_GEOTIFF}
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=data, headers=self.json_headers, only_local=True)
            assert resp.status_code == 201, resp.text
            status_url = resp.json.get("location")
            self.monitor_job(status_url, expect_failed=True)

            data["inputs"]["file"]["type"] = ContentType.APP_YAML
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=data, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], resp.text
            status_url = resp.json.get("location")
            self.monitor_job(status_url)  # expect successful

    def test_execute_output_file_format_validator(self):
        """
        Test with custom :mod:`pywps` file format extension validator involved in output resolution.
        """
        from weaver.processes.wps_package import format_extension_validator as real_validator

        cwl = self.retrieve_payload("PseudoOutputGenerator", "package", local=True)
        body = {
            "processDescription": {
                "id": self._testMethodName,
                "inputs": {
                    "image_tif": {
                        "formats": [{"mediaType": ContentType.IMAGE_GEOTIFF}]
                    }
                }
            },
            "executionUnit": [{"unit": cwl}],
        }
        self.deploy_process(body)
        data = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": {"data": "0123456789"},
        }
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            stack_exec.enter_context(mocked_wps_output(self.settings))

            mock_validator = stack_exec.enter_context(
                mock.patch("weaver.processes.wps_package.format_extension_validator", side_effect=real_validator)
            )

            proc_url = f"/processes/{self._testMethodName}/execution"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=data, headers=self.json_headers, only_local=True)
            assert resp.status_code == 201, resp.text
            status_url = resp.json.get("location")
            results = self.monitor_job(status_url)  # successful (if validator did not apply correctly, execution fails)

            assert mock_validator.called
            validator_call_types = [call.args[0].data_format.mime_type for call in mock_validator.call_args_list]
            expected_media_types = [
                "image/jp2",
                ContentType.IMAGE_TIFF,
                ContentType.IMAGE_PNG,
                ContentType.TEXT_XML,
            ]
            assert validator_call_types == expected_media_types

            assert len(results) != len(expected_media_types), (
                "some outputs are expected to not be validated by the extension validator"
            )
            assert list(results) == list(cwl["outputs"]), "all outputs should be collected in the results"

    def test_deploy_block_builtin_processes_from_api(self):
        """
        Test to validates if ``builtin`` process type is explicitly blocked during deployment from API.

        .. versionchanged:: 4.2
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": ["python3"],
            "inputs": {
                "stringInput": "string"
            },
            "requirements": {
                CWL_REQUIREMENT_APP_DOCKER: {
                    "dockerPull": "python:3.7-alpine"
                },
            },
            "outputs": [],
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                    "type": ProcessType.BUILTIN,
                },
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            resp = mocked_sub_requests(self.app, "post_json", "/processes", data=body, timeout=5,
                                       headers=self.json_headers, only_local=True, expect_errors=True)
            # With Weaver<=4.1.x, the 'type' was explicitly checked to block it since Deploy payload was kept as is
            # This field was allowed to trickle all they way down to the instantiation of Process object
            # assert resp.status_code == 200

            # With Weaver>4.1.x, the deserialized result from Deploy payload is employed, which drops unknown 'type'
            # Ensure that deploy now succeeds, but the obtained Process is not 'builtin' (just a regular application)
            assert resp.status_code == 201
            assert ProcessType.BUILTIN not in resp.json["processSummary"]["keywords"]
            process = self.process_store.fetch_by_id(self._testMethodName)
            assert process.type == ProcessType.APPLICATION

    @parameterized.expand([
        # not allowed even if combined with another known and valid definition
        ({"UnknownRequirement": {}, CWL_REQUIREMENT_APP_DOCKER: {"dockerPull": "python:3.7-alpine"}}, ),
        ({"UnknownRequirement": {}}, ),
        ({}, ),  # no requirement (i.e.: simple shell script) also invalid
    ])
    def test_deploy_block_unknown_processes(self, requirements):
        # type: (CWL_AnyRequirements) -> None
        """
        Test to validate that any process that cannot be resolved against one of known
        :py:data:`weaver.processes.constants.CWL_REQUIREMENT_APP_TYPES` is explicitly blocked.
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": ["python3"],
            "inputs": {
                "stringInput": "string"
            },
            "requirements": requirements,
            "outputs": [],
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

        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            resp = mocked_sub_requests(self.app, "post_json", "/processes", data=body, timeout=5,
                                       headers=self.json_headers, only_local=True, expect_errors=True)
            assert resp.status_code == 422

    def test_deploy_requirement_inline_javascript(self):
        """
        Test that CWL with ``InlineJavascriptRequirement`` definition is permitted.

        .. versionadded:: 4.27
        """
        body = self.retrieve_payload("DirectoryMergingProcess", "deploy", local=True)
        pkg = self.retrieve_payload("DirectoryMergingProcess", "package", local=True)
        body["executionUnit"] = [{"unit": pkg}]
        assert CWL_REQUIREMENT_INLINE_JAVASCRIPT in pkg["requirements"]
        _, cwl = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        assert CWL_REQUIREMENT_INLINE_JAVASCRIPT in cwl["requirements"]

    def test_deploy_merge_complex_io_with_multiple_formats_and_defaults(self):
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
        ns_json, type_json = get_cwl_file_format(ContentType.APP_JSON)
        ns_text, type_text = get_cwl_file_format(ContentType.TEXT_PLAIN)
        ns_ncdf, type_ncdf = get_cwl_file_format(ContentType.APP_NETCDF)
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
                {
                    "id": "multi_value_single_format",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    "format": type_ncdf,
                },
                {
                    "id": "multi_value_multi_format",
                    "type": {
                        "type": "array",
                        "items": "File",
                    },
                    # NOTE:
                    #   not valid to have array of format for output as per:
                    #   https://github.com/common-workflow-language/common-workflow-language/issues/482
                    #   WPS payload must specify them
                    # "format": [type3, type2, type_json],
                },
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
                                    "mimeType": ContentType.TEXT_PLAIN,
                                    "default": True,
                                }
                            ]
                        },
                        {
                            "id": "multi_value_multi_format_default",
                            "formats": [
                                {
                                    "mimeType": ContentType.APP_NETCDF,
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
                                {"mimeType": ContentType.APP_JSON},
                                {"mimeType": ContentType.TEXT_PLAIN},
                                {"mimeType": ContentType.APP_NETCDF},
                            ]
                        },
                        {
                            "id": "multi_value_multi_format",
                            "formats": [
                                {"mimeType": ContentType.APP_NETCDF},
                                {"mimeType": ContentType.TEXT_PLAIN},
                                {"mimeType": ContentType.APP_JSON},
                            ]
                        }
                    ]
                },
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        proc = desc["process"]  # type: ProcessOfferingListing

        # process description input validation
        assert proc["inputs"][0]["id"] == "single_value_single_format"
        assert proc["inputs"][0]["minOccurs"] == 1
        assert proc["inputs"][0]["maxOccurs"] == 1
        assert len(proc["inputs"][0]["formats"]) == 1
        assert proc["inputs"][0]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["inputs"][0]["formats"][0]["default"] is True  # only format available, auto default
        assert proc["inputs"][1]["id"] == "multi_value_single_format"
        assert proc["inputs"][1]["minOccurs"] == 1
        assert proc["inputs"][1]["maxOccurs"] == "unbounded"
        assert len(proc["inputs"][1]["formats"]) == 1
        assert proc["inputs"][1]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["inputs"][1]["formats"][0]["default"] is True  # only format available, auto default
        assert proc["inputs"][2]["id"] == "single_value_single_format_default"
        assert proc["inputs"][2]["minOccurs"] == 0
        assert proc["inputs"][2]["maxOccurs"] == 1
        assert len(proc["inputs"][2]["formats"]) == 1
        assert proc["inputs"][2]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert proc["inputs"][2]["formats"][0]["default"] is True  # only format available, auto default
        assert proc["inputs"][3]["id"] == "multi_value_single_format_default"
        assert proc["inputs"][3]["minOccurs"] == 0
        assert proc["inputs"][3]["maxOccurs"] == "unbounded"
        assert len(proc["inputs"][3]["formats"]) == 1
        assert proc["inputs"][3]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["inputs"][3]["formats"][0]["default"] is True  # only format available, auto default
        assert proc["inputs"][4]["id"] == "single_value_multi_format"
        assert proc["inputs"][4]["minOccurs"] == 1
        assert proc["inputs"][4]["maxOccurs"] == 1
        assert len(proc["inputs"][4]["formats"]) == 3
        assert proc["inputs"][4]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["inputs"][4]["formats"][0]["default"] is True  # no explicit default, uses first
        assert proc["inputs"][4]["formats"][1]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["inputs"][4]["formats"][1]["default"] is False
        assert proc["inputs"][4]["formats"][2]["mediaType"] == ContentType.APP_NETCDF
        assert proc["inputs"][4]["formats"][2]["default"] is False
        assert proc["inputs"][5]["id"] == "multi_value_multi_format"
        assert proc["inputs"][5]["minOccurs"] == 1
        assert proc["inputs"][5]["maxOccurs"] == "unbounded"
        assert len(proc["inputs"][5]["formats"]) == 3
        assert proc["inputs"][5]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert proc["inputs"][5]["formats"][0]["default"] is False
        assert proc["inputs"][5]["formats"][1]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["inputs"][5]["formats"][1]["default"] is True  # specified in process description
        assert proc["inputs"][5]["formats"][2]["mediaType"] == ContentType.APP_JSON
        assert proc["inputs"][5]["formats"][2]["default"] is False
        assert proc["inputs"][6]["id"] == "single_value_multi_format_default"
        assert proc["inputs"][6]["minOccurs"] == 0
        assert proc["inputs"][6]["maxOccurs"] == 1
        assert len(proc["inputs"][6]["formats"]) == 3
        assert proc["inputs"][6]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["inputs"][6]["formats"][0]["default"] is True  # no explicit default, uses first
        assert proc["inputs"][6]["formats"][1]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["inputs"][6]["formats"][1]["default"] is False
        assert proc["inputs"][6]["formats"][2]["mediaType"] == ContentType.APP_NETCDF
        assert proc["inputs"][6]["formats"][2]["default"] is False
        assert proc["inputs"][7]["id"] == "multi_value_multi_format_default"
        assert proc["inputs"][7]["minOccurs"] == 0
        assert proc["inputs"][7]["maxOccurs"] == "unbounded"
        assert len(proc["inputs"][7]["formats"]) == 3
        assert proc["inputs"][7]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["inputs"][7]["formats"][0]["default"] is False
        assert proc["inputs"][7]["formats"][1]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["inputs"][7]["formats"][1]["default"] is False
        assert proc["inputs"][7]["formats"][2]["mediaType"] == ContentType.APP_NETCDF
        assert proc["inputs"][7]["formats"][2]["default"] is True  # specified in process description

        # process description output validation
        assert isinstance(proc["outputs"], list)
        assert len(proc["outputs"]) == 4
        for output in proc["outputs"]:
            for field in ["minOccurs", "maxOccurs", "default"]:
                assert field not in output
            for format_spec in output["formats"]:
                # FIXME: not breaking for now, but should be fixed eventually (doesn't make sense to have defaults)
                #   https://github.com/crim-ca/weaver/issues/17
                #   https://github.com/crim-ca/weaver/issues/50
                if "default" in format_spec:
                    LOGGER.warning("Output [%s] has 'default' key but shouldn't (non-breaking).", output["id"])
                # assert "default" not in format_spec

        assert proc["outputs"][0]["id"] == "single_value_single_format"
        assert len(proc["outputs"][0]["formats"]) == 1
        assert proc["outputs"][0]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["outputs"][0]["formats"][0]["default"] is True
        assert proc["outputs"][1]["id"] == "single_value_multi_format"
        assert len(proc["outputs"][1]["formats"]) == 3
        assert proc["outputs"][1]["formats"][0]["mediaType"] == ContentType.APP_JSON
        assert proc["outputs"][1]["formats"][1]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["outputs"][1]["formats"][2]["mediaType"] == ContentType.APP_NETCDF
        assert proc["outputs"][1]["formats"][0]["default"] is True   # mandatory
        assert proc["outputs"][1]["formats"][1].get("default", False) is False  # omission is allowed
        assert proc["outputs"][1]["formats"][2].get("default", False) is False  # omission is allowed
        assert proc["outputs"][2]["id"] == "multi_value_single_format"
        assert len(proc["outputs"][2]["formats"]) == 1
        assert proc["outputs"][2]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert proc["outputs"][2]["formats"][0]["default"] is True
        assert proc["outputs"][3]["id"] == "multi_value_multi_format"
        assert len(proc["outputs"][3]["formats"]) == 3
        assert proc["outputs"][3]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert proc["outputs"][3]["formats"][1]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["outputs"][3]["formats"][2]["mediaType"] == ContentType.APP_JSON
        assert proc["outputs"][3]["formats"][0]["default"] is True   # mandatory
        assert proc["outputs"][3]["formats"][1].get("default", False) is False  # omission is allowed
        assert proc["outputs"][3]["formats"][2].get("default", False) is False  # omission is allowed

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
        for output in proc["outputs"]:
            assert "default" not in output
        assert pkg["outputs"][0]["id"] == "single_value_single_format"
        assert pkg["outputs"][0]["type"] == "File"
        assert pkg["outputs"][0]["format"] == type_json
        assert pkg["outputs"][1]["id"] == "single_value_multi_format"
        assert pkg["outputs"][1]["type"] == "File"
        assert "format" not in pkg["outputs"][1], "CWL format array not allowed for outputs."
        assert pkg["outputs"][2]["id"] == "multi_value_single_format"
        assert pkg["outputs"][2]["type"] == {"type": "array", "items": "File"}
        assert pkg["outputs"][2]["format"] == type_ncdf
        assert pkg["outputs"][3]["id"] == "multi_value_multi_format"
        assert pkg["outputs"][3]["type"] == {"type": "array", "items": "File"}
        assert "format" not in pkg["outputs"][3], "CWL format array not allowed for outputs."

    def test_deploy_merge_resolution_io_min_max_occurs(self):
        """
        Test validates that various merging/resolution strategies of I/O definitions are properly applied for
        corresponding ``minOccurs`` and ``maxOccurs`` fields across `CWL` and `WPS` payloads. Also, fields that can help
        infer ``minOccurs`` and ``maxOccurs`` values such as ``default`` and ``type`` are tested.

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

        .. note::
            This test assumes formats/values are valid and can be resolved.
            Validation of formats/values themselves are accomplished in other tests.

        .. seealso::
            - :meth:`test_valid_io_min_max_occurs_as_str_or_int`
            - :meth:`test_invalid_io_min_max_occurs_wrong_format`
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
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        proc = desc["process"]  # type: ProcessOfferingListing

        assert proc["inputs"][0]["id"] == "required_literal"
        assert proc["inputs"][0]["minOccurs"] == 1
        assert proc["inputs"][0]["maxOccurs"] == 1
        assert proc["inputs"][1]["id"] == "required_literal_default"
        assert proc["inputs"][1]["minOccurs"] == 0
        assert proc["inputs"][1]["maxOccurs"] == 1
        assert proc["inputs"][2]["id"] == "optional_literal_shortcut"
        assert proc["inputs"][2]["minOccurs"] == 0
        assert proc["inputs"][2]["maxOccurs"] == 1
        assert proc["inputs"][3]["id"] == "optional_literal_explicit"
        assert proc["inputs"][3]["minOccurs"] == 0
        assert proc["inputs"][3]["maxOccurs"] == 1
        assert proc["inputs"][4]["id"] == "required_array_shortcut"
        assert proc["inputs"][4]["minOccurs"] == 1
        assert proc["inputs"][4]["maxOccurs"] == "unbounded"
        assert proc["inputs"][5]["id"] == "required_array_explicit"
        assert proc["inputs"][5]["minOccurs"] == 1
        assert proc["inputs"][5]["maxOccurs"] == "unbounded"
        assert proc["inputs"][6]["id"] == "optional_array_shortcut"
        assert proc["inputs"][6]["minOccurs"] == 0
        assert proc["inputs"][6]["maxOccurs"] == "unbounded"
        assert proc["inputs"][7]["id"] == "optional_array_explicit"
        assert proc["inputs"][7]["minOccurs"] == 0
        assert proc["inputs"][7]["maxOccurs"] == "unbounded"
        assert proc["inputs"][8]["id"] == "required_literal_min_fixed_by_wps"
        assert proc["inputs"][8]["minOccurs"] == 1
        assert proc["inputs"][8]["maxOccurs"] == 1
        assert proc["inputs"][9]["id"] == "optional_literal_min_fixed_by_wps"
        assert proc["inputs"][9]["minOccurs"] == 0
        assert proc["inputs"][9]["maxOccurs"] == 1
        assert proc["inputs"][10]["id"] == "required_array_min_fixed_by_wps"
        # FIXME: https://github.com/crim-ca/weaver/issues/50
        #   `maxOccurs=1` not updated to `maxOccurs="unbounded"` as it is evaluated as a single value,
        #   but it should be considered an array since `minOccurs>1`
        #   (see: https://github.com/crim-ca/weaver/issues/17)
        assert proc["inputs"][10]["minOccurs"] == 2
        # assert proc["inputs"][10]["maxOccurs"] == "unbounded"
        assert proc["inputs"][11]["id"] == "required_array_min_optional_fixed_by_wps"
        assert proc["inputs"][11]["minOccurs"] == 2
        # assert proc["inputs"][11]["maxOccurs"] == "unbounded"
        assert proc["inputs"][12]["id"] == "required_array_max_fixed_by_wps"
        assert proc["inputs"][12]["minOccurs"] == 1
        assert proc["inputs"][12]["maxOccurs"] == 10
        assert proc["inputs"][13]["id"] == "optional_array_max_fixed_by_wps"
        assert proc["inputs"][13]["minOccurs"] == 0
        assert proc["inputs"][13]["maxOccurs"] == 10

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

    def test_deploy_merge_valid_io_min_max_occurs_as_str_or_int(self):
        """
        Test validates that I/O definitions with ``minOccurs`` and/or ``maxOccurs`` are permitted as both integer and
        string definitions in order to support (1, "1", "unbounded") variations.

        .. seealso::
            - :meth:`test_invalid_io_min_max_occurs_wrong_format`
            - :meth:`test_resolution_io_min_max_occurs`
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "inputs": [
                {"id": "io_min_int_max_int", "type": "string"},
                {"id": "io_min_int_max_str", "type": "string"},
                {"id": "io_min_str_max_int", "type": "string"},
                {"id": "io_min_str_max_str", "type": "string"},
                {"id": "io_min_int_max_unbounded", "type": {"type": "array", "items": "string"}},
                {"id": "io_min_str_max_unbounded", "type": {"type": "array", "items": "string"}},
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
                    {"id": "io_min_int_max_int", "minOccurs": 1, "maxOccurs": 1},
                    {"id": "io_min_int_max_str", "minOccurs": 1, "maxOccurs": "1"},
                    {"id": "io_min_str_max_int", "minOccurs": "1", "maxOccurs": 1},
                    {"id": "io_min_str_max_str", "minOccurs": "1", "maxOccurs": "1"},
                    {"id": "io_min_int_max_unbounded", "minOccurs": 1, "maxOccurs": "unbounded"},
                    {"id": "io_min_str_max_unbounded", "minOccurs": "1", "maxOccurs": "unbounded"},
                ]
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        try:
            desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        except colander.Invalid:
            self.fail("MinOccurs/MaxOccurs values defined as valid int/str should not raise an invalid schema error")

        inputs = body["processDescription"]["inputs"]  # type: List[JSON]
        proc = desc["process"]  # type: ProcessOfferingListing
        assert isinstance(proc["inputs"], list)
        assert len(proc["inputs"]) == len(inputs)
        for i, process_input in enumerate(inputs):
            assert proc["inputs"][i]["id"] == process_input["id"]
            for field in ["minOccurs", "maxOccurs"]:
                proc_in_res = proc["inputs"][i][field]
                proc_in_exp = (
                    int(process_input[field]) if str(process_input[field]).isnumeric() else process_input[field]
                )
                assert proc_in_res == proc_in_exp, (
                    f"Field '{field}' of input '{process_input}'({i}) "
                    f"is expected to be '{proc_in_exp}' but was '{proc_in_res}'"
                )

    def test_deploy_merge_wps_io_as_mappings(self):
        """
        Validate that WPS I/O submitted during deployment as mapping (OGC format) are converted to merge with CWL I/O.
        """

        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            # use different list/map representation in CWL to check that WPS can be merged with any of them
            "inputs": [
                {"id": "input_num", "type": {"type": "array", "items": "float"}},
                {"id": "input_file", "type": "File"},
            ],
            "outputs": {"values": {"type": "string"}, "out_file": {"type": "File"}}
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "inputs": {
                        "input_num": {"title": "Input numbers", "maxOccurs": 20},
                        "input_file": {"title": "Test File", "formats": [{"mediaType": ContentType.APP_ZIP}]},
                    },
                    "outputs": {
                        "values": {"title": "Test Output", "description": "CSV raw values"},
                        "out_file": {"title": "Result File", "formats": [{"mediaType": "text/csv"}]}
                    }
                }
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        proc = desc  # type: ProcessOfferingMapping

        assert isinstance(proc["inputs"], dict)
        assert len(proc["inputs"]) == len(body["processDescription"]["process"]["inputs"])
        assert isinstance(proc["outputs"], dict)
        assert len(proc["outputs"]) == len(body["processDescription"]["process"]["outputs"])

        # following inputs metadata were correctly parsed from WPS mapping entries if defined and not using defaults
        assert proc["inputs"]["input_num"]["title"] == "Input numbers"
        assert proc["inputs"]["input_num"]["maxOccurs"] == 20
        assert proc["inputs"]["input_num"]["literalDataDomains"][0]["dataType"]["name"] == "float"
        assert proc["inputs"]["input_file"]["title"] == "Test File"
        assert proc["inputs"]["input_file"]["formats"][0]["mediaType"] == ContentType.APP_ZIP
        assert proc["outputs"]["values"]["title"] == "Test Output"
        assert proc["outputs"]["values"]["description"] == "CSV raw values"
        assert proc["outputs"]["values"]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert proc["outputs"]["out_file"]["title"] == "Result File"
        assert proc["outputs"]["out_file"]["formats"][0]["mediaType"] == "text/csv"

    def test_execute_process_revision(self):
        proc = self.fully_qualified_test_name()
        old = "1.0.0"
        rev = "1.1.0"
        cwl = {
            "s:version": old,
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": "echo",
            "inputs": {"message": {"type": "string", "inputBinding": {"position": 1}}},
            "outputs": {"output": {"type": "string", "outputBinding": {"outputEval": "$(inputs.message)"}}}
        }
        body = {
            "processDescription": {"process": {"id": proc}},
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        self.deploy_process(body)

        path = f"/processes/{proc}"
        data = {"version": rev, "title": "updated", "jobControlOptions": [ExecuteControlOption.SYNC]}
        resp = self.app.patch_json(path, params=data, headers=self.json_headers)
        assert resp.status_code == 200

        exec_value = "test"
        exec_body = {
            # because it is updated above to be sync-only,
            # using async below MUST fail with correctly resolved newer revision
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": [{"id": "message", "value": exec_value}],
            "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}]
        }

        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)

            # test the newer revision with async, failure expected
            path = f"/processes/{proc}:{rev}/execution"
            resp = mocked_sub_requests(
                self.app, "post_json", path,
                data=exec_body, headers=self.json_headers,
                timeout=5, only_local=True, expect_errors=True
            )
            assert resp.status_code == 422, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"

            # use the older revision which allowed async, validating that the right process version is invoked
            path = f"/processes/{proc}:{old}/execution"
            resp = mocked_sub_requests(
                self.app, "post_json", path,
                data=exec_body, headers=self.json_headers,
                timeout=5, only_local=True, expect_errors=True
            )
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            status_url = resp.headers.get("Location")
            assert f"{proc}:{old}" in status_url
            job_id = resp.json.get("jobID")
            job = self.job_store.fetch_by_id(job_id)
            assert job.process == f"{proc}:{old}"
            data = self.get_outputs(status_url, schema=JobInputsOutputsSchema.OGC)
            assert data["outputs"]["output"]["value"] == exec_value

            # counter-validate the assumption with the latest revision using permitted sync
            # use the explicit version to be sure
            exec_body["mode"] = ExecuteMode.SYNC
            path = f"/processes/{proc}:{rev}/execution"
            resp = mocked_sub_requests(
                self.app, "post_json", path,
                data=exec_body, headers=self.json_headers,
                timeout=5, only_local=True, expect_errors=True
            )
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            results_url = resp.headers.get("Content-Location")  # because sync returns directly, no 'Location' header
            assert f"{proc}:{rev}" in results_url
            job_id = results_url.split("/results", 1)[0].rsplit("/", 1)[-1]
            job = self.job_store.fetch_by_id(job_id)
            assert job.process == f"{proc}:{rev}"
            assert resp.json["output"] == exec_value

    def test_execute_job_with_accept_languages(self):
        """
        Test that different accept language matching supported languages all successfully execute and apply them.

        Invalid accept languages must be correctly reported as not supported.
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": "echo",
            "inputs": {"message": {"type": "string", "inputBinding": {"position": 1}}},
            "outputs": {"output": {"type": "File", "outputBinding": {"glob": "stdout.log"}}}
        }
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        self.deploy_process(body)
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": [{"id": "message", "value": "test"}],
            "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}]
        }
        headers = dict(self.json_headers)

        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            proc_url = f"/processes/{self._testMethodName}/jobs"

            # combinations of (test, expect)
            # where 'expect' can be success/fail or explicit language expected on success
            partial_matches = [("fr-CH", "fr")]  # 'fr' only is offered, so it can be matched as smaller subset
            quality_matches = [("de-CH;q=1, de;q=0.5, en;q=0.1", "en")]  # match english even if at the lowest quality
            valid_languages = [(lang, True) for lang in AcceptLanguage.values()]
            wrong_languages = [(lang, False) for lang in ["ru", "it", "zh", "es", "es-MX"]]
            for lang, accept in valid_languages + wrong_languages + partial_matches + quality_matches:
                if isinstance(accept, str):
                    result_lang = accept
                    accept = True
                else:
                    result_lang = lang
                headers["Accept-Language"] = lang
                resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5, expect_errors=not accept,
                                           data=exec_body, headers=headers, only_local=True)
                code = resp.status_code
                if accept:  # must execute until completion with success
                    assert code in [200, 201], f"Failed with: [{code}]\nReason:\n{resp.json}"
                    status_url = resp.json.get("location")
                    try:
                        self.monitor_job(status_url, timeout=5, return_status=True)  # wait until success
                    except AssertionError as exc:
                        raise AssertionError(f"Failed execution for Accept-Language: [{lang}]") from exc
                    job_id = resp.json.get("jobID")
                    job = self.job_store.fetch_by_id(job_id)
                    assert job.accept_language == result_lang
                else:
                    # job not even created
                    assert code == 406, f"Error code should indicate not acceptable header for: [{lang}]"
                    detail = resp.json.get("detail")
                    assert "language" in detail and lang in detail, (
                        "Expected error description to indicate bad language"
                    )

    @mocked_aws_config
    @mocked_aws_s3
    @mocked_http_file
    def test_execute_job_with_array_input(self):
        """
        The test validates job can receive an array as input and process it as expected.
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": ["python3", "script.py"],
            "inputs":
            {
                "test_int_array": {"type": {"type": "array", "items": "int"}, "inputBinding": {"position": 1}},
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
                CWL_REQUIREMENT_APP_DOCKER: {
                    "dockerPull": "python:3.7-alpine"
                },
                CWL_REQUIREMENT_INIT_WORKDIR: {
                    "listing": [
                        {
                            "entryname": "script.py",
                            "entry": inspect.cleandoc("""
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
                                                    with open (path_, mode="r", encoding="utf-8") as file_:
                                                        file_data = file_.read()
                                                return file_data.upper()
                                            value = map(tmp, value)
                                        input[key] = ";".join(map(str, value))
                                    elif isinstance(value, dict):
                                        path_ = value.get('path')
                                        if path_ and os.path.exists(path_):
                                            with open (path_, mode="r", encoding="utf-8") as file_:
                                                file_data = file_.read()
                                            input[key] = file_data.upper()
                                    elif isinstance(value, str):
                                        input[key] = value.upper()
                                    elif isinstance(value, bool):
                                        input[key] = not value
                                    elif isinstance(value, int):
                                        input[key] = value+1
                                    elif isinstance(value, float):
                                        input[key] = value+0.5
                                json.dump(input, open("./tmp.txt","w"))
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
            desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        except colander.Invalid:
            self.fail("Test")

        assert desc is not None

        test_bucket_ref = mocked_aws_s3_bucket_test_file(
            "wps-process-test-bucket",
            "input_file_s3.txt",
            "This is a generated file for s3 test"
        )

        test_http_ref = mocked_reference_test_file(
            "input_file_http.txt",
            "http",
            "This is a generated file for http test",
            MOCK_HTTP_REF  # hosted under mock endpoint to avoid missing location when fetching file
        )

        test_file_ref = mocked_reference_test_file(
            "input_file_ref.txt",
            "file",
            "This is a generated file for file test"
        )

        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs":
            [
                {"id": "test_int_array", "value": [10, 20, 30, 40, 50]},
                {"id": "test_float_array", "value": [10.03, 20.03, 30.03, 40.03, 50.03]},
                {"id": "test_string_array", "value": ["this", "is", "a", "test"]},
                {"id": "test_reference_array",
                    "value": [
                        {"href": test_file_ref},
                        {"href": test_http_ref},
                        {"href": test_bucket_ref}
                    ]
                 },
                {"id": "test_int_value", "value": 2923},
                {"id": "test_float_value", "value": 389.73},
                {"id": "test_string_value", "value": "string_test"},
                {"id": "test_reference_http_value", "href": test_http_ref},
                {"id": "test_reference_file_value", "href": test_file_ref},
                {"id": "test_reference_s3_value", "href": test_bucket_ref}
            ],
            "outputs": [
                {"id": "output_test", "type": "File"},
            ]
        }

        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            proc_url = f"/processes/{self._testMethodName}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            status_url = resp.json.get("location")

        results = self.monitor_job(status_url)

        job_output_path = results.get("output_test")["href"].split(self.settings["weaver.wps_output_path"])[-1]
        wps_out = self.settings["weaver.wps_output_dir"]
        tmp_file = f"{wps_out}/{job_output_path}"

        try:
            with open(tmp_file, mode="r", encoding="utf-8") as out_file:
                processed_values = json.load(out_file)
        except FileNotFoundError:
            self.fail(f"Output file [{tmp_file}] was not found where it was expected to resume test")
        except Exception as exception:
            self.fail(f"An error occurred during the reading of the file: {exception}")
        assert processed_values["test_int_array"] == "11;21;31;41;51"
        assert processed_values["test_float_array"] == "10.53;20.53;30.53;40.53;50.53"
        assert processed_values["test_string_array"] == "THIS;IS;A;TEST"
        assert processed_values["test_reference_array"] == ("THIS IS A GENERATED FILE FOR FILE TEST;"
                                                            "THIS IS A GENERATED FILE FOR HTTP TEST;"
                                                            "THIS IS A GENERATED FILE FOR S3 TEST")
        assert processed_values["test_int_value"] == 2924
        assert processed_values["test_float_value"] == 390.23
        assert processed_values["test_string_value"] == "STRING_TEST"
        assert processed_values["test_reference_s3_value"] == "THIS IS A GENERATED FILE FOR S3 TEST"
        assert processed_values["test_reference_http_value"] == "THIS IS A GENERATED FILE FOR HTTP TEST"
        assert processed_values["test_reference_file_value"] == "THIS IS A GENERATED FILE FOR FILE TEST"

    def test_execute_job_with_inline_input_values(self):
        """
        Validates that the job can receive an object and array types inputs and process them as expected.
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": ["python3", "script.py"],
            "inputs": {
                "stringInput": "string",
                "integerInput": "int",
                "doubleInput": "float",
                "stringArrayInput": {"type": {"type": "array", "items": "string"}},
                "integerArrayInput": {"type": {"type": "array", "items": "int"}},
                "floatArrayInput": {"type": {"type": "array", "items": "float"}},
                "measureStringInput": "string",
                "measureIntegerInput": "int",
                "measureFloatInput": "float",
                "measureFileInput": "File"
            },
            "requirements": {
                CWL_REQUIREMENT_APP_DOCKER: {
                    "dockerPull": "python:3.7-alpine"
                },
                CWL_REQUIREMENT_INIT_WORKDIR: {
                    "listing": [
                        {
                            "entryname": "script.py",
                            "entry": inspect.cleandoc("""
                                import json
                                import os
                                import ast
                                input = $(inputs)
                                try:
                                    for key, value in input.items():
                                        if isinstance(value, dict):
                                            path_ = value.get("path")
                                            if path_ and os.path.exists(path_):
                                                with open (path_, mode="r", encoding="utf-8") as file_:
                                                    file_data = file_.read()
                                                input[key] = ast.literal_eval(file_data.upper())
                                    json.dump(input, open("./tmp.txt", "w"))
                                except Exception as exc:
                                    print(exc)
                                    raise
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
            desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        except colander.Invalid:
            self.fail("Test")

        assert desc["process"] is not None

        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            tmp_file = stack_exec.enter_context(tempfile.NamedTemporaryFile(mode="w", suffix=".json"))  # noqa
            tmp_file.write(json.dumps({"value": {"ref": 1, "measurement": 10.3, "uom": "m"}}))
            tmp_file.seek(0)

            exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": {
                    "stringInput": "string_test",
                    "integerInput": 10,
                    "doubleInput": 3.14159,
                    "stringArrayInput": ["1", "2", "3", "4", "5", "6"],
                    "integerArrayInput": [1, 2, 3, 4, 5, 6],
                    "floatArrayInput": [1.45, 2.65, 3.5322, 4.86, 5.57, 6.02],
                    "measureStringInput": {
                        "value": "this is a test"
                    },
                    "measureIntegerInput": {
                        "value": 45
                    },
                    "measureFloatInput": {
                        "value": 10.2
                    },
                    "measureFileInput": {
                        "href": f"file://{tmp_file.name}"
                    }
                },
                "outputs": [
                    {"id": "output_test", "type": "File"},
                ]
            }

            proc_url = f"/processes/{self._testMethodName}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            status_url = resp.json.get("location")

        results = self.monitor_job(status_url)

        job_output_path = results.get("output_test")["href"].split(self.settings["weaver.wps_output_path"])[-1]
        wps_out = self.settings["weaver.wps_output_dir"]
        tmp_file = f"{wps_out}/{job_output_path}"

        try:
            with open(tmp_file, mode="r", encoding="utf-8") as f:
                processed_values = json.load(f)
        except FileNotFoundError:
            self.fail(f"Output file [{tmp_file}] was not found where it was expected to resume test")
        except Exception as exception:
            self.fail(f"An error occurred during the reading of the file: {exception}")
        assert processed_values["stringInput"] == "string_test"
        assert processed_values["integerInput"] == 10
        assert processed_values["doubleInput"] == 3.14159
        assert processed_values["stringArrayInput"] == ["1", "2", "3", "4", "5", "6"]
        assert processed_values["integerArrayInput"] == [1, 2, 3, 4, 5, 6]
        assert processed_values["floatArrayInput"] == [1.45, 2.65, 3.5322, 4.86, 5.57, 6.02]
        assert processed_values["measureStringInput"] == "this is a test"
        assert processed_values["measureIntegerInput"] == 45
        assert processed_values["measureFloatInput"] == 10.2
        assert processed_values["measureFileInput"] == {"VALUE": {"REF": 1, "MEASUREMENT": 10.3, "UOM": "M"}}

    def test_execute_job_with_bbox(self):
        body = self.retrieve_payload("EchoBoundingBox", "deploy", local=True)
        proc = self.fully_qualified_test_name(self._testMethodName)
        self.deploy_process(body, describe_schema=ProcessSchema.OGC, process_id=proc)

        data = self.retrieve_payload("EchoBoundingBox", "execute", local=True)
        bbox = data["bboxInput"]
        assert bbox["crs"] == "http://www.opengis.net/def/crs/OGC/1.3/CRS84", (
            "Input BBOX expects an explicit CRS reference URI. "
            "This is used to validate interpretation of CRS by WPS data type handlers."
        )
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": data,
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"

            status_url = resp.json["location"]
            results = self.monitor_job(status_url)

        # note: following CRS format is not valid unless nested under 'value' (ie: schema allows it as "object" value)
        expect_bbox = {"bbox": bbox["bbox"], "crs": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        assert results
        assert "bboxOutput" in results
        assert results["bboxOutput"] == expect_bbox, (
            "Expected the BBOX CRS URI to be interpreted and validated by known WPS definitions."
        )

    def test_execute_job_with_collection_input_geojson_feature_collection(self):
        name = "EchoFeatures"
        body = self.retrieve_payload(name, "deploy", local=True)
        proc = self.fully_qualified_test_name(self._testMethodName)
        self.deploy_process(body, describe_schema=ProcessSchema.OGC, process_id=proc)

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match collection prefix hostnames
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())  # pylint: disable=R1732
            stack.enter_context(mocked_file_server(tmp_dir, tmp_host, settings=self.settings, mock_browse_index=True))

            exec_body_val = self.retrieve_payload(name, "execute", local=True)
            col_file = os.path.join(tmp_dir, "test.json")
            col_feats = exec_body_val["inputs"]["features"]["value"]  # type: JSON
            with open(col_file, mode="w", encoding="utf-8") as tmp_feature_collection_geojson:
                json.dump(col_feats, tmp_feature_collection_geojson)

            col_exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": {
                    "features": {
                        # accessed directly as a static GeoJSON FeatureCollection
                        "collection": "https://mocked-file-server.com/test.json",
                        "format": ExecuteCollectionFormat.GEOJSON,
                        "schema": "http://www.opengis.net/def/glossary/term/FeatureCollection",
                    },
                }
            }

            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc}/execution"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=col_exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"

            status_url = resp.json["location"]
            results = self.monitor_job(status_url)
            assert "features" in results

        job_id = status_url.rsplit("/", 1)[-1]
        wps_dir = get_wps_output_dir(self.settings)
        job_dir = os.path.join(wps_dir, job_id)
        job_out = os.path.join(job_dir, "features", "features.geojson")
        assert os.path.isfile(job_out), f"Invalid output file not found: [{job_out}]"
        with open(job_out, mode="r", encoding="utf-8") as out_fd:
            out_data = json.load(out_fd)
        assert out_data["features"] == col_feats["features"]

    @parameterized.expand([
        # note: the following are not *actually* filtering, but just validating formats are respected across code paths
        ("POST", "cql2-json", {"op": "=", "args": [{"property": "name"}, "test"]}),
        ("GET", "cql2-text", "property.name = 'test'"),
    ])
    def test_execute_job_with_collection_input_ogc_features(self, filter_method, filter_lang, filter_value):
        name = "EchoFeatures"
        body = self.retrieve_payload(name, "deploy", local=True)
        proc = self.fully_qualified_test_name(self._testMethodName)
        self.deploy_process(body, describe_schema=ProcessSchema.OGC, process_id=proc)

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match collection prefix hostnames
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())  # pylint: disable=R1732
            tmp_svr = stack.enter_context(
                mocked_file_server(tmp_dir, tmp_host, settings=self.settings, mock_browse_index=True)
            )
            exec_body_val = self.retrieve_payload(name, "execute", local=True)
            col_feats = exec_body_val["inputs"]["features"]["value"]  # type: JSON
            if filter_method == "GET":
                filter_match = responses.matchers.query_param_matcher({
                    "filter": filter_value,
                    "filter-lang": filter_lang,
                })
            else:
                filter_match = responses.matchers.json_params_matcher(filter_value)
            tmp_svr.add(filter_method, f"{tmp_host}/collections/test/items", json=col_feats, match=[filter_match])

            col_exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": {
                    "features": {
                        "collection": f"{tmp_host}/collections/test",
                        "format": ExecuteCollectionFormat.OGC_FEATURES,
                        "type": ContentType.APP_GEOJSON,
                        "filter-lang": filter_lang,
                        "filter": filter_value,
                    }
                }
            }

            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc}/execution"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=col_exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"

            status_url = resp.json["location"]
            results = self.monitor_job(status_url)
            assert "features" in results

        job_id = status_url.rsplit("/", 1)[-1]
        wps_dir = get_wps_output_dir(self.settings)
        job_dir = os.path.join(wps_dir, job_id)
        job_out = os.path.join(job_dir, "features", "features.geojson")
        assert os.path.isfile(job_out), f"Invalid output file not found: [{job_out}]"
        with open(job_out, mode="r", encoding="utf-8") as out_fd:
            out_data = json.load(out_fd)
        assert out_data["features"] == col_feats["features"]

    @pytest.mark.oap_part3
    def test_execute_job_with_collection_input_stac_items(self):
        """
        Validate parsing and handling of ``collection`` specified in an input with :term:`STAC` :term:`API` endpoint.

        Ensures that ``format: stac-items`` can be used to return the Items directly rather than matched Assets
        by corresponding :term:`Media-Type`.

        .. versionadded:: 6.0
            Fix resolution of STAC ItemSearch endpoint.
        """
        name = "EchoFeatures"
        body = self.retrieve_payload(name, "deploy", local=True)
        proc = self.fully_qualified_test_name(self._testMethodName)
        self.deploy_process(body, describe_schema=ProcessSchema.OGC, process_id=proc)

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match collection prefix hostnames
            tmp_svr = stack.enter_context(
                responses.RequestsMock(assert_all_requests_are_fired=False)
            )
            exec_body_val = self.retrieve_payload(name, "execute", local=True)
            col_feats = exec_body_val["inputs"]["features"]["value"]  # type: JSON

            # patch the original content to make it respect STAC validation
            col_id = "test"
            stac_feats_url = f"{tmp_host}/collections/{col_id}/items"
            for idx, feat in enumerate(col_feats["features"]):
                feat.update({
                    "stac_version": "1.0.0",
                    "stac_extensions": [],
                    "collection": col_id,
                    "id": f"{col_id}-{idx}",
                    "properties": {
                        "datetime": "2024-01-01T00:00:00Z",
                    },
                    "assets": {},
                    "links": [{"rel": "self", "href": f"{stac_feats_url}/{col_id}-{idx}"}]
                })

            filter_lang = "cql2-json"
            filter_value = {"op": "=", "args": [{"property": "name"}, "test"]}
            search_datetime = "2024-01-01T00:00:00Z/2024-01-02T00:00:00Z"
            search_body = {
                "collections": [col_id],
                "datetime": search_datetime,
                "filter": filter_value,
                "filter-lang": filter_lang,
            }
            search_match = responses.matchers.json_params_matcher(search_body)
            tmp_svr.add("POST", f"{tmp_host}/search", json=col_feats, match=[search_match])

            stac_item_body = col_feats["features"][0]
            stac_item_id = stac_item_body["id"]
            stac_item_url = f"{stac_feats_url}/{stac_item_id}"
            tmp_svr.add("HEAD", stac_item_url, json=stac_item_body)
            tmp_svr.add("GET", stac_item_url, json=stac_item_body)

            col_exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": {
                    "features": {
                        "collection": f"{tmp_host}/collections/{col_id}",
                        "format": ExecuteCollectionFormat.STAC_ITEMS,  # NOTE: this is the test!
                        "type": ContentType.APP_GEOJSON,
                        "datetime": search_datetime,
                        "filter-lang": filter_lang,
                        "filter": filter_value,
                    }
                }
            }

            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc}/execution"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=col_exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"

            status_url = resp.json["location"]
            results = self.monitor_job(status_url)
            assert "features" in results

        job_id = status_url.rsplit("/", 1)[-1]
        wps_dir = get_wps_output_dir(self.settings)
        job_dir = os.path.join(wps_dir, job_id)
        job_out = os.path.join(job_dir, "features", "features.geojson")
        assert os.path.isfile(job_out), f"Invalid output file not found: [{job_out}]"
        with open(job_out, mode="r", encoding="utf-8") as out_fd:
            out_data = json.load(out_fd)

        assert "features" in out_data and isinstance(out_data["features"], list)
        assert len(out_data["features"]) == 1

    @parameterized.expand([
        (
            {"subset": "Lat(10:20),Lon(30:40)", "datetime": "2025-01-01/2025-01-02"},
            "?subset=Lat(10:20),Lon(30:40)&datetime=2025-01-01/2025-01-02",
        ),
        (
            {"subset": {"Lat": [10, 20], "Lon": [30, 40]}, "datetime": ["2025-01-01", "2025-01-02"]},
            "?subset=Lat(10:20),Lon(30:40)&datetime=2025-01-01/2025-01-02",
        ),
    ])
    def test_execute_job_with_collection_input_coverages_netcdf(self, coverage_parameters, coverage_request):
        # type: (JSON, str) -> None
        proc_name = "DockerNetCDF2Text"
        body = self.retrieve_payload(proc_name, "deploy", local=True)
        cwl = self.retrieve_payload(proc_name, "package", local=True)
        body["executionUnit"] = [{"unit": cwl}]
        proc_id = self.fully_qualified_test_name(self._testMethodName)
        self.deploy_process(body, describe_schema=ProcessSchema.OGC, process_id=proc_id)

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match collection prefix hostnames
            tmp_svr = stack.enter_context(responses.RequestsMock(assert_all_requests_are_fired=False))
            test_file = "test.nc"
            test_data = stack.enter_context(open(os.path.join(TEST_DATA_ROOT, test_file), mode="rb")).read()

            # coverage request expected with resolved query parameters matching submitted collection input parameters
            col_url = f"{tmp_host}/collections/climate-data"
            col_cov_url = f"{col_url}/coverage"
            col_cov_req = f"{col_cov_url}{coverage_request}"
            tmp_svr.add("GET", col_cov_req, body=test_data)

            col_exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": {
                    "input_nc": {
                        "collection": col_url,
                        "format": ExecuteCollectionFormat.OGC_COVERAGE,  # NOTE: this is the test!
                        "type": ContentType.APP_NETCDF,  # must align with process input media-type
                        **coverage_parameters,
                    }
                }
            }

            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=col_exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"

            status_url = resp.json["location"]
            results = self.monitor_job(status_url)
            assert "output_txt" in results

        job_id = status_url.rsplit("/", 1)[-1]
        log_url = f"{status_url}/logs"
        log_txt = self.app.get(log_url, headers={"Accept": ContentType.TEXT_PLAIN}).text
        cov_col = "coverage.nc"  # file name applied by 'collection_processor' (resolved by 'format' + 'type' extension)
        cov_out = "coverage.txt"  # extension modified by invoked process from input file name, literal copy of NetCDF
        assert cov_col in log_txt, "Resolved NetCDF file from collection handler should have been logged."
        assert cov_out in log_txt, "Chained NetCDF copied by the process as text should have been logged."

        wps_dir = get_wps_output_dir(self.settings)
        job_dir = os.path.join(wps_dir, job_id)
        job_out = os.path.join(job_dir, "output_txt", cov_out)
        assert os.path.isfile(job_out), f"Invalid output file not found: [{job_out}]"
        with open(job_out, mode="rb") as out_fd:  # output, although ".txt" is actually a copy of the submitted NetCDF
            out_data = out_fd.read(3)
        assert out_data == b"CDF", "Output file from (collection + process) chain should contain the NetCDF header."

        for file_path in [
            os.path.join(job_dir, cov_col),
            os.path.join(job_dir, "inputs", cov_col),
            os.path.join(job_dir, "output_txt", cov_col),
            os.path.join(job_out, cov_col),
            os.path.join(job_out, "inputs", cov_col),
            os.path.join(job_out, "output_txt", cov_col),
        ]:
            assert not os.path.exists(file_path), (
                f"Intermediate collection coverage file should not exist: [{file_path}]"
            )

    def test_execute_job_with_context_output_dir(self):
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": "echo",
            "inputs": {"message": {"type": "string", "inputBinding": {"position": 1}}},
            "outputs": {"output": {"type": "File", "outputBinding": {"glob": "stdout.log"}}}
        }
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        self.deploy_process(body)
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": [{"id": "message", "value": "test"}],
            "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.REFERENCE}]
        }
        headers = dict(self.json_headers)

        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            proc_url = f"/processes/{self._testMethodName}/jobs"

            wps_context_dirs = [None, "", "test", "sub/test"]
            for ctx in wps_context_dirs:
                if ctx is not None:
                    headers["x-wps-output-context"] = ctx
                resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                           data=exec_body, headers=headers, only_local=True)
                code = resp.status_code
                assert code in [200, 201], f"Failed with: [{code}]\nReason:\n{resp.json}"
                status_url = resp.json.get("location")
                job_id = resp.json["jobID"]
                results = self.monitor_job(status_url, timeout=5)
                wps_dir = self.settings["weaver.wps_output_dir"]
                ctx_dir = f"{wps_dir}/{ctx}" if ctx else wps_dir
                out_url = self.settings["weaver.wps_output_url"]
                ctx_url = f"{out_url}/{ctx}" if ctx else out_url
                res_url = f"{ctx_url}/{job_id}/output/stdout.log"
                res_path = os.path.join(ctx_dir, job_id, "output", "stdout.log")
                assert results["output"]["href"] == res_url, f"Invalid output URL with context: {ctx}"
                assert os.path.isfile(res_path), f"Invalid output path with context: {ctx}"

    def test_execute_job_with_custom_file_name(self):
        """
        Verify that remote HTTP files providing valid ``Content-Disposition`` header will be fetched with ``filename``.

        .. versionadded:: 4.4
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": "echo",
            "inputs": {"input_file": {"type": "File", "inputBinding": {"position": 1}}},
            "outputs": {"output": {"type": "File", "outputBinding": {"glob": "stdout.log"}}}
        }
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        self.deploy_process(body)
        headers = dict(self.json_headers)

        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            tmp_dir = stack_exec.enter_context(tempfile.TemporaryDirectory())
            tmp_file = stack_exec.enter_context(
                # NOTE:
                #   It is important here that the base directory is NOT the WPS output dir.
                #   Otherwise, mapping functions when executing the process will automatically resolve the file
                #   as if "already available" and won't trigger HTTP download that is required for this test.
                tempfile.NamedTemporaryFile(dir=tmp_dir, prefix="", suffix=".txt")
            )
            tmp_name_target = "custom-filename-desired.txt"
            tmp_name_random = os.path.split(tmp_file.name)[-1]
            tmp_path = mocked_reference_test_file(tmp_file.name, "", "random data")
            tmp_http = map_wps_output_location(tmp_path, self.settings, url=True, exists=True)
            assert tmp_http is None, "Failed setup of test file. Must not be available on WPS output location."
            tmp_host = "https://random-file-server.com"
            tmp_http = f"{tmp_host}/{tmp_name_random}"
            headers.update({"Content-Disposition": f"filename=\"{tmp_name_target}\""})
            stack_exec.enter_context(mocked_file_server(tmp_dir, tmp_host, self.settings, headers_override=headers))

            proc_url = f"/processes/{self._testMethodName}/jobs"
            exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": [{"id": "input_file", "href": tmp_http}],
                "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}]
            }
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=headers, only_local=True)
            code = resp.status_code
            assert code in [200, 201], f"Failed with: [{code}]\nReason:\n{resp.json}"
            status_url = resp.json.get("location")
            job_id = resp.json["jobID"]
            self.monitor_job(status_url, timeout=5)
            wps_dir = get_wps_output_dir(self.settings)
            job_dir = os.path.join(wps_dir, job_id)
            job_out = os.path.join(job_dir, "output", "stdout.log")
            assert os.path.isfile(job_out), f"Invalid output file not found: [{job_out}]"
            with open(job_out, mode="r", encoding="utf-8") as out_fd:
                out_data = out_fd.read()
            assert tmp_name_target in out_data and tmp_name_random not in out_data, (
                "Expected input file fetched and staged with Content-Disposition preferred filename "
                "to be printed into the output log file. Expected name was not found.\n"
                f"Expected: [{tmp_name_target}]\n"
                f"Original: [{tmp_name_random}]"
            )

    def test_execute_with_browsable_directory(self):
        """
        Test that HTML browsable directory-like structure retrieves children files recursively for the process.

        .. versionadded:: 4.27
        """
        proc = "DirectoryListingProcess"
        body = self.retrieve_payload(proc, "deploy", local=True)
        pkg = self.retrieve_payload(proc, "package", local=True)
        body["executionUnit"] = [{"unit": pkg}]
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        assert desc["inputs"]["input_dir"]["formats"][0]["mediaType"] == ContentType.APP_DIR

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match in 'Execute_WorkflowSelectCopyNestedOutDir.json'
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            stack.enter_context(mocked_file_server(tmp_dir, tmp_host, settings=self.settings, mock_browse_index=True))
            test_http_dir = f"{tmp_host}/dir/"
            test_http_dir_files = [
                "dir/file.txt",
                "dir/sub/file.txt",
                "dir/sub/nested/file.txt",
                "other/file.txt",
                "root.file.txt"
            ]
            for file in test_http_dir_files:
                path = os.path.join(tmp_dir, file)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, mode="w", encoding="utf-8") as f:
                    f.write("test data")

            exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": [
                    {"id": "input_dir", "href": test_http_dir},
                ],
                "outputs": [
                    {"id": "output_file", "transmissionMode": ExecuteTransmissionMode.REFERENCE},
                ]
            }
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            status_url = resp.json["location"]

            results = self.monitor_job(status_url)
            assert "output_file" in results
            stack.enter_context(mocked_wps_output(self.settings))
            tmpdir = stack.enter_context(tempfile.TemporaryDirectory())
            output_file = fetch_file(results["output_file"]["href"], tmpdir, settings=self.settings)
            output_data = load_file(output_file, text=True)

            # because files under dir are fetched and mounted in stage dir, random sub-dir from CWL is generated
            # ignore this part of the paths for testing invariant results
            # ignore prefixed file metadata generated by the process listing
            cwl_stage_dir = "/var/lib/cwl/"  # /stg<UUID>/<expected-files>
            output_listing = [file.rsplit(" ")[-1] for file in output_data.split("\n") if file]
            expect_http_files = [file for file in test_http_dir_files if file.startswith("dir/")]
            assert len(output_listing) == len(expect_http_files)
            assert all(file.startswith(cwl_stage_dir) for file in output_listing)
            assert all(any(file.endswith(dir_file) for file in output_listing) for dir_file in expect_http_files)

    @pytest.mark.flaky(retries=2, delay=1)
    def test_execute_with_json_listing_directory(self):
        """
        Test that HTTP returning JSON list of directory contents retrieves children files for the process.

        .. fixme:
        .. todo::
            In some circonstances when running the complete test suite, this test fails sporadically when asserting
            the expected output listing size and paths. Re-running this test by itself validates if this case happened.
            Find a way to make it work seamlessly. Retries sometime works, but it is not guaranteed.

        .. versionadded:: 4.27
        """
        proc = "DirectoryListingProcess"
        body = self.retrieve_payload(proc, "deploy", local=True)
        pkg = self.retrieve_payload(proc, "package", local=True)
        body["executionUnit"] = [{"unit": pkg}]
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        assert desc["inputs"]["input_dir"]["formats"][0]["mediaType"] == ContentType.APP_DIR

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match in 'Execute_WorkflowSelectCopyNestedOutDir.json'
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            stack.enter_context(mocked_file_server(tmp_dir, tmp_host, settings=self.settings, mock_browse_index=True))
            test_http_dir = f"{tmp_host}/dir/"
            expect_http_files = [
                "dir/file.txt",
                "dir/sub/file.txt",
                "dir/sub/nested/file.txt",
                "dir/other/file.txt",
            ]
            for file in expect_http_files:
                path = os.path.join(tmp_dir, file)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, mode="w", encoding="utf-8") as f:
                    f.write("test data")

            # make last reference explicit (full URL) to valide it resolves correct as well
            # other references are relative to the initial URL and should resolve them accordingly
            test_http_dir_files = copy.deepcopy(expect_http_files)
            test_http_dir_files[-1] = test_http_dir + test_http_dir_files[-1]

            exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": [
                    {"id": "input_dir", "href": test_http_dir},
                ],
                "outputs": [
                    {"id": "output_file", "transmissionMode": ExecuteTransmissionMode.REFERENCE},
                ]
            }
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            status_url = resp.json["location"]

            results = self.monitor_job(status_url)
            assert "output_file" in results
            stack.enter_context(mocked_wps_output(self.settings))
            tmpdir = stack.enter_context(tempfile.TemporaryDirectory())
            output_file = fetch_file(results["output_file"]["href"], tmpdir, settings=self.settings)
            output_data = load_file(output_file, text=True)

            # because files under dir are fetched and mounted in stage dir, random sub-dir from CWL is generated
            # ignore this part of the paths for testing invariant results
            # ignore prefixed file metadata generated by the process listing
            cwl_stage_dir = "/var/lib/cwl/"  # /stg<UUID>/<expected-files>
            output_listing = [file.rsplit(" ")[-1] for file in output_data.split("\n") if file]
            assert len(output_listing) == len(expect_http_files), (
                f"Output: {repr_json(output_listing)}\nExpect: {repr_json(expect_http_files)}"
            )
            assert all(file.startswith(cwl_stage_dir) for file in output_listing)
            assert all(any(file.endswith(dir_file) for file in output_listing) for dir_file in expect_http_files)

    @mocked_aws_config
    @mocked_aws_s3
    def test_execute_with_bucket_directory(self):
        """
        Test that directory pointing at a S3 bucket downloads all children files recursively for the process.

        .. versionadded:: 4.27
        """
        proc = "DirectoryListingProcess"
        body = self.retrieve_payload(proc, "deploy", local=True)
        pkg = self.retrieve_payload(proc, "package", local=True)
        body["executionUnit"] = [{"unit": pkg}]
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OGC)
        assert desc["inputs"]["input_dir"]["formats"][0]["mediaType"] == ContentType.APP_DIR

        test_bucket_files = [
            "dir/file.txt",
            "dir/sub/file.txt",
            "dir/sub/nested/file.txt",
            "other/file.txt",
            "root.file.txt"
        ]
        test_bucket_ref = "wps-process-test-bucket"
        for file in test_bucket_files:
            mocked_aws_s3_bucket_test_file(test_bucket_ref, file)
        test_bucket_dir = f"s3://{test_bucket_ref}/dir/"
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": [
                {"id": "input_dir", "href": test_bucket_dir},
            ],
            "outputs": [
                {"id": "output_file", "transmissionMode": ExecuteTransmissionMode.REFERENCE},
            ]
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            status_url = resp.json["location"]

            results = self.monitor_job(status_url)
            assert "output_file" in results
            stack.enter_context(mocked_wps_output(self.settings))
            tmpdir = stack.enter_context(tempfile.TemporaryDirectory())
            output_file = fetch_file(results["output_file"]["href"], tmpdir, settings=self.settings)
            output_data = load_file(output_file, text=True)

            # because files under dir are fetched and mounted in stage dir, random sub-dir from CWL is generated
            # ignore this part of the paths for testing invariant results
            # ignore prefixed file metadata generated by the process listing
            cwl_stage_dir = "/var/lib/cwl/"  # /stg<UUID>/<expected-files>
            output_listing = [file.rsplit(" ")[-1] for file in output_data.split("\n") if file]
            expect_bucket_files = [file for file in test_bucket_files if file.startswith("dir/")]
            assert len(output_listing) == len(expect_bucket_files)
            assert all(file.startswith(cwl_stage_dir) for file in output_listing)
            assert all(any(file.endswith(dir_file) for file in output_listing) for dir_file in expect_bucket_files)

    def test_execute_with_directory_output(self):
        """
        Test that directory complex type is resolved from CWL and produces the expected output files.

        .. versionadded:: 4.27
        """
        proc = "DirectoryMergingProcess"
        body = self.retrieve_payload(proc, "deploy", local=True)
        pkg = self.retrieve_payload(proc, "package", local=True)
        body["executionUnit"] = [{"unit": pkg}]
        self.deploy_process(body, describe_schema=ProcessSchema.OGC)

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match in 'Execute_WorkflowSelectCopyNestedOutDir.json'
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            stack.enter_context(mocked_file_server(tmp_dir, tmp_host, settings=self.settings, mock_browse_index=True))
            input_http_files = [
                # NOTE:
                #   base names must differ to have >1 file in output dir listing because of flat list generated
                #   see the process shell script definition
                "dir/file1.txt",
                "dir/sub/file2.txt",
                "dir/sub/nested/file3.txt",
                "dir/other/file4.txt",
            ]
            for file in input_http_files:
                path = os.path.join(tmp_dir, file)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, mode="w", encoding="utf-8") as f:
                    f.write("test data")

            exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": [
                    {"id": "files", "href": os.path.join(tmp_host, http_file)} for http_file in input_http_files
                ],
                "outputs": [
                    {"id": "output_dir", "transmissionMode": ExecuteTransmissionMode.REFERENCE},
                ]
            }
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            status_url = resp.json["location"]
            job_id = resp.json["jobID"]

            results = self.monitor_job(status_url)
            assert "output_dir" in results
            wps_dir = get_wps_output_dir(self.settings)
            wps_url = get_wps_output_url(self.settings)
            out_dir = os.path.join(wps_dir, job_id, "output_dir")
            out_url = f"{os.path.join(wps_url, job_id, 'output_dir')}/"
            assert results["output_dir"]["href"] == out_url
            assert os.path.isdir(out_dir)
            expect_out_files = {
                # the process itself makes a flat list of input files, this is not a byproduct of dir-type output
                os.path.join(out_dir, os.path.basename(file)) for file in input_http_files
            }
            assert all(os.path.isfile(file) for file in expect_out_files)
            output_dir_files = {os.path.join(root, file) for root, _, files in os.walk(out_dir) for file in files}
            assert output_dir_files == expect_out_files

    @parameterized.expand([
        # all values in MiB / seconds accordingly
        (False, 48, 96, 16, 3, 0.25, 0.25, {}),
        (False, 48, 36, 4, 4, 0.25, 0.25, {CWL_REQUIREMENT_RESOURCE: {"ramMax": 52}}),
        # FIXME: ensure ResourceRequirements are effective (https://github.com/crim-ca/weaver/issues/138)
        # (True, 48, 96, 4, 2, 0.25, 0.25, {CWL_REQUIREMENT_RESOURCE: {"ramMax": 2}}),      # FIXME: hangs forever
        # (True, 48, 96, 4, 2, 0.25, 0.25, {CWL_REQUIREMENT_RESOURCE: {"outdirMax": 2}}),   # FIXME: not failing
        (False, 48, 12, 4, 2, 0.25, 0.25, {CWL_REQUIREMENT_RESOURCE: {"outdirMax": 16}}),
    ])
    def test_execute_with_resource_requirement(self,
                                               expect_fail,             # type: bool
                                               expect_ram_min_mb,       # type: int
                                               expect_size_min_mb,      # type: int
                                               ram_chunks_mb,           # type: int
                                               ram_amount_mb,           # type: int
                                               time_duration_s,         # type: Number
                                               time_interval_s,         # type: Number
                                               resource_requirement,    # type: CWL_RequirementsDict
                                               ):                       # type: (...) -> None
        """
        Test that :data:`CWL_REQUIREMENT_RESOURCE` are considered for :term:`Process` execution.

        .. note::
            This test also conveniently serves for testing how large :term:`Job` logs are handled by the storage.
            Because of the large output produced and captured in the logs, saving them directly to the database
            is not supported. The :term:`Job` should therefore filter problematic entries to the log.
        """
        proc = "SimulateResourceUsage"
        body = self.retrieve_payload(proc, "deploy", local=True)
        pkg = self.retrieve_payload(proc, "package", local=True)
        pkg["requirements"].update(resource_requirement)
        body["executionUnit"] = [{"unit": pkg}]
        self.deploy_process(body, describe_schema=ProcessSchema.OGC)

        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": {
                "ram_chunks": ram_chunks_mb,
                "ram_amount": ram_amount_mb,
                "time_duration": time_duration_s,
                "time_interval": time_interval_s,
            },
            "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.REFERENCE}]
        }
        out_dir = None
        try:
            with contextlib.ExitStack() as stack:
                for mock_exec in mocked_execute_celery():
                    stack.enter_context(mock_exec)
                proc_url = f"/processes/{proc}/jobs"
                resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                           data=exec_body, headers=self.json_headers, only_local=True)
                assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
                status_url = resp.json["location"]
                job_id = resp.json["jobID"]
                wps_dir = get_wps_output_dir(self.settings)
                out_dir = os.path.join(wps_dir, job_id, "output")

                results = self.monitor_job(status_url, expect_failed=expect_fail)
                assert "output" in results
                out_log = os.path.join(out_dir, "stdout.log")
                assert os.path.isfile(out_log)
                assert os.stat(out_log).st_size >= expect_size_min_mb * 2**20
                with open(out_log, mode="r", encoding="utf-8") as out_file:
                    output = (line for line in out_file.readlines() if line[0] != "\0")
                output = list(output)
                assert all(
                    any(f"Allocating {i} x {ram_chunks_mb} MiB" in line for line in output)
                    for i in range(1, ram_amount_mb + 1)
                )

                log_url = f"{status_url}/logs"
                log_resp = mocked_sub_requests(self.app, "get", log_url, timeout=5,
                                               headers=self.json_headers, only_local=True)
                job_logs = log_resp.json
                assert all(
                    any(f"Allocating {i} x {ram_chunks_mb} MiB" in line for line in job_logs)
                    for i in range(1, ram_amount_mb + 1)
                )
                assert all(
                    any(
                        f"<message clipped due to large dimension ({i * ram_chunks_mb:.2f} MiB)>"
                        in line for line in job_logs
                    )
                    for i in range(1, ram_amount_mb + 1)
                )

                stat_url = f"{status_url}/statistics"
                stat_resp = mocked_sub_requests(self.app, "get", stat_url, timeout=5,
                                                headers=self.json_headers, only_local=True)
                job_stats = stat_resp.json
                assert all(
                    job_stats["process"][mem] > expect_ram_min_mb
                    for mem in ["rssBytes", "ussBytes", "vmsBytes"]
                )
        finally:
            if out_dir:
                shutil.rmtree(out_dir, ignore_errors=True)

    # FIXME: create a real async test (threading/multiprocess) to evaluate this correctly
    def test_dismiss_job(self):
        """
        Test that different accept language matching supported languages all successfully execute and apply them.

        Invalid accept languages must be correctly reported as not supported.
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            "baseCommand": "sleep",
            "inputs": {"delay": {"type": "int", "inputBinding": {"position": 1}}},
            "outputs": {"output": {"type": "File", "outputBinding": {"glob": "stdout.log"}}}
        }
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/dockerizedApplication",
            "executionUnit": [{"unit": cwl}],
        }
        self.deploy_process(body)
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": [{"id": "delay", "value": 1}],
            "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}]
        }

        with contextlib.ExitStack() as stack_exec:
            # Because 'mocked_execute_celery' is blocking, we cannot dismiss it until it has already completed
            # without getting into complex multiprocess queue/wait to preserve sub-request mock context of TestApp.
            # Instead, create a full job, and simulate dismissing it midway after the fact to check result.
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            mock_del = stack_exec.enter_context(mocked_dismiss_process())
            path = f"/processes/{self._testMethodName}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            status_url = resp.json.get("location")
            status = self.monitor_job(status_url, return_status=True)
            job_id = status["jobID"]

            # patch the job as if still running but dismissed midway
            job = self.job_store.fetch_by_id(job_id)
            job.logs = job.logs[:len(job.logs)//2]
            job.status = Status.RUNNING
            job.progress = 50
            self.job_store.update_job(job)

            # validate that API reports dismiss instead of failed
            path = f"/jobs/{job_id}"
            resp = self.app.delete(path, headers=self.json_headers)
            assert resp.status_code == 200
            assert resp.json["status"] == Status.DISMISSED
            assert mock_del.control.revoke.called_with(job.task_id, terminate=True)
            assert mock_del.control.revoke.call_count == 1

            # subsequent calls to dismiss should be refused
            path = f"/jobs/{job_id}"
            resp = self.app.delete(path, headers=self.json_headers, expect_errors=True)
            assert resp.status_code == 410
            assert mock_del.control.revoke.call_count == 1  # not called again

    def test_deploy_invalid_io_min_max_occurs_wrong_format(self):
        """
        Test verifies that ``minOccurs`` and/or ``maxOccurs`` definitions other than allowed formats are raised as
        invalid schemas.

        .. seealso::
            - :meth:`test_valid_io_min_max_occurs_as_str_or_int`
            - :meth:`test_resolution_io_min_max_occurs`
        """
        cwl = {
            "cwlVersion": "v1.0",
            "class": "CommandLineTool",
            # "inputs": {},   # updated after
            "outputs": {"values": {"type": "string"}}
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                    # "inputs": {}  # updated after
                },
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }

        # replace by invalid min/max and check that it raises
        cwl["inputs"] = [{"id": "test", "type": {"type": "array", "items": "string"}}]
        body["processDescription"]["process"]["inputs"] = [{"id": "test", "minOccurs": [1], "maxOccurs": 1}]
        resp = mocked_sub_requests(self.app, "post_json", "/processes", data=body, headers=self.json_headers)
        assert resp.status_code == 400, "Invalid input minOccurs schema definition should have been raised"
        assert "DeployMinMaxOccurs" in str(resp.json["cause"])
        assert "Invalid" in resp.json["error"]

        cwl["inputs"] = [{"id": "test", "type": {"type": "array", "items": "string"}}]
        body["processDescription"]["process"]["inputs"][0] = {"id": "test", "minOccurs": 1, "maxOccurs": 3.1416}
        resp = mocked_sub_requests(self.app, "post_json", "/processes", data=body, headers=self.json_headers)
        assert resp.status_code == 400, "Invalid input maxOccurs schema definition should have been raised"
        assert "DeployMinMaxOccurs" in str(resp.json["cause"])
        assert "Invalid" in resp.json["error"]

    def test_deploy_merge_complex_io_from_package(self):
        """
        Test validates that complex I/O definitions *only* defined in the `CWL` package as `JSON` within the deployment
        body generates expected `WPS` process description I/O with corresponding formats and values.
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
        desc, _ = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        proc = desc["process"]  # type: ProcessOfferingListing
        assert proc["id"] == self._testMethodName
        assert proc["title"] == "some title"
        assert proc["description"] == "this is a test"
        assert isinstance(proc["inputs"], list)
        assert len(proc["inputs"]) == 1
        assert proc["inputs"][0]["id"] == "url"
        assert proc["inputs"][0]["minOccurs"] == 1
        assert proc["inputs"][0]["maxOccurs"] == 1
        assert isinstance(proc["inputs"][0]["formats"], list)
        assert len(proc["inputs"][0]["formats"]) == 1
        assert isinstance(proc["inputs"][0]["formats"][0], dict)
        assert proc["inputs"][0]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["inputs"][0]["formats"][0]["default"] is True
        assert isinstance(proc["outputs"], list)
        assert len(proc["outputs"]) == 1
        assert proc["outputs"][0]["id"] == "files"
        assert "minOccurs" not in proc["outputs"][0]
        assert "maxOccurs" not in proc["outputs"][0]
        assert isinstance(proc["outputs"][0]["formats"], list)
        assert len(proc["outputs"][0]["formats"]) == 1
        assert isinstance(proc["outputs"][0]["formats"][0], dict)
        assert proc["outputs"][0]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["outputs"][0]["formats"][0]["default"] is True
        expect = KNOWN_PROCESS_DESCRIPTION_FIELDS
        fields = set(proc.keys()) - expect
        assert len(fields) == 0, f"Unexpected fields found:\n  Unknown: {fields}\n  Expected: {expect}"

    def test_deploy_merge_complex_io_from_package_and_offering(self):
        """
        Test validates that complex I/O definitions simultaneously defined in *both* (but not necessarily for each one
        and exhaustively) `CWL` and `WPS` payloads are correctly resolved. More specifically, verifies that:

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
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        proc = desc["process"]  # type: ProcessOfferingListing

        assert proc["id"] == self._testMethodName
        assert proc["title"] == "some title"
        assert proc["description"] == "this is a test"
        assert isinstance(proc["inputs"], list)
        assert len(proc["inputs"]) == 2
        assert proc["inputs"][0]["id"] == "complex_input_only_cwl_minimal"
        assert proc["inputs"][0]["minOccurs"] == 1
        assert proc["inputs"][0]["maxOccurs"] == 1
        assert len(proc["inputs"][0]["formats"]) == 1, \
            "Default format should be added to process definition when omitted from both CWL and WPS"
        assert proc["inputs"][0]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["inputs"][0]["formats"][0]["default"] is True
        assert proc["inputs"][1]["id"] == "complex_input_both_cwl_and_wps"
        assert proc["inputs"][1]["minOccurs"] == 1
        assert proc["inputs"][1]["maxOccurs"] == 1
        assert len(proc["inputs"][1]["formats"]) == 1, \
            "Default format should be added to process definition when omitted from both CWL and WPS"
        assert proc["inputs"][1]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["inputs"][1]["formats"][0]["default"] is True
        assert proc["inputs"][1]["title"] == "Extra detail for I/O both in CWL and WPS", \
            "Additional details defined only in WPS matching CWL I/O by ID should be preserved"
        assert isinstance(proc["outputs"], list)
        assert len(proc["outputs"]) == 2
        assert proc["outputs"][0]["id"] == "complex_output_only_cwl_minimal"
        assert len(proc["outputs"][0]["formats"]) == 1, \
            "Default format should be added to process definition when omitted from both CWL and WPS"
        assert proc["outputs"][0]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["outputs"][0]["formats"][0]["default"] is True
        assert proc["outputs"][1]["id"] == "complex_output_both_cwl_and_wps"
        assert len(proc["outputs"][1]["formats"]) == 1, \
            "Default format should be added to process definition when omitted from both CWL and WPS"
        assert proc["outputs"][1]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN
        assert proc["outputs"][1]["formats"][0]["default"] is True
        assert proc["outputs"][1]["title"] == "Additional detail only within WPS output", \
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

    def test_deploy_literal_and_complex_io_from_wps_xml_reference(self):
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "executionUnit": [{"href": f"mock://{resources.WPS_LITERAL_COMPLEX_IO_XML}"}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication"
        }
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OLD, mock_requests_only_local=False)

        # basic contents validation
        assert "cwlVersion" in pkg
        assert "process" in desc
        proc = desc["process"]  # type: ProcessOfferingListing
        assert proc["id"] == self._testMethodName

        # package I/O validation
        assert "inputs" in pkg
        assert len(pkg["inputs"]) == 2
        assert isinstance(pkg["inputs"], list)
        assert pkg["inputs"][0]["id"] == "tasmax"
        assert "default" not in pkg["inputs"][0]
        assert pkg["inputs"][0]["format"] == OGC_NETCDF
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
        assert pkg["outputs"][0]["format"] == OGC_NETCDF
        assert pkg["outputs"][0]["type"] == "File"
        # NOTE:
        #   not using "glob: <output-id>/*.<ext>" anymore in **generated** CWL for remote WPS
        #   the package definition will consider the outputs as if generated relatively
        #   to the URL endpoint where the process runs
        #   it is only during *Workflow Steps* (when each result is staged locally) that output ID dir nesting
        #   is applied to resolve potential conflict/over-matching of files by globs is applied for local file-system.
        assert pkg["outputs"][0]["outputBinding"]["glob"] == "*.nc"  # output_netcdf/*.nc
        assert pkg["outputs"][1]["id"] == "output_log"
        assert "default" not in pkg["outputs"][1]
        assert pkg["outputs"][1]["format"] == EDAM_PLAIN
        assert pkg["outputs"][1]["type"] == "File"
        assert pkg["outputs"][1]["outputBinding"]["glob"] == "*.*"  # "output_log/*.*"

        # process description I/O validation
        assert len(proc["inputs"]) == 2
        assert proc["inputs"][0]["id"] == "tasmax"
        assert proc["inputs"][0]["title"] == "Resource"
        assert "abstract" not in proc["inputs"][0], "Field 'abstract' should be replaced by 'description'."
        assert proc["inputs"][0]["description"] == "NetCDF Files or archive (tar/zip) containing netCDF files."
        assert proc["inputs"][0]["minOccurs"] == 1
        assert proc["inputs"][0]["maxOccurs"] == 1000
        assert len(proc["inputs"][0]["formats"]) == 1
        assert proc["inputs"][0]["formats"][0]["default"] is True
        assert proc["inputs"][0]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert proc["inputs"][0]["formats"][0]["encoding"] == "base64"
        assert proc["inputs"][1]["id"] == "freq"
        assert proc["inputs"][1]["title"] == "Frequency"
        assert "abstract" not in proc["inputs"][1], "Field 'abstract' should be replaced by 'description'."
        assert proc["inputs"][1]["description"] == "Resampling frequency"
        assert proc["inputs"][1]["minOccurs"] == 0
        assert proc["inputs"][1]["maxOccurs"] == 1
        assert "formats" not in proc["inputs"][1]
        assert len(proc["outputs"]) == 2
        assert proc["outputs"][0]["id"] == "output_netcdf"
        assert proc["outputs"][0]["title"] == "Function output in netCDF"
        assert "abstract" not in proc["outputs"][0], "Field 'abstract' should be replaced by 'description'."
        assert proc["outputs"][0]["description"] == "The indicator values computed on the original input grid."
        assert "minOccurs" not in proc["outputs"][0]
        assert "maxOccurs" not in proc["outputs"][0]
        assert len(proc["outputs"][0]["formats"]) == 1
        assert proc["outputs"][0]["formats"][0]["default"] is True
        assert proc["outputs"][0]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert proc["outputs"][0]["formats"][0]["encoding"] == "base64"
        assert proc["outputs"][1]["id"] == "output_log"
        assert proc["outputs"][1]["title"] == "Logging information"
        assert "abstract" not in proc["inputs"][1], "Field 'abstract' should be replaced by 'description'."
        assert proc["outputs"][1]["description"] == "Collected logs during process run."
        assert "minOccurs" not in proc["outputs"][1]
        assert "maxOccurs" not in proc["outputs"][1]
        assert len(proc["outputs"][1]["formats"]) == 1
        assert proc["outputs"][1]["formats"][0]["default"] is True
        assert proc["outputs"][1]["formats"][0]["mediaType"] == ContentType.TEXT_PLAIN

    def test_deploy_enum_array_and_multi_format_inputs_from_wps_xml_reference(self):
        body = {
            "processDescription": {"process": {"id": self._testMethodName}},
            "executionUnit": [{"href": f"mock://{resources.WPS_ENUM_ARRAY_IO_XML}"}],
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication"
        }
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OLD, mock_requests_only_local=False)

        # basic contents validation
        assert "cwlVersion" in pkg
        assert "process" in desc
        proc = desc["process"]  # type: ProcessOfferingListing
        assert proc["id"] == self._testMethodName

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
        assert len(pkg["inputs"][0]["type"]) == 3, "default value (null) + single type + array type of same base"
        assert pkg["inputs"][0]["type"][0] == "null", "XML defaultValue should result in 'null' as valid unspecified"
        assert "default" in pkg["inputs"][0]
        assert pkg["inputs"][0]["default"] == "DEU", "CWL default value should match extracted defaultValue from XML"
        assert isinstance(pkg["inputs"][0]["type"][1], dict), "enum base type expected since allowed values"
        assert pkg["inputs"][0]["type"][1]["type"] == "enum"
        assert isinstance(pkg["inputs"][0]["type"][1]["symbols"], list)
        assert len(pkg["inputs"][0]["type"][1]["symbols"]) == 220
        assert all(isinstance(s, str) for s in pkg["inputs"][0]["type"][1]["symbols"])
        # array type of same enum allowed values
        assert pkg["inputs"][0]["type"][2]["type"] == "array"
        assert pkg["inputs"][0]["type"][2]["items"]["type"] == "enum"
        assert isinstance(pkg["inputs"][0]["type"][2]["items"]["symbols"], list)
        assert len(pkg["inputs"][0]["type"][2]["items"]["symbols"]) == 220
        assert all(isinstance(s, str) for s in pkg["inputs"][0]["type"][2]["items"]["symbols"])
        # second input
        assert pkg["inputs"][1]["id"] == "mosaic"
        # note: modified by https://github.com/crim-ca/weaver/pull/344
        #   explicit 'null' should not be reported as 'default', causing CWL error seeing as string with "null" value
        #   must be in 'type' instead to define it as optional, as tested below
        # assert pkg["inputs"][1]["default"] == "null"
        assert "null" not in pkg["inputs"][1]
        assert "format" not in pkg["inputs"][1]
        assert isinstance(pkg["inputs"][1]["type"], list), "default 'null' result type formed with it"
        assert len(pkg["inputs"][1]["type"]) == 2
        assert pkg["inputs"][1]["type"][0] == "null", "CWL omitted input expect from minOccurs=0 from WPS input"
        assert pkg["inputs"][1]["type"][1] == "boolean"
        assert pkg["inputs"][2]["id"] == "resource"
        assert "default" not in pkg["inputs"][2], \
            "WPS 'default format media-type' with minOccurs=1 must not result in CWL input with 'default' value"
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
        assert len(proc["inputs"]) == 3
        assert proc["inputs"][0]["id"] == "region"
        assert proc["inputs"][0]["title"] == "Region"
        assert "abstract" not in proc["inputs"][0], "Field 'abstract' should be replaced by 'description'."
        assert proc["inputs"][0]["description"] == "Country code, see ISO-3166-3"
        assert proc["inputs"][0]["minOccurs"] == 0, \
            "Real XML indicates 'minOccurs=1' but also has 'defaultValue', Weaver should correct it."
        assert proc["inputs"][0]["maxOccurs"] == 220
        assert "literalDataDomains" in proc["inputs"][0]
        assert "defaultValue" in proc["inputs"][0]["literalDataDomains"][0]
        assert len(proc["inputs"][0]["literalDataDomains"][0]["valueDefinition"]) == 220, \
            "List of all 220 region abbreviation explicitly provided is expected."
        assert proc["inputs"][0]["literalDataDomains"][0]["defaultValue"] == "DEU"
        assert "formats" not in proc["inputs"][0]
        assert proc["inputs"][1]["id"] == "mosaic"
        assert proc["inputs"][1]["title"] == "Union of multiple regions"
        assert "abstract" not in proc["inputs"][1], "Field 'abstract' should be replaced by 'description'."
        assert proc["inputs"][1]["description"] == \
               "If True, selected regions will be merged into a single geometry."   # noqa
        assert proc["inputs"][1]["minOccurs"] == 0
        assert proc["inputs"][1]["maxOccurs"] == 1
        assert "formats" not in proc["inputs"][1]
        assert proc["inputs"][2]["id"] == "resource"
        assert proc["inputs"][2]["title"] == "Resource"
        assert "abstract" not in proc["inputs"][2], "Field 'abstract' should be replaced by 'description'."
        assert proc["inputs"][2]["description"] == "NetCDF Files or archive (tar/zip) containing NetCDF files."
        assert proc["inputs"][2]["minOccurs"] == 1
        assert proc["inputs"][2]["maxOccurs"] == 1000
        # note: TAR should remain as literal format in the WPS context (not mapped/added as GZIP when resolved for CWL)
        assert len(proc["inputs"][2]["formats"]) == 3
        assert proc["inputs"][2]["formats"][0]["default"] is True
        assert proc["inputs"][2]["formats"][0]["mediaType"] == ContentType.APP_NETCDF
        assert "encoding" not in proc["inputs"][2]["formats"][0]  # none specified, so omitted in response
        assert proc["inputs"][2]["formats"][1]["default"] is False
        assert proc["inputs"][2]["formats"][1]["mediaType"] == ContentType.APP_TAR
        assert "encoding" not in proc["inputs"][2]["formats"][1]  # none specified, so omitted in response
        assert proc["inputs"][2]["formats"][2]["default"] is False
        assert proc["inputs"][2]["formats"][2]["mediaType"] == ContentType.APP_ZIP
        assert "encoding" not in proc["inputs"][2]["formats"][2]  # none specified, so omitted in response

    @pytest.mark.skip(reason="not implemented")
    def test_deploy_multi_outputs_file_from_wps_xml_reference(self):
        """
        Left for documentation purpose only.

        While multi-value output under a same ID is supported by :term:`OGC API - Processes` and :term:`CWL`,
        such definitions are not compliant with :term:`WPS` specification. A server responding with
        a :term:`XML` ``ProcessDescription`` should never indicate a ``maxOccurs!=1`` value, or it would be
        non-compliant and would actually represent undefined behavior. The test cannot be implemented for this reason.

        .. note::
            This does not impact multi-value output support for a :term:`OGC API - Processes` using the :term:`WPS`
            interface. The multi-value output would be represented as an embedded :term:`JSON` array as single value
            encoded with media-type :data:`ContentType.APP_RAW_JSON``. From the point of view of the :term:`WPS`
            definition, the output would not be multi-value to respect the standard. However, there is no **official**
            way to detect this embedded :term:`JSON` as multi-value support directly from the ``ProcessDescription``.
        """
        raise NotImplementedError

    def test_execute_cwl_enum_schema_combined_type_single_array_from_cwl(self):
        """
        Test that validates successful reuse of :term:`CWL` ``Enum`` within a list of types.

        .. code-block:: yaml

            input:
                type:
                    - "null"
                    - type: enum
                      symbols: [A, B, C]
                    - type: array
                      items:
                          type: enum
                          symbols: [A, B, C]

        When the above definition is applied, :mod:`cwltool` and its underlying :mod:`schema_salad` utilities often
        resulted in failed schema validation due to the reused :term:`CWL` ``Enum`` being detected as "*conflicting*"
        by ``name`` auto-generated when parsing the tool definition.

        .. seealso::
            :func:`test_execute_cwl_enum_schema_combined_type_single_array_from_wps`
        """
        proc = "Finch_EnsembleGridPointWetdays"
        body = self.retrieve_payload(proc, "deploy", local=True)
        pkg = self.retrieve_payload(proc, "package", local=True)
        body["executionUnit"] = [{"unit": pkg}]
        body["processDescription"]["process"]["id"] = self._testMethodName
        self.deploy_process(body, describe_schema=ProcessSchema.OGC)

        data = self.retrieve_payload(proc, "execute", local=True)
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": data,
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{self._testMethodName}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"

            status_url = resp.json["location"]
            results = self.monitor_job(status_url)

        assert results

    @mocked_remote_server_requests_wps1([
        resources.TEST_REMOTE_SERVER_URL,
        resources.TEST_REMOTE_SERVER_WPS1_GETCAP_XML,
        {
            "Finch_EnsembleGridPointWetdays": os.path.join(
                resources.FUNCTIONAL_APP_PKG,
                "Finch_EnsembleGridPointWetdays/describe.xml"
            )
        },
    ])
    def test_execute_cwl_enum_schema_combined_type_single_array_from_wps(self, mock_responses):
        # type: (RequestsMock) -> None
        """
        Test that validates successful reuse of :term:`CWL` ``Enum`` within a list of types.

        In this case, the :term:`CWL` ``Enum`` combining single-value reference and array of ``Enum`` should be
        automatically generated from the corresponding :term:`WPS` I/O descriptions.

        .. seealso::
            :func:`test_execute_cwl_enum_schema_combined_type_single_array_from_cwl`
        """
        proc = "Finch_EnsembleGridPointWetdays"
        body = self.retrieve_payload(proc, "deploy", local=True)
        wps = get_path_kvp(
            resources.TEST_REMOTE_SERVER_URL,
            service="WPS",
            request="DescribeProcess",
            identifier=proc,
            version="1.0.0"
        )
        body["executionUnit"] = [{"href": wps}]
        body["processDescription"]["process"]["id"] = self._testMethodName
        self.deploy_process(body, describe_schema=ProcessSchema.OGC)

        data = self.retrieve_payload(proc, "execute", local=True)
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": data,
        }
        status_path = os.path.join(resources.FUNCTIONAL_APP_PKG, "Finch_EnsembleGridPointWetdays/status.xml")
        status_url = f"{resources.TEST_REMOTE_SERVER_URL}/status.xml"
        output_log_url = f"{resources.TEST_REMOTE_SERVER_URL}/result.txt"
        output_zip_url = f"{resources.TEST_REMOTE_SERVER_URL}/output.zip"
        with open(status_path, mode="r", encoding="utf-8") as status_file:
            status_body = status_file.read().format(
                TEST_SERVER_URL=resources.TEST_REMOTE_SERVER_URL,
                PROCESS_ID=proc,
                LOCATION_XML=status_url,
                OUTPUT_FILE_URL=output_zip_url,
                OUTPUT_LOG_FILE_URL=output_log_url,
            )

        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)

            # mock responses expected by "remote" WPS-1 Execute request and relevant documents
            mock_responses.add("POST", resources.TEST_REMOTE_SERVER_URL, body=status_body, headers=self.xml_headers)
            mock_responses.add("GET", status_url, body=status_body, headers=self.xml_headers)
            mock_responses.add("GET", output_log_url, body="log", headers={"Content-Type": ContentType.TEXT_PLAIN})
            mock_responses.add("GET", output_zip_url, body="zip", headers={"Content-Type": ContentType.APP_ZIP})

            proc_url = f"/processes/{self._testMethodName}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"

            status_url = resp.json["location"]
            results = self.monitor_job(status_url)

        assert results


@pytest.mark.functional
class WpsPackageAppTestResultResponses(WpsConfigBase, ResourcesUtil):
    """
    Tests to evaluate the various combinations of results response representations.

    .. seealso::
        - :ref:`proc_exec_results`
        - :ref:`proc_op_job_results`
    """
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = {
            "weaver.wps": True,
            "weaver.wps_path": "/ows/wps",
            "weaver.wps_restapi_path": "/",
            "weaver.wps_output_path": "/wpsoutputs",
            "weaver.wps_output_url": "http://localhost/wpsoutputs",
            "weaver.wps_output_dir": "/tmp/weaver-test/wps-outputs",  # nosec: B108 # don't care hardcoded for test
        }
        super(WpsPackageAppTestResultResponses, cls).setUpClass()

    def setUp(self) -> None:
        self.process_store.clear_processes()

    @staticmethod
    def remove_result_format(results):
        """
        Remove the results ``format`` property to simplify test comparions.

        For backward compatibility, the ``format`` property is inserted in result definitions when represented
        as :term:`JSON`, on top of the :term:`OGC` compliant ``type``, ``mediaType``, etc. of the "format" schema
        for qualified values and link references.
        """
        if not results or not isinstance(results, dict):
            return results
        for result in results.values():
            if isinstance(result, dict):
                result.pop("format", None)
        return results

    @staticmethod
    def remove_result_multipart_variable(results):
        # type: (str) -> str
        """
        Removes any variable headers from the multipart contents to simplify test comparison.
        """
        results = re.sub(r"Date: .*\r\n", "", results)
        results = re.sub(r"Last-Modified: .*\r\n", "", results)
        return results.strip()

    @staticmethod
    def fix_result_multipart_indent(results):
        # type: (str) -> str
        """
        Remove indented whitespace from multipart literal contents.

        This behaves similarly to :func:`inspect.cleandoc`, but handles cases were the nested part contents could
        themselves contain newlines, leading to inconsistent indents for some lines when injected by string formating,
        and causing :func:`inspect.cleandoc` to fail removing any indent.

        Also, automatically applies ``\r\n`` characters correction which are critical in parsing multipart contents.
        This is done to consider that literal newlines will include or not the ``\r`` depending on the OS running tests.

        .. warning::
            This should be used only for literal test string (i.e.: expected value) for comparison against the result.
            Result contents obtained from the response should be compared as-is, without any fix for strict checks.
        """
        if results.startswith("\n "):
            results = results[1:]
        res_dedent = results.lstrip()
        res_indent = len(results) - len(res_dedent)
        res_spaces = " " * res_indent
        res_dedent = res_dedent.replace(f"\n{res_spaces}", "\r\n")  # indented line
        res_dedent = res_dedent.replace("\n\r\n", "\r\n\r\n")  # empty line (header/body separator)
        res_dedent = res_dedent.replace("\r\r", "\r")  # in case windows
        res_dedent = res_dedent.rstrip("\n ")  # last line often indented less because of closing multiline string
        return res_dedent

    @pytest.mark.oap_part1
    def test_execute_single_output_prefer_header_return_representation_literal(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.REPRESENTATION}, respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_data": {}  # no 'transmissionMode' to auto-resolve 'value' from 'return=representation'
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

        job_id = status["jobID"]
        results = self.app.get(f"/jobs/{job_id}/results")
        assert results.content_type.startswith(ContentType.TEXT_PLAIN)
        assert results.text == "test"
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_prefer_header_return_representation_complex(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.REPRESENTATION}, respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {}  # no 'transmissionMode' to auto-resolve 'value' from 'return=representation'
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        assert results.status_code == 200, f"Failed with: [{results.status_code}]\nReason:\n{resp.text}"
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results.text == "{\"data\":\"test\"}"
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_prefer_header_return_minimal_literal_accept_default(self):
        """
        For single requested  output, without ``Accept`` content negotiation, its default format is returned directly.
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.MINIMAL}; wait=5"  # sync to allow direct content response
        exec_headers = {
            "Prefer": prefer_header,
            "Accept": ContentType.ANY,
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_data": {}  # no 'transmissionMode' to auto-resolve 'value' from 'return=minimal'
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"

        results = self.app.get(f"/jobs/{job_id}/results")
        assert results.content_type.startswith(ContentType.TEXT_PLAIN)
        assert results.text == "test"
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_prefer_header_return_minimal_literal_accept_json(self):
        """
        For single requested  output, with ``Accept`` :term:`JSON` content negotiation, document response is returned.
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.MINIMAL}, wait=5"  # sync to allow direct content response
        exec_headers = {
            "Prefer": prefer_header,
            "Accept": ContentType.APP_JSON,
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_data": {}  # no 'transmissionMode' to auto-resolve 'value' from 'return=minimal'
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"

        results = self.app.get(f"/jobs/{job_id}/results")
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results.json == {
            "output_data": "test"
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_prefer_header_return_minimal_complex_accept_default(self):
        """
        For single requested  output, without ``Accept`` content negotiation, its default format is returned by link.

        .. note::
            Because :term:`JSON` ``Accept`` header is **NOT** explicitly requested along the ``Prefer`` header,
            the response is returned by ``Link`` header. This is different from requesting ``Accept`` :term:`JSON`,
            which "forces" ``minimal`` to be mapped to ``document`` response. This is because, for a single output
            combined with ``minimal`` (i.e.: requesting explicitly not to return the contents of the file), a ``Link``
            becomes required. To force the :term:`JSON` contents of the file to be returned directly, ``representation``
            must be requested instead.

        .. seealso::
            - :func:`test_execute_single_output_prefer_header_return_minimal_complex_accept_json`
            - :func:`test_execute_single_output_prefer_header_return_representation_complex`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.MINIMAL}, wait=5"  # sync to allow direct content response
        exec_headers = {
            "Prefer": prefer_header,
            # omitting or specifying 'Accept' any must result the same (default link),
            # but test it is handled explicitly since the header would be "found" when parsing
            "Accept": ContentType.ANY,
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {}  # no 'transmissionMode' to auto-resolve 'reference' from 'return=minimal'
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 204, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"

        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_href = f"{self.url}/processes/{p_id}/jobs/{job_id}/results"
        output_json_href = f"{out_url}/{job_id}/output_json/result.json"
        output_json_link = f"<{output_json_href}>; rel=\"output_json\"; type=\"{ContentType.APP_JSON}\""
        assert results.status_code == 204, "No contents expected for minimal reference result."
        assert results.body == b""
        assert results.content_type is None
        assert results.headers["Content-Location"] == results_href
        assert ("Link", output_json_link) in results.headerlist
        assert not any(
            any(out_id in link[-1] for out_id in ["output_data", "output_text"])
            for link in results.headerlist if link[0] == "Link"
        ), "Filtered outputs should not be found in results response links."
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_prefer_header_return_minimal_complex_accept_json(self):
        """
        For single requested  output, with ``Accept`` :term:`JSON` content negotiation, document response is returned.

        .. note::
            In this test, the selected output just so happens to be :term:`JSON` as well.
            Since it is the ``Accept`` header that is requesting :term:`JSON`, and not a
            combination of ``transmissionMode: value`` with :term:`JSON` ``format``, the
            contents of ``output_json`` file are **NOT** directly returned in the response.

        .. seealso::
            - :func:`test_execute_single_output_prefer_header_return_minimal_complex_accept_default`
              which returns the result by ``Link`` header, which refers to a :term:`JSON` file.
            - :func:`test_execute_single_output_prefer_header_return_representation_complex`
              for case of embedded ``output_json`` file contents in the response using the other ``Prefer`` return.
            - :func:`test_execute_single_output_response_raw_value_complex`
              for case of embedded ``output_json`` file contents in the response,
              using the ``response`` parameter at :term:`Job` execution time, as alternative method to ``Prefer``.
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.MINIMAL}, wait=5"  # sync to allow direct content response
        exec_headers = {
            "Prefer": prefer_header,
            "Accept": ContentType.APP_JSON,
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {}  # no 'transmissionMode' to auto-resolve 'reference' from 'return=minimal'
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        results = self.app.get(f"/jobs/{job_id}/results")
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results.json == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            }
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_response_raw_value_literal(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        exec_headers = {
            "Prefer": "respond-async"
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "response": ExecuteResponse.RAW,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_data": {},  # should use 'transmissionMode: value' by default
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        results = self.app.get(f"/jobs/{job_id}/results")
        assert results.content_type.startswith(ContentType.TEXT_PLAIN)
        assert results.text == "test"
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_response_raw_value_complex(self):
        """
        Since value transmission is requested for a single output, its :term:`JSON` contents are returned directly.

        .. seealso::
            - :func:`test_execute_single_output_prefer_header_return_minimal_complex_accept_json`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = "respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "response": ExecuteResponse.RAW,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {"transmissionMode": ExecuteTransmissionMode.VALUE},
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        out_url = get_wps_output_url(self.settings)
        job_id = status["jobID"]
        results = self.app.get(f"/jobs/{job_id}/results")
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results.json == {"data": "test"}
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_response_raw_reference_literal(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = "respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "response": ExecuteResponse.RAW,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_data": {"transmissionMode": ExecuteTransmissionMode.REFERENCE},
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_href = f"{self.url}/processes/{p_id}/jobs/{job_id}/results"
        output_data_href = f"{out_url}/{job_id}/output_data/output_data.txt"
        output_data_args = f"; rel=\"output_data\"; type=\"{ContentType.TEXT_PLAIN}\""
        output_data_link = f"<{output_data_href}>{output_data_args}"
        assert results.status_code == 204, "No contents expected for minimal reference result."
        assert results.body == b""
        assert results.content_type is None
        assert results.headers["Content-Location"] == results_href
        assert ("Link", output_data_link) in results.headerlist
        assert not any(
            any(out_id in link[-1] for out_id in ["output_json", "output_text"])
            for link in results.headerlist if link[0] == "Link"
        ), "Filtered outputs should not be found in results response links."
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_response_raw_reference_complex(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = "respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "response": ExecuteResponse.RAW,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {},  # should use 'transmissionMode: reference' by default
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_href = f"{self.url}/processes/{p_id}/jobs/{job_id}/results"
        output_json_href = f"{out_url}/{job_id}/output_json/result.json"
        output_json_link = f"<{output_json_href}>; rel=\"output_json\"; type=\"{ContentType.APP_JSON}\""
        assert results.status_code == 204, "No contents expected for single reference result."
        assert results.body == b""
        assert results.content_type is None
        assert results.headers["Content-Location"] == results_href
        assert ("Link", output_json_link) in results.headerlist
        assert not any(
            any(out_id in link[-1] for out_id in ["output_data", "output_text"])
            for link in results.headerlist if link[0] == "Link"
        ), "Filtered outputs should not be found in results response links."
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_multipart_accept_data(self):
        """
        Validate that requesting multipart for a single output is permitted.

        Although somewhat counter-productive to wrap a single output as multipart, this is technically permitted.
        This can be used to "normalize" the response to always be multipart, regardless of the amount outputs
        produced by the process job. The output format should be contained within the part.

        .. seealso::
            - :func:`test_execute_single_output_multipart_accept_link`
            - :func:`test_execute_single_output_multipart_accept_alt_format`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        # NOTE:
        #   no 'response' nor 'Prefer: return' to ensure resolution is done by 'Accept' header
        #   without 'Accept' using multipart, it is expected that JSON document is used
        exec_headers = {
            "Accept": ContentType.MULTIPART_MIXED,
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "mode": ExecuteMode.SYNC,  # WARNING: force sync to make sure JSON job status is not returned instead
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {"transmissionMode": ExecuteTransmissionMode.VALUE}
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" not in resp.headers

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        # validate the results based on original execution request
        results = resp
        assert ContentType.MULTIPART_MIXED in results.content_type
        boundary = parse_kvp(results.headers["Content-Type"])["boundary"][0]
        results_body = self.fix_result_multipart_indent(f"""
            --{boundary}
            Content-Disposition: attachment; name="output_json"; filename="result.json"
            Content-Type: {ContentType.APP_JSON}
            Content-Location: {out_url}/{job_id}/output_json/result.json
            Content-ID: <output_json@{job_id}>
            Content-Length: 15

            {{"data":"test"}}
            --{boundary}--
        """)
        results_text = self.remove_result_multipart_variable(results.text)
        assert results_text == results_body
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_single_output_multipart_accept_link(self):
        """
        Validate that requesting multipart for a single output is permitted.

        Embedded part contains the link instead of the data contents.

        .. seealso::
            - :func:`test_execute_single_output_multipart_accept_data`
            - :func:`test_execute_single_output_multipart_accept_alt_format`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        # NOTE:
        #   no 'response' nor 'Prefer: return' to ensure resolution is done by 'Accept' header
        #   without 'Accept' using multipart, it is expected that JSON document is used
        exec_headers = {
            "Accept": ContentType.MULTIPART_MIXED,
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "mode": ExecuteMode.SYNC,  # WARNING: force sync to make sure JSON job status is not returned instead
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {"transmissionMode": ExecuteTransmissionMode.REFERENCE}
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" not in resp.headers

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        # validate the results based on original execution request
        results = resp
        assert ContentType.MULTIPART_MIXED in results.content_type
        boundary = parse_kvp(results.headers["Content-Type"])["boundary"][0]
        results_body = self.fix_result_multipart_indent(f"""
            --{boundary}
            Content-Disposition: attachment; name="output_json"; filename="result.json"
            Content-Type: {ContentType.APP_JSON}
            Content-Location: {out_url}/{job_id}/output_json/result.json
            Content-ID: <output_json@{job_id}>
            Content-Length: 0

            --{boundary}--
        """)
        results_text = self.remove_result_multipart_variable(results.text)
        assert results_text == results_body
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    # FIXME: implement (https://github.com/crim-ca/weaver/pull/548)
    @pytest.mark.oap_part1
    @pytest.mark.xfail(reason="not implemented")
    def test_execute_single_output_multipart_accept_alt_format(self):
        """
        Validate the returned contents combining an ``Accept`` header as ``multipart`` and a ``format`` in ``outputs``.

        The main contents of the response should be ``multipart``, but the nested contents should be the transformed
        output representation, based on the ``format`` definition.
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        exec_headers = {
            "Accept": ContentType.MULTIPART_MIXED,
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "mode": ExecuteMode.SYNC,  # WARNING: force sync to make sure JSON job status is not returned instead
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {
                    "transmissionMode": ExecuteTransmissionMode.VALUE,  # embed in the part contents
                    "format": {"mediaType": ContentType.APP_YAML},      # request alternate output format
                }
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" not in resp.headers

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        # validate the results based on original execution request
        results = resp
        assert ContentType.MULTIPART_MIXED in results.content_type
        boundary = parse_kvp(results.headers["Content-Type"])["boundary"][0]
        output_json_as_yaml = yaml.safe_dump({"data": "test"})
        results_body = self.fix_result_multipart_indent(f"""
            --{boundary}
            Content-Type: {ContentType.APP_YAML}
            Content-ID: <output_json@{job_id}>
            Content-Length: 12

            {output_json_as_yaml}
            --{boundary}--
        """)
        results_text = self.remove_result_multipart_variable(results.text)
        assert results.content_type.startswith(ContentType.MULTIPART_MIXED)
        assert results_text == results_body
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": "test",
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/output.yml",
                "type": ContentType.APP_YAML,
            },
        }

        # validate the results can be obtained with the "real" representation
        result_json = self.app.get(f"/jobs/{job_id}/results/output_json", headers=self.json_headers)
        assert result_json.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
        assert result_json.content_type == ContentType.APP_JSON
        assert result_json.text == "{\"data\":\"test\"}"

    # FIXME: implement (https://github.com/crim-ca/weaver/pull/548)
    @pytest.mark.oap_part1
    @pytest.mark.xfail(reason="not implemented")
    def test_execute_single_output_response_document_alt_format_yaml(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        exec_headers = {
            "Accept": ContentType.MULTIPART_MIXED,
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "mode": ExecuteMode.SYNC,  # force sync to make sure JSON job status is not returned instead
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {
                    "transmissionMode": ExecuteTransmissionMode.VALUE,  # embed in the part contents
                    "format": {"mediaType": ContentType.APP_YAML},      # request alternate output format
                }
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" not in resp.headers

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        # validate the results based on original execution request
        results = resp
        assert ContentType.MULTIPART_MIXED in results.content_type
        boundary = parse_kvp(results.headers["Content-Type"])["boundary"][0]
        output_json_as_yaml = yaml.safe_dump({"data": "test"})
        results_body = self.fix_result_multipart_indent(f"""
            --{boundary}
            Content-Type: {ContentType.APP_YAML}
            Content-ID: <output_json@{job_id}>
            Content-Length: 12

            {output_json_as_yaml}
            --{boundary}--
        """)
        results_text = self.remove_result_multipart_variable(results.text)
        assert results.content_type.startswith(ContentType.MULTIPART_MIXED)
        assert results_text == results_body
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": "test",
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/output.yml",
                "type": ContentType.APP_YAML,
            },
        }

        # FIXME: implement (https://github.com/crim-ca/weaver/pull/548)
        # validate the results can be obtained with the "real" representation
        result_json = self.app.get(f"/jobs/{job_id}/results/output_json", headers=self.json_headers)
        assert result_json.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
        assert result_json.content_type == ContentType.APP_JSON
        assert result_json.text == "{\"data\":\"test\"}"

    @pytest.mark.oap_part1
    def test_execute_single_output_response_document_alt_format_json_raw_literal(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        exec_headers = {
            "Accept": ContentType.APP_JSON,  # response 'document' should be enough to use JSON, but make extra sure
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "mode": ExecuteMode.SYNC,  # force sync to make sure JSON job status is not returned instead
            "response": ExecuteResponse.DOCUMENT,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {
                    # note:
                    #   Default output format is JSON, but request it as plain text.
                    #   Ensure the JSON response contents does not revert it back to nested JSON.
                    #   Expect a literal string containing the embedded JSON.
                    "transmissionMode": ExecuteTransmissionMode.VALUE,  # force convert of the file reference
                    "format": {"mediaType": ContentType.TEXT_PLAIN},    # force output format explicitly
                }
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" not in resp.headers

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        # validate the results based on original execution request
        results = resp
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results.json == {
            "output_json": {
                "mediaType": ContentType.APP_RAW_JSON,  # ensure special type used to distinguish a literal JSON
                "value": "{\"data\":\"test\"}",
            }
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

        # FIXME: add check of direct request of output (https://github.com/crim-ca/weaver/pull/548)
        # validate the results can be obtained with the "real" representation
        # result_json = self.app.get(f"/jobs/{job_id}/results/output_json", headers=self.json_headers)
        # assert result_json.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
        # assert result_json.content_type == ContentType.APP_JSON
        # assert result_json.json == {"data": "test"}

    @pytest.mark.oap_part1
    def test_execute_single_output_response_document_default_format_json_special(self):
        """
        Validate that a :term:`JSON` output is directly embedded in a ``document`` response also using :term:`JSON`.

        For most types, the data converted from a file reference would be directly embedded as a string
        nested under a ``value`` property and provide the associated ``mediaType``. However, given the
        same :term:`JSON` representation is used for the entire response contents and the nested contents,
        this special case typically expected that the nested :term:`JSON` is not embedded in a string to
        facilitate directly parsing the entire response contents as :term:`JSON`.

        .. seealso::
            - :func:`test_execute_single_output_response_document_alt_format_json`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        exec_headers = {
            "Accept": ContentType.APP_JSON,  # response 'document' should be enough to use JSON, but make extra sure
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "mode": ExecuteMode.SYNC,  # force sync to make sure JSON job status is not returned instead
            "response": ExecuteResponse.DOCUMENT,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {
                    # note:
                    #   Technically, 'format' does not necessarily need to be specified for this case since
                    #   JSON is the default output format for this result, but specify it for clarity
                    #   (see other test cases that ensure non-JSON by default can be converted).
                    "transmissionMode": ExecuteTransmissionMode.VALUE,  # force convert of the file reference
                    "format": {"mediaType": ContentType.APP_JSON},      # request output format explicitly
                }
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" not in resp.headers

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        # validate the results based on original execution request
        results = resp
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results.json == {
            "output_json": {
                "mediaType": ContentType.APP_JSON,
                "value": {"data": "test"},
            }
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @parameterized.expand([
        ContentType.MULTIPART_ANY,
        ContentType.MULTIPART_MIXED,
    ])
    @pytest.mark.oap_part1
    def test_execute_multi_output_multipart_accept(self, multipart_header):
        """
        Requesting ``multipart`` explicitly should return it instead of default :term:`JSON` ``document`` response.

        .. seealso::
            - :func:`test_execute_multi_output_multipart_accept_async_alt_acceptable`
            - :func:`test_execute_multi_output_multipart_accept_async_not_acceptable`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        # NOTE:
        #   No 'response' nor 'Prefer: return' to ensure resolution is done by 'Accept' header
        #   without 'Accept' using multipart, it is expected that JSON document is used
        #   Also, use 'Prefer: wait' to avoid 'respond-async', since async always respond with the Job status.
        prefer_header = "wait=5"
        exec_headers = {
            "Accept": multipart_header,
            "Content-Type": ContentType.APP_JSON,
            "Prefer": prefer_header,
        }
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                # no 'transmissionMode' to auto-resolve 'value' from 'return=representation'
                # request multiple outputs, but not 'all', to test filter behavior at the same time
                # use 1 expected as 'File' and 1 'string' literal to test conversion to raw 'value'
                "output_json": {},
                "output_data": {}
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        results = self.app.get(f"/jobs/{job_id}/results")
        boundary = parse_kvp(results.headers["Content-Type"])["boundary"][0]
        results_body = self.fix_result_multipart_indent(f"""
            --{boundary}
            Content-Disposition: attachment; name="output_data"
            Content-Type: {ContentType.TEXT_PLAIN}
            Content-ID: <output_data@{job_id}>
            Content-Length: 4

            test
            --{boundary}
            Content-Disposition: attachment; name="output_json"; filename="result.json"
            Content-Type: {ContentType.APP_JSON}
            Content-Location: {out_url}/{job_id}/output_json/result.json
            Content-ID: <output_json@{job_id}>
            Content-Length: 0

            --{boundary}--
        """)
        results_text = self.remove_result_multipart_variable(results.text)
        assert results.content_type.startswith(ContentType.MULTIPART_MIXED)
        assert results_text == results_body
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_multi_output_multipart_accept_async_not_acceptable(self):
        """
        When executing the process asynchronously, ``Accept`` with multipart (strictly) is not acceptable.

        Because async requires to respond a Job Status, the ``Accept`` actually refers to that response,
        rather than a results response as returned directly in sync.

        .. seealso::
            - :func:`test_execute_multi_output_multipart_accept`
            - :func:`test_execute_multi_output_multipart_accept_async_alt_acceptable`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        exec_headers = {
            "Accept": ContentType.MULTIPART_MIXED,
            "Content-Type": ContentType.APP_JSON,
            "Prefer": "respond-async",
        }
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {}
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 406, f"Expected error. Instead got: [{resp.status_code}]\nReason:\n{resp.text}"
            assert resp.content_type == ContentType.APP_JSON, "Expect JSON instead of Multipart because of error."
            assert "Accept header" in resp.json["detail"]
            assert resp.json["value"] == ContentType.MULTIPART_MIXED
            assert resp.json["cause"] == {
                "name": "Accept",
                "in": "headers",
            }

    @pytest.mark.oap_part1
    def test_execute_multi_output_multipart_accept_async_alt_acceptable(self):
        """
        When executing the process asynchronously, ``Accept`` with multipart and an alternative is acceptable.

        Because async requires to respond a Job Status, the ``Accept`` actually refers to that response,
        rather than a results response as returned directly in sync.

        .. seealso::
            - :func:`test_execute_multi_output_multipart_accept`
            - :func:`test_execute_multi_output_multipart_accept_async_not_acceptable`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = "respond-async"
        exec_headers = {
            "Accept": f"{ContentType.MULTIPART_MIXED}, {ContentType.APP_JSON}",
            "Content-Type": ContentType.APP_JSON,
            "Prefer": prefer_header,
        }
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {}
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert resp.content_type == ContentType.APP_JSON, "Expect JSON instead of Multipart because of error."
            assert "status" in resp.json, "Expected a JSON Job Status response."
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

    @pytest.mark.oap_part1
    def test_execute_multi_output_prefer_header_return_representation(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.REPRESENTATION}, respond-async"
        exec_headers = {
            "Prefer": prefer_header,
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                # no 'transmissionMode' to auto-resolve 'value' from 'return=representation'
                # request multiple outputs, but not 'all', to test filter behavior at the same time
                # use 1 expected as 'File' and 1 'string' literal to test conversion to raw 'value'
                "output_json": {},
                "output_data": {}
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        boundary = parse_kvp(results.headers["Content-Type"])["boundary"][0]
        results_body = self.fix_result_multipart_indent(f"""
            --{boundary}
            Content-Disposition: attachment; name="output_data"
            Content-Type: {ContentType.TEXT_PLAIN}
            Content-ID: <output_data@{job_id}>
            Content-Length: 4

            test
            --{boundary}
            Content-Disposition: attachment; name="output_json"; filename="result.json"
            Content-Type: {ContentType.APP_JSON}
            Content-Location: {out_url}/{job_id}/output_json/result.json
            Content-ID: <output_json@{job_id}>
            Content-Length: 15

            {{"data":"test"}}
            --{boundary}--
        """)
        results_text = self.remove_result_multipart_variable(results.text)
        assert results.content_type.startswith(ContentType.MULTIPART_MIXED)
        assert results_text == results_body
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_multi_output_response_raw_value(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = "respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "response": ExecuteResponse.RAW,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {"transmissionMode": ExecuteTransmissionMode.VALUE},
                "output_data": {}  # should use 'value' by default
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        boundary = parse_kvp(results.headers["Content-Type"])["boundary"][0]
        results_body = self.fix_result_multipart_indent(f"""
            --{boundary}
            Content-Disposition: attachment; name="output_data"
            Content-Type: {ContentType.TEXT_PLAIN}
            Content-ID: <output_data@{job_id}>
            Content-Length: 4

            test
            --{boundary}
            Content-Disposition: attachment; name="output_json"; filename="result.json"
            Content-Type: {ContentType.APP_JSON}
            Content-Location: {out_url}/{job_id}/output_json/result.json
            Content-ID: <output_json@{job_id}>
            Content-Length: 15

            {{"data":"test"}}
            --{boundary}--
        """)
        results_text = self.remove_result_multipart_variable(results.text)
        assert results.content_type.startswith(ContentType.MULTIPART_MIXED)
        assert results_text == results_body
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_multi_output_response_raw_reference_default_links(self):
        """
        All outputs resolved as reference (explicitly or inferred) with raw representation should be all Link headers.

        The multipart representation of the corresponding request must ask for it explicitly.

        .. seealso::
            - :func:`test_execute_multi_output_response_raw_reference_accept_multipart`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = "respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "response": ExecuteResponse.RAW,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {},  # should use 'reference' by default
                "output_data": {"transmissionMode": ExecuteTransmissionMode.REFERENCE},
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_href = f"{self.url}/processes/{p_id}/jobs/{job_id}/results"
        output_data_href = f"{out_url}/{job_id}/output_data/output_data.txt"
        output_data_link = f"<{output_data_href}>; rel=\"output_data\"; type=\"{ContentType.TEXT_PLAIN}\""
        output_json_href = f"{out_url}/{job_id}/output_json/result.json"
        output_json_link = f"<{output_json_href}>; rel=\"output_json\"; type=\"{ContentType.APP_JSON}\""
        assert results.status_code == 204, "No contents expected for minimal reference result."
        assert results.body == b""
        assert results.content_type is None
        assert results.headers["Content-Location"] == results_href
        assert ("Link", output_data_link) in results.headerlist
        assert ("Link", output_json_link) in results.headerlist
        assert not any(
            any(out_id in link[-1] for out_id in ["output_text"])
            for link in results.headerlist if link[0] == "Link"
        ), "Filtered outputs should not be found in results response links."
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_multi_output_response_raw_reference_accept_multipart(self):
        """
        Requesting ``multipart`` explicitly should return it instead of default ``Link`` headers response.

        .. seealso::
            - :func:`test_execute_multi_output_response_raw_reference_default_links`
            - :func:`test_execute_multi_output_multipart_accept_async_alt_acceptable`
            - :func:`test_execute_multi_output_multipart_accept_async_not_acceptable`
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        # NOTE:
        #   No 'response' nor 'Prefer: return' to ensure resolution is done by 'Accept' header
        #   without 'Accept' using multipart, it is expected that JSON document is used
        #   Also, use 'Prefer: wait' to avoid 'respond-async', since async always respond with the Job status.
        prefer_header = "wait=5"
        exec_headers = {
            "Accept": ContentType.MULTIPART_MIXED,
            "Content-Type": ContentType.APP_JSON,
            "Prefer": prefer_header,
        }
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {},  # should use 'reference' by default
                "output_data": {"transmissionMode": ExecuteTransmissionMode.REFERENCE},
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        results = self.app.get(f"/jobs/{job_id}/results")
        boundary = parse_kvp(results.headers["Content-Type"])["boundary"][0]
        results_body = self.fix_result_multipart_indent(f"""
            --{boundary}
            Content-Disposition: attachment; name="output_data"; filename="output_data.txt"
            Content-Type: {ContentType.TEXT_PLAIN}
            Content-Location: {out_url}/{job_id}/output_data/output_data.txt
            Content-ID: <output_data@{job_id}>
            Content-Length: 0

            --{boundary}
            Content-Disposition: attachment; name="output_json"; filename="result.json"
            Content-Type: {ContentType.APP_JSON}
            Content-Location: {out_url}/{job_id}/output_json/result.json
            Content-ID: <output_json@{job_id}>
            Content-Length: 0

            --{boundary}--
        """)
        results_text = self.remove_result_multipart_variable(results.text)
        assert results.content_type.startswith(ContentType.MULTIPART_MIXED)
        assert results_text == results_body
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_multi_output_response_raw_mixed(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = "respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "response": ExecuteResponse.RAW,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_data": {},  # should use 'value' by default
                "output_text": {},  # should use 'reference' by default
                "output_json": {"transmissionMode": ExecuteTransmissionMode.VALUE},  # force 'value'
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            # request status instead of results since not expecting 'document' JSON in this case
            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        boundary = parse_kvp(results.headers["Content-Type"])["boundary"][0]
        results_body = self.fix_result_multipart_indent(f"""
            --{boundary}
            Content-Disposition: attachment; name="output_data"
            Content-Type: {ContentType.TEXT_PLAIN}
            Content-ID: <output_data@{job_id}>
            Content-Length: 4

            test
            --{boundary}
            Content-Disposition: attachment; name="output_text"; filename="result.txt"
            Content-Type: {ContentType.TEXT_PLAIN}
            Content-Location: {out_url}/{job_id}/output_text/result.txt
            Content-ID: <output_text@{job_id}>
            Content-Length: 0

            --{boundary}
            Content-Disposition: attachment; name="output_json"; filename="result.json"
            Content-Type: {ContentType.APP_JSON}
            Content-Location: {out_url}/{job_id}/output_json/result.json
            Content-ID: <output_json@{job_id}>
            Content-Length: 15

            {{"data":"test"}}
            --{boundary}--
        """)
        results_text = self.remove_result_multipart_variable(results.text)
        assert results.content_type.startswith(ContentType.MULTIPART_MIXED)
        assert results_text == results_body
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_text": {
                "href": f"{out_url}/{job_id}/output_text/result.txt",
                "type": ContentType.TEXT_PLAIN,
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_multi_output_prefer_header_return_minimal_defaults(self):
        """
        Test ``Prefer: return=minimal`` with default ``transmissionMode`` resolutions for literal/complex outputs.
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.MINIMAL}, respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                # no 'transmissionMode' to auto-resolve 'value' based on literal/complex output
                # request multiple outputs, but not 'all', to test filter behavior at the same time
                # use 1 expected as 'File' and 1 'string' literal to test respective auto-resolution on their own
                "output_json": {},
                "output_data": {}
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_json = self.remove_result_format(results.json)
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results_json == {
            "output_data": "test",
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_multi_output_prefer_header_return_minimal_override_transmission(self):
        """
        Test ``Prefer: return=minimal`` with ``transmissionMode`` overrides.

        .. note::
            From a technical standpoint, this response will not really be "minimal" since the values are
            embedded inline. However, this respects the *preference* vs *enforced* property requirements.
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.MINIMAL}, respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                # force inline data for file instead of minimal link reference
                "output_json": {"transmissionMode": ExecuteTransmissionMode.VALUE},
                # force reference creation for literal data instead of minimal contents
                "output_data": {"transmissionMode": ExecuteTransmissionMode.REFERENCE},
                # auto-resolution for this file, to test that 'minimal' still applies with a link reference
                "output_text": {},
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_json = self.remove_result_format(results.json)
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results_json == {
            "output_data": {
                "href": f"{out_url}/{job_id}/output_data/output_data.txt",
                "type": ContentType.TEXT_PLAIN,
            },
            "output_json": {
                "value": {"data": "test"},
                "mediaType": ContentType.APP_JSON,
            },
            "output_text": {
                "href": f"{out_url}/{job_id}/output_text/result.txt",
                "type": ContentType.TEXT_PLAIN,
            },
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
            "output_text": {
                "href": f"{out_url}/{job_id}/output_text/result.txt",
                "type": ContentType.TEXT_PLAIN,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_multi_output_response_document_defaults(self):
        """
        Test ``response: document`` with default ``transmissionMode`` resolutions for literal/complex outputs.
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.MINIMAL}, respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "inputs": {
                "message": "test"
            },
            "outputs": {
                # no 'transmissionMode' to auto-resolve 'value' based on literal/complex output
                # request multiple outputs, but not 'all', to test filter behavior at the same time
                # use 1 expected as 'File' and 1 'string' literal to test respective auto-resolution on their own
                "output_json": {},
                "output_data": {}
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_json = self.remove_result_format(results.json)
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results_json == {
            "output_data": "test",
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part1
    def test_execute_multi_output_response_document_mixed(self):
        """
        Test ``response: document`` with ``transmissionMode`` specified to force convertion of literal/complex outputs.
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = "respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "response": ExecuteResponse.DOCUMENT,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                # force inline data for file instead of minimal link reference
                "output_json": {"transmissionMode": ExecuteTransmissionMode.VALUE},
                # force reference creation for literal data instead of minimal contents
                "output_data": {"transmissionMode": ExecuteTransmissionMode.REFERENCE},
                # auto-resolution for this file, to test that 'minimal' still applies with a link reference
                "output_text": {},
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_json = self.remove_result_format(results.json)
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results_json == {
            "output_data": {
                "href": f"{out_url}/{job_id}/output_data/output_data.txt",
                "type": ContentType.TEXT_PLAIN,
            },
            "output_json": {
                "value": {"data": "test"},
                "mediaType": ContentType.APP_JSON,
            },
            "output_text": {
                "href": f"{out_url}/{job_id}/output_text/result.txt",
                "type": ContentType.TEXT_PLAIN,
            },
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
            "output_text": {
                "href": f"{out_url}/{job_id}/output_text/result.txt",
                "type": ContentType.TEXT_PLAIN,
            },
        }

    def test_execute_mismatch_process(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        # use non-existing process to ensure this particular situation is handled as well
        # a missing process reference must not cause an early "not-found" response
        proc = "random-other-process"
        proc_other = self.fully_qualified_test_name(proc)

        exec_content = {
            "process": f"https://localhost/processes/{proc_other}",
            "inputs": {"message": "test"}
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = f"/processes/{p_id}/execution"  # mismatch on purpose
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=self.json_headers, only_local=True)
            assert resp.status_code == 400, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["cause"] == {"name": "process", "in": "body"}

    @pytest.mark.oap_part4
    def test_execute_jobs_sync(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        exec_headers = {
            "Accept": ContentType.APP_JSON,  # response 'document' should be enough to use JSON, but make extra sure
            "Content-Type": ContentType.APP_JSON,
        }
        exec_content = {
            "process": f"https://localhost/processes/{p_id}",
            "mode": ExecuteMode.SYNC,  # force sync to make sure JSON job status is not returned instead
            "response": ExecuteResponse.DOCUMENT,
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {
                    "transmissionMode": ExecuteTransmissionMode.VALUE,  # force convert of the file reference
                    "format": {"mediaType": ContentType.APP_JSON},      # request output format explicitly
                }
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = "/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" not in resp.headers

        # rely on location that should be provided to find the job ID
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"
        out_url = get_wps_output_url(self.settings)

        # validate the results based on original execution request
        results = resp
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results.json == {
            "output_json": {
                "mediaType": ContentType.APP_JSON,
                "value": {"data": "test"},
            }
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part4
    def test_execute_jobs_async(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.MINIMAL}, respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "process": f"https://localhost/processes/{p_id}",
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {},
                "output_data": {}
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = "/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        job_id = status["jobID"]
        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_json = self.remove_result_format(results.json)
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results_json == {
            "output_data": "test",
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part4
    def test_execute_jobs_create_trigger(self):
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        prefer_header = f"return={ExecuteReturnPreference.MINIMAL}, respond-async"
        exec_headers = {
            "Prefer": prefer_header
        }
        exec_headers.update(self.json_headers)
        exec_content = {
            "process": f"https://localhost/processes/{p_id}",
            "status": "create",  # force wait until triggered
            "inputs": {
                "message": "test"
            },
            "outputs": {
                "output_json": {},
                "output_data": {}
            }
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)

            # create the job, with pending status (not in worker processing queue)
            path = "/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=exec_headers, only_local=True)
            assert resp.status_code == 201, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert "Preference-Applied" in resp.headers
            assert resp.headers["Preference-Applied"] == prefer_header.replace(",", ";")

            status_url = resp.json["location"]
            status = self.monitor_job(status_url, return_status=True, wait_for_status=Status.CREATED)
            assert status["status"] == Status.CREATED

            # trigger the execution (submit the task to worker processing queue)
            job_id = status["jobID"]
            res_path = f"/jobs/{job_id}/results"
            res_headers = {
                "Accept": ContentType.APP_JSON,
            }
            resp = mocked_sub_requests(self.app, "post_json", res_path, timeout=5,
                                       data={}, headers=res_headers, only_local=True)
            assert resp.status_code == 202, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert resp.json["status"] == Status.ACCEPTED

            # retrieve the execution status
            status = self.monitor_job(status_url, return_status=True)
            assert status["status"] == Status.SUCCESSFUL

        out_url = get_wps_output_url(self.settings)
        results = self.app.get(f"/jobs/{job_id}/results")
        results_json = self.remove_result_format(results.json)
        assert results.content_type.startswith(ContentType.APP_JSON)
        assert results_json == {
            "output_data": "test",
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }
        outputs = self.app.get(f"/jobs/{job_id}/outputs", params={"schema": JobInputsOutputsSchema.OGC_STRICT})
        assert outputs.content_type.startswith(ContentType.APP_JSON)
        assert outputs.json["outputs"] == {
            "output_data": {
                "value": "test"
            },
            "output_json": {
                "href": f"{out_url}/{job_id}/output_json/result.json",
                "type": ContentType.APP_JSON,
            },
        }

    @pytest.mark.oap_part4
    def test_execute_jobs_process_not_found(self):
        # use non-existing process to ensure this particular situation is handled as well
        # a missing process reference must not cause an early "not-found" response
        proc = "random-other-process"
        proc = self.fully_qualified_test_name(proc)

        exec_content = {
            "process": f"https://localhost/processes/{proc}",
            "inputs": {"message": "test"}
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = "/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=self.json_headers, only_local=True)
            assert resp.status_code == 404, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["type"] == "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process"

    @pytest.mark.oap_part4
    def test_execute_jobs_process_malformed_json(self):
        exec_content = {
            "process": "xyz",
            "inputs": {"message": "test"}
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = "/jobs"
            resp = mocked_sub_requests(self.app, "post_json", path, timeout=5,
                                       data=exec_content, headers=self.json_headers, only_local=True)
            assert resp.status_code == 400, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["type"] == "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process"
            assert resp.json["cause"] == {"in": "body", "process": "xyz"}

    @pytest.mark.oap_part4
    def test_execute_jobs_process_malformed_xml(self):
        exec_content = """
        <xml>
            <ows:Identifier></ows:Identifier>
        </xml>
        """
        headers = {
            "Accept": ContentType.APP_JSON,
            "Content-Type": ContentType.APP_XML,
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = "/jobs"
            resp = mocked_sub_requests(self.app, "post", path, timeout=5,
                                       data=exec_content, headers=headers, only_local=True)
            assert resp.status_code == 400, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["type"] == "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process"
            assert resp.json["cause"] == {"in": "body", "ows:Identifier": None}

    @pytest.mark.oap_part4
    def test_execute_jobs_unsupported_media_type(self):
        headers = {
            "Accept": ContentType.APP_JSON,
            "Content-Type": ContentType.TEXT_PLAIN,
        }
        with contextlib.ExitStack() as stack:
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            path = "/jobs"
            resp = mocked_sub_requests(self.app, "post", path, timeout=5, data="", headers=headers, only_local=True)
            assert resp.status_code == 415, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert resp.content_type == ContentType.APP_JSON
            assert resp.json["type"] == (
                "http://www.opengis.net/def/exceptions/ogcapi-processes-4/1.0/unsupported-media-type"
            )
            assert resp.json["cause"] == {"in": "headers", "name": "Content-Type", "value": ContentType.TEXT_PLAIN}


@pytest.mark.functional
class WpsPackageAppWithS3BucketTest(WpsConfigBase, ResourcesUtil):
    """
    Test with output results uploaded to S3 bucket.

    .. warning::
        Every test must setup the WPS-output S3 bucket. This is due to how :mod:`unittest` method contexts are handled
        by :mod:`pywps` as individual test functions, which recreates a new :mod:`moto` mock each time. Therefore, any
        progress within the "session" operations such as remembering the creation of a bucket is undone after each test.

    .. seealso::
        Below decorators apply. Call order matters since following ones employs configurations from previous ones.

        - :func:`mocked_aws_config`
        - :func:`mocked_aws_s3`
        - :func:`setup_aws_s3_bucket`
    """

    @classmethod
    @mocked_aws_config
    @mocked_aws_s3  # avoid error on setup of output S3 bucket under PyWPS config
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

    @mocked_aws_config
    @mocked_aws_s3
    @setup_aws_s3_bucket(bucket="wps-output-test-bucket")
    def test_execute_application_package_process_with_bucket_results(self):
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
                CWL_REQUIREMENT_APP_DOCKER: {
                    "dockerPull": "alpine:latest"
                },
                CWL_REQUIREMENT_INIT_WORKDIR: {
                    # directly copy files to output dir in order to retrieve them by glob
                    "listing": [
                        {"entry": "$(inputs.input_with_http)"},
                        {"entry": "$(inputs.input_with_s3)"},
                    ]
                }
            },
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
        test_http_ref = f"https://www.iana.org/assignments/media-types/{input_file_http}"
        test_bucket_ref = mocked_aws_s3_bucket_test_file("wps-process-test-bucket", input_file_s3)
        exec_body = {
            "mode": ExecuteMode.ASYNC,
            "response": ExecuteResponse.DOCUMENT,
            "inputs": [
                {"id": "input_with_http", "href": test_http_ref},
                {"id": "input_with_s3", "href": test_bucket_ref},
            ],
            "outputs": [
                {"id": "output_from_http", "transmissionMode": ExecuteTransmissionMode.REFERENCE},
                {"id": "output_from_s3", "transmissionMode": ExecuteTransmissionMode.REFERENCE},
            ]
        }
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            proc_url = f"/processes/{self._testMethodName}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            status_url = resp.json["location"]
            job_id = resp.json["jobID"]

        results = self.monitor_job(status_url)
        outputs = self.get_outputs(status_url)

        assert "output_from_http" in results
        assert "output_from_s3" in results

        # check that outputs are S3 bucket references
        output_values = {out["id"]: get_any_value(out) for out in outputs["outputs"]}
        output_bucket = self.settings["weaver.wps_output_s3_bucket"]
        output_files = [("output_from_s3", input_file_s3), ("output_from_http", input_file_http)]
        wps_uuid = str(self.job_store.fetch_by_id(job_id).wps_id)
        for out_id, out_file in output_files:
            output_ref = f"{output_bucket}/{wps_uuid}/{out_id}/{out_file}"
            output_ref_abbrev = f"s3://{output_ref}"
            output_ref_full = f"https://s3.{MOCK_AWS_REGION}.amazonaws.com/{output_ref}"
            output_ref_any = [output_ref_abbrev, output_ref_full]  # allow any variant weaver can parse
            # validation on outputs path
            assert output_values[out_id] in output_ref_any
            # validation on results path
            assert results[out_id]["href"] in output_ref_any

        # check that outputs are indeed stored in S3 buckets
        mocked_s3 = boto3.client("s3", region_name=MOCK_AWS_REGION)
        resp_json = mocked_s3.list_objects_v2(Bucket=output_bucket)
        bucket_file_keys = [obj["Key"] for obj in resp_json["Contents"]]
        for out_id, out_file in output_files:
            out_key = f"{job_id}/{out_id}/{out_file}"
            assert out_key in bucket_file_keys

        # check that outputs are NOT copied locally, but that XML status does exist
        # counter validate path with file always present to ensure outputs are not 'missing' just because of wrong dir
        wps_outdir = self.settings["weaver.wps_output_dir"]
        for out_id, out_file in output_files:
            assert not os.path.exists(os.path.join(wps_outdir, out_file))
            assert not os.path.exists(os.path.join(wps_outdir, job_id, out_file))
            assert not os.path.exists(os.path.join(wps_outdir, wps_uuid, out_file))
            assert not os.path.exists(os.path.join(wps_outdir, out_id, out_file))
            assert not os.path.exists(os.path.join(wps_outdir, job_id, out_id, out_file))
            assert not os.path.exists(os.path.join(wps_outdir, wps_uuid, out_id, out_file))
        assert os.path.isfile(os.path.join(wps_outdir, f"{job_id}.xml"))

    @pytest.mark.skip(reason="OAS execute parse/validate values not implemented")
    def test_execute_job_with_oas_validation(self):
        """
        Process with :term:`OpenAPI` I/O definitions validates the schema of the submitted :term:`JSON` data.
        """
        raise NotImplementedError  # FIXME: implement

    @mocked_aws_config
    @mocked_aws_s3
    @setup_aws_s3_bucket(bucket="wps-output-test-bucket")
    def test_execute_with_directory_output(self):
        """
        Test that directory complex type is resolved from CWL and produces the expected output files in an AWS bucket.

        .. versionadded:: 4.27
        """
        proc = "DirectoryMergingProcess"
        body = self.retrieve_payload(proc, "deploy", local=True)
        pkg = self.retrieve_payload(proc, "package", local=True)
        body["executionUnit"] = [{"unit": pkg}]
        self.deploy_process(body, describe_schema=ProcessSchema.OGC)

        with contextlib.ExitStack() as stack:
            tmp_host = "https://mocked-file-server.com"  # must match in 'Execute_WorkflowSelectCopyNestedOutDir.json'
            tmp_dir = stack.enter_context(tempfile.TemporaryDirectory())
            stack.enter_context(mocked_file_server(tmp_dir, tmp_host, settings=self.settings, mock_browse_index=True))
            input_http_files = [
                # NOTE:
                #   base names must differ to have >1 file in output dir listing because of flat list generated
                #   see the process shell script definition
                "dir/file1.txt",
                "dir/sub/file2.txt",
                # see if auto-detected Media-Type from extensions
                # they should be uploaded along with bucket object file-keys
                "dir/sub/nested/file3.json",
                "dir/other/file4.yml",
            ]
            expect_media_types = {
                "file1.txt": ContentType.TEXT_PLAIN,
                "file2.txt": ContentType.TEXT_PLAIN,
                "file3.json": ContentType.APP_JSON,
                "file4.yml": ContentType.APP_YAML,
            }
            for file in input_http_files:
                path = os.path.join(tmp_dir, file)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, mode="w", encoding="utf-8") as f:
                    f.write("test data")

            output_id = "output_dir"
            exec_body = {
                "mode": ExecuteMode.ASYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": [
                    {"id": "files", "href": os.path.join(tmp_host, http_file)} for http_file in input_http_files
                ],
                "outputs": [
                    {"id": output_id, "transmissionMode": ExecuteTransmissionMode.REFERENCE},
                ]
            }
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{proc}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            status_url = resp.json["location"]
            job_id = resp.json["jobID"]

            results = self.monitor_job(status_url)

            # check that outputs are S3 bucket references
            output_bucket = self.settings["weaver.wps_output_s3_bucket"]
            output_loc = results[output_id]["href"]
            output_ref = f"{output_bucket}/{job_id}/{output_id}/"
            output_key_base = f"{job_id}/{output_id}/"
            output_ref_abbrev = f"s3://{output_ref}"
            output_ref_full = f"https://s3.{MOCK_AWS_REGION}.amazonaws.com/{output_ref}"
            output_ref_any = [output_ref_abbrev, output_ref_full]  # allow any variant weaver can parse
            # validation on outputs path
            assert output_loc in output_ref_any

            # check that outputs are indeed stored in S3 buckets
            mocked_s3 = boto3.client("s3", region_name=MOCK_AWS_REGION)
            resp_json = mocked_s3.list_objects_v2(Bucket=output_bucket)
            bucket_file_info = {obj["Key"]: obj for obj in resp_json["Contents"]}
            expect_out_files = {
                # the process itself makes a flat list of input files, this is not a byproduct of dir-type output
                os.path.join(output_key_base, os.path.basename(file)) for file in input_http_files
            }
            expect_out_dirs = {output_ref_abbrev}
            assert resp_json["Name"] == output_bucket
            assert not any(out_dir in bucket_file_info for out_dir in expect_out_dirs)
            assert all(out_file in bucket_file_info for out_file in expect_out_files)
            assert len(set(bucket_file_info) - expect_out_files) == 0, "No extra files expected."

            # validate that common file extensions could be detected and auto-populated the Content-Type
            # (information not available in 'list_objects_v2', so fetch each file individually
            bucket_file_media_types = {}
            for out_file in expect_out_files:
                out_info = mocked_s3.head_object(Bucket=output_bucket, Key=out_file)
                out_key = os.path.basename(out_file)
                bucket_file_media_types[out_key] = out_info["ContentType"]
            assert bucket_file_media_types == expect_media_types

            # check that outputs are NOT copied locally, but that XML status does exist
            # counter validate path with file always present to ensure outputs are not 'missing' because of wrong dir
            wps_uuid = str(self.job_store.fetch_by_id(job_id).wps_id)
            wps_outdir = self.settings["weaver.wps_output_dir"]
            bad_out_dirs = {output_id}
            bad_out_files = {os.path.basename(file) for file in input_http_files}
            for out_dir in bad_out_dirs:
                assert not os.path.exists(os.path.join(wps_outdir, out_dir))
                assert not os.path.exists(os.path.join(wps_outdir, job_id, out_dir))
                assert not os.path.exists(os.path.join(wps_outdir, wps_uuid, out_dir))
            for out_file in bad_out_files:
                assert not os.path.exists(os.path.join(wps_outdir, out_file))
                assert not os.path.exists(os.path.join(wps_outdir, job_id, out_file))
                assert not os.path.exists(os.path.join(wps_outdir, wps_uuid, out_file))
                assert not os.path.exists(os.path.join(wps_outdir, output_id, out_file))
                assert not os.path.exists(os.path.join(wps_outdir, job_id, output_id, out_file))
                assert not os.path.exists(os.path.join(wps_outdir, wps_uuid, output_id, out_file))
            assert os.path.isfile(os.path.join(wps_outdir, f"{job_id}.xml"))

    @mocked_aws_config
    @mocked_aws_s3
    @setup_aws_s3_bucket(bucket="wps-output-test-bucket")
    def test_execute_with_result_representations(self):
        """
        Test that an output file stored in an AWS bucket can be retrieved as per their requested ``transmissionMode``.

        .. versionadded:: 6.0
        """
        proc = "EchoResultsTester"
        p_id = self.fully_qualified_test_name(proc)
        body = self.retrieve_payload(proc, "deploy", local=True)
        self.deploy_process(body, process_id=p_id)

        with contextlib.ExitStack() as stack:
            exec_body = {
                "mode": ExecuteMode.SYNC,
                "response": ExecuteResponse.DOCUMENT,
                "inputs": {"message": "test data in bucket"},
                "outputs": {
                    "output_json": {"transmissionMode": ExecuteTransmissionMode.VALUE},
                    "output_text": {"transmissionMode": ExecuteTransmissionMode.REFERENCE},
                },
            }
            for mock_exec in mocked_execute_celery():
                stack.enter_context(mock_exec)
            proc_url = f"/processes/{p_id}/execution"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code == 200, f"Failed with: [{resp.status_code}]\nReason:\n{resp.text}"
            assert resp.content_type == ContentType.APP_JSON

        # rely on location that should be provided to find the job ID
        results = resp.json
        results_url = get_header("Content-Location", resp.headers)
        assert results_url, (
            "Content-Location should have been provided in"
            "results response pointing at where they can be found."
        )
        job_id = results_url.rsplit("/results")[0].rsplit("/jobs/")[-1]
        assert is_uuid(job_id), f"Failed to retrieve the job ID: [{job_id}] is not a UUID"

        out_path = f"/jobs/{job_id}/outputs"
        out_params = {"schema": JobInputsOutputsSchema.OGC_STRICT}
        out_resp = self.app.get(out_path, headers=self.json_headers, params=out_params)
        outputs = out_resp.json

        # check that outputs by reference are S3 bucket references
        # for 'outputs' endpoint, reference always expected for File type
        # for 'results' endpoint, only the output requested by reference 'transmissionMode' is expected
        for output_id, output_file, outputs_doc in [
            ("output_text", "result.txt", results),
            ("output_text", "result.txt", outputs["outputs"]),
            ("output_json", "result.json", outputs["outputs"]),
        ]:
            output_bucket = self.settings["weaver.wps_output_s3_bucket"]
            output_loc = outputs_doc[output_id]["href"]
            output_key = f"{job_id}/{output_id}/{output_file}"
            output_ref = f"{output_bucket}/{output_key}"
            output_ref_abbrev = f"s3://{output_ref}"
            output_ref_full = f"https://s3.{MOCK_AWS_REGION}.amazonaws.com/{output_ref}"
            output_ref_any = [output_ref_abbrev, output_ref_full]  # allow any variant weaver can parse
            assert output_loc in output_ref_any

        # check that result by 'transmissionMode' value is not a reference, but the contents
        assert "output_json" in results
        assert "value" in results["output_json"]
        assert "href" not in results["output_json"]
        assert results["output_json"]["value"] == {"data": "test data in bucket"}
        assert results["output_json"]["mediaType"] == ContentType.APP_JSON

        # check that outputs are indeed stored in S3 buckets
        mocked_s3 = boto3.client("s3", region_name=MOCK_AWS_REGION)
        resp_json = mocked_s3.list_objects_v2(Bucket=output_bucket)
        bucket_file_info = {obj["Key"]: obj for obj in resp_json["Contents"]}
        expect_out_files = {
            f"{job_id}/{output_id}/{output_file}": out_type
            for output_id, output_file, out_type
            in [
                ("output_json", "result.json", ContentType.APP_JSON),
                ("output_text", "result.txt", ContentType.TEXT_PLAIN),
            ]
        }
        assert resp_json["Name"] == output_bucket
        assert len(bucket_file_info) == len(expect_out_files), "No extra files expected."
        assert all(out_file in bucket_file_info for out_file in expect_out_files)

        # validate that common file extensions could be detected and auto-populated the Content-Type
        # (information not available in 'list_objects_v2', so fetch each file individually
        for out_file, out_type in expect_out_files.items():
            out_info = mocked_s3.head_object(Bucket=output_bucket, Key=out_file)
            assert out_info["ContentType"] == out_type

        # check that outputs are NOT copied locally, but that XML status does exist
        # counter validate path with file always present to ensure outputs are not 'missing' because of wrong dir
        wps_uuid = str(self.job_store.fetch_by_id(job_id).wps_id)
        wps_outdir = self.settings["weaver.wps_output_dir"]
        # NOTE: exception for 'output_json' since by-value representation forces it to retrieve it locally
        exception_id = ["output_json"]
        for out_file in list(expect_out_files):
            out_path, out_name = os.path.split(out_file)
            _, out_id = os.path.split(out_path)
            assert not os.path.exists(os.path.join(wps_outdir, out_name))
            assert not os.path.exists(os.path.join(wps_outdir, job_id, out_name))
            assert not os.path.exists(os.path.join(wps_outdir, wps_uuid, out_name))
            assert not os.path.exists(os.path.join(wps_outdir, out_id, out_name))
            if out_id not in exception_id:
                assert not os.path.exists(os.path.join(wps_outdir, job_id, out_id, out_name))
                assert not os.path.exists(os.path.join(wps_outdir, wps_uuid, out_id, out_name))
        assert os.path.isfile(os.path.join(wps_outdir, f"{job_id}.xml"))
