"""
Functional tests of operations implemented by :mod:`weaver.processes.wps_package`.

Validates that CWL package definitions are parsed and executes the process as intended.
Local test web application is employed to run operations by mocking external requests.

.. seealso::
    - :mod:`tests.processes.wps_package`.
"""
import contextlib
import copy
import json
import logging
import os
import tempfile
from copy import deepcopy
from inspect import cleandoc
from typing import TYPE_CHECKING

import boto3
import colander
import pytest
import yaml
from parameterized import parameterized

from tests import resources
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
    mocked_sub_requests,
    mocked_wps_output,
    setup_aws_s3_bucket
)
from weaver.execute import ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
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
    ProcessSchema
)
from weaver.processes.types import ProcessType
from weaver.status import Status
from weaver.utils import fetch_file, get_any_value, load_file
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url, map_wps_output_location

if TYPE_CHECKING:
    from typing import List

    from weaver.typedefs import JSON, CWL_AnyRequirements

EDAM_PLAIN = EDAM_NAMESPACE + ":" + EDAM_MAPPING[ContentType.TEXT_PLAIN]
OGC_NETCDF = OGC_NAMESPACE + ":" + OGC_MAPPING[ContentType.APP_NETCDF]
# note: x-tar cannot be mapped during CWL format resolution (not official schema),
#       it remains explicit tar definition in WPS context
IANA_TAR = IANA_NAMESPACE + ":" + ContentType.APP_TAR  # noqa # pylint: disable=unused-variable
IANA_ZIP = IANA_NAMESPACE + ":" + ContentType.APP_ZIP  # noqa # pylint: disable=unused-variable

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

    @classmethod
    def request(cls, method, url, *args, **kwargs):
        raise NotImplementedError  # not used

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
        proc = desc["process"]
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
        ogc_api_ref = "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/d52579"

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
            "format": "ogc-bbox",
            # added:
            "$id": f"{ogc_api_ref}/core/openapi/schemas/bbox.yaml"
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
        # FIXME: support measure I/O (https://github.com/crim-ca/weaver/issues/430)
        #        parsing works to detect numeric type, but reverse operation WPS->OAS not obvious
        #        since no real indication/distinction between a literal data and one with uom
        # assert desc["inputs"]["measureInput"]["schema"] == ref["inputs"]["measureInput"]["schema"]  # no change
        assert desc["inputs"]["stringInput"]["schema"] == ref["inputs"]["stringInput"]["schema"]  # no change

        # NOTE:
        #   although conversion is possible, min/max occurs not allowed in outputs WPS representation
        #   because of this, they will also be omitted in the OpenAPI schema definition following merge
        #   *everything else* should be identical to inputs
        assert desc["outputs"]["arrayOutput"]["schema"] == ref["outputs"]["arrayOutput"]["schema"]  # no change
        assert desc["outputs"]["boundingBoxOutput"]["schema"] == {
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
            "format": "ogc-bbox",
            # added:
            "$id": f"{ogc_api_ref}/core/openapi/schemas/bbox.yaml"
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
        # FIXME: support measure I/O (https://github.com/crim-ca/weaver/issues/430)
        #        parsing works to detect numeric type, but reverse operation WPS->OAS not obvious
        #        since no real indication/distinction between a literal data and one with uom
        # assert desc["outputs"]["measureOutput"]["schema"] == ref["outputs"]["measureOutput"]["schema"]  # no change
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
        proc = desc["process"]

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
        proc = desc["process"]

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
        proc = desc["process"]

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
        proc = desc["process"]
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
                        # FIXME: multiple output (array) not implemented (https://github.com/crim-ca/weaver/issues/25)
                        # {
                        #     "id": "multi_value_multi_format",
                        #     "formats": [
                        #         {"mimeType": ContentType.APP_NETCDF},
                        #         {"mimeType": ContentType.TEXT_PLAIN},
                        #         {"mimeType": ContentType.APP_JSON},
                        #     ]
                        # }
                    ]
                },
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }
        desc, pkg = self.deploy_process(body, describe_schema=ProcessSchema.OLD)
        proc = desc["process"]

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
        assert len(proc["outputs"]) == 2  # FIXME: adjust output count when issue #25 is implemented
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
        # FIXME: enable when issue #25 is implemented
        # assert proc["outputs"][2]["id"] == "multi_value_single_format"
        # assert len(proc["outputs"][2]["formats"]) == 1
        # assert proc["outputs"][2]["formats"][0] == ContentType.APP_NETCDF
        # assert proc["outputs"][3]["id"] == "multi_value_multi_format"
        # assert len(proc["outputs"][3]["formats"]) == 3
        # assert proc["outputs"][3]["formats"][0] == ContentType.APP_NETCDF
        # assert proc["outputs"][3]["formats"][1] == ContentType.TEXT_PLAIN
        # assert proc["outputs"][3]["formats"][2] == ContentType.APP_JSON

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
        # FIXME: enable when issue #25 is implemented
        # assert pkg["outputs"][2]["id"] == "multi_value_single_format"
        # assert pkg["outputs"][2]["type"] == "array"
        # assert pkg["outputs"][2]["items"] == "File"
        # assert pkg["outputs"][2]["format"] == type_ncdf
        # assert pkg["outputs"][3]["id"] == "multi_value_multi_format"
        # assert pkg["outputs"][3]["type"] == "array"
        # assert pkg["outputs"][3]["items"] == "File"
        # assert "format" not in pkg["outputs"][3], "CWL format array not allowed for outputs."

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
        proc = desc["process"]

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
        proc = desc["process"]
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

        assert isinstance(desc["inputs"], dict)
        assert len(desc["inputs"]) == len(body["processDescription"]["process"]["inputs"])
        assert isinstance(desc["outputs"], dict)
        assert len(desc["outputs"]) == len(body["processDescription"]["process"]["outputs"])

        # following inputs metadata were correctly parsed from WPS mapping entries if defined and not using defaults
        assert desc["inputs"]["input_num"]["title"] == "Input numbers"
        assert desc["inputs"]["input_num"]["maxOccurs"] == 20
        assert desc["inputs"]["input_num"]["literalDataDomains"][0]["dataType"]["name"] == "float"
        assert desc["inputs"]["input_file"]["title"] == "Test File"
        assert desc["inputs"]["input_file"]["formats"][0]["mediaType"] == ContentType.APP_ZIP
        assert desc["outputs"]["values"]["title"] == "Test Output"
        assert desc["outputs"]["values"]["description"] == "CSV raw values"
        assert desc["outputs"]["values"]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert desc["outputs"]["out_file"]["title"] == "Result File"
        assert desc["outputs"]["out_file"]["formats"][0]["mediaType"] == "text/csv"

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
        headers = deepcopy(self.json_headers)

        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            proc_url = f"/processes/{self._testMethodName}/jobs"

            valid_languages = [(lang, True) for lang in AcceptLanguage.values()]
            wrong_languages = [(lang, False) for lang in ["ru", "fr-CH"]]
            for lang, accept in valid_languages + wrong_languages:
                headers["Accept-Language"] = lang
                resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5, expect_errors=not accept,
                                           data=exec_body, headers=headers, only_local=True)
                code = resp.status_code
                if accept:  # must execute until completion with success
                    assert code in [200, 201], f"Failed with: [{code}]\nReason:\n{resp.json}"
                    status_url = resp.json.get("location")
                    self.monitor_job(status_url, timeout=5, return_status=True)  # wait until success
                    job_id = resp.json.get("jobID")
                    job = self.job_store.fetch_by_id(job_id)
                    assert job.accept_language == lang
                else:
                    # job not even created
                    assert code == 406, "Error code should indicate not acceptable header"
                    desc = resp.json.get("description")
                    assert "language" in desc and lang in desc, "Expected error description to indicate bad language"

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
                            "entry": cleandoc("""
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
            "outputs": [{"id": "output", "transmissionMode": ExecuteTransmissionMode.VALUE}]
        }
        headers = deepcopy(self.json_headers)

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
                ctx_dir = (wps_dir + "/" + ctx) if ctx else wps_dir
                out_url = self.settings["weaver.wps_output_url"]
                ctx_url = (out_url + "/" + ctx) if ctx else out_url
                res_url = ctx_url + "/" + job_id + "/output/stdout.log"
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
        headers = deepcopy(self.json_headers)

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

    def test_execute_with_json_listing_directory(self):
        """
        Test that HTTP returning JSON list of directory contents retrieves children files for the process.

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
            out_url = os.path.join(wps_url, job_id, "output_dir") + "/"
            assert results["output_dir"]["href"] == out_url
            assert os.path.isdir(out_dir)
            expect_out_files = {
                # the process itself makes a flat list of input files, this is not a byproduct of dir-type output
                os.path.join(out_dir, os.path.basename(file)) for file in input_http_files
            }
            assert all(os.path.isfile(file) for file in expect_out_files)
            output_dir_files = {os.path.join(root, file) for root, _, files in os.walk(out_dir) for file in files}
            assert output_dir_files == expect_out_files

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
            "inputs": [{}],   # updated after
            "outputs": {"values": {"type": "string"}}
        }
        body = {
            "processDescription": {
                "process": {
                    "id": self._testMethodName,
                    "title": "some title",
                    "abstract": "this is a test",
                    "inputs": [{}]  # updated after
                },
            },
            "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication",
            "executionUnit": [{"unit": cwl}],
        }

        # replace by invalid min/max and check that it raises
        cwl["inputs"][0] = {"id": "test", "type": {"type": "array", "items": "string"}}
        body["processDescription"]["process"]["inputs"][0] = {"id": "test", "minOccurs": [1], "maxOccurs": 1}
        resp = mocked_sub_requests(self.app, "post_json", "/processes", data=body, headers=self.json_headers)
        assert resp.status_code == 400, "Invalid input minOccurs schema definition should have been raised"
        assert "DeployMinMaxOccurs" in resp.json["cause"]
        assert "Invalid" in resp.json["error"]

        cwl["inputs"][0] = {"id": "test", "type": {"type": "array", "items": "string"}}
        body["processDescription"]["process"]["inputs"][0] = {"id": "test", "minOccurs": 1, "maxOccurs": 3.1416}
        resp = mocked_sub_requests(self.app, "post_json", "/processes", data=body, headers=self.json_headers)
        assert resp.status_code == 400, "Invalid input maxOccurs schema definition should have been raised"
        assert "DeployMinMaxOccurs" in resp.json["cause"]
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
        proc = desc["process"]
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
        proc = desc["process"]

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
        proc = desc["process"]
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
        assert pkg["outputs"][0]["outputBinding"]["glob"] == "output_netcdf/*.nc"
        assert pkg["outputs"][1]["id"] == "output_log"
        assert "default" not in pkg["outputs"][1]
        assert pkg["outputs"][1]["format"] == EDAM_PLAIN
        assert pkg["outputs"][1]["type"] == "File"
        assert pkg["outputs"][1]["outputBinding"]["glob"] == "output_log/*.*"

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
        proc = desc["process"]
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

    # FIXME: implement,
    #   need to find a existing WPS with some, or manually write XML
    #   multi-output (with same ID) would be an indirect 1-output with ref to multi (Metalink file)
    #   (https://github.com/crim-ca/weaver/issues/25)
    @pytest.mark.skip(reason="not implemented")
    def test_deploy_multi_outputs_file_from_wps_xml_reference(self):
        raise NotImplementedError


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
                {"id": "output_from_http", "transmissionMode": ExecuteTransmissionMode.VALUE},
                {"id": "output_from_s3", "transmissionMode": ExecuteTransmissionMode.VALUE},
            ]
        }
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            proc_url = f"/processes/{self._testMethodName}/jobs"
            resp = mocked_sub_requests(self.app, "post_json", proc_url, timeout=5,
                                       data=exec_body, headers=self.json_headers, only_local=True)
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            status_url = resp.json["location"]
            job_id = resp.json["jobID"]

        results = self.monitor_job(status_url)
        outputs = self.get_outputs(status_url)

        assert "output_from_http" in results
        assert "output_from_s3" in results

        # check that outputs are S3 bucket references
        output_values = {out["id"]: get_any_value(out) for out in outputs["outputs"]}
        output_bucket = self.settings["weaver.wps_output_s3_bucket"]
        wps_uuid = str(self.job_store.fetch_by_id(job_id).wps_id)
        for out_key, out_file in [("output_from_s3", input_file_s3), ("output_from_http", input_file_http)]:
            output_ref = f"{output_bucket}/{wps_uuid}/{out_file}"
            output_ref_abbrev = f"s3://{output_ref}"
            output_ref_full = f"https://s3.{MOCK_AWS_REGION}.amazonaws.com/{output_ref}"
            output_ref_any = [output_ref_abbrev, output_ref_full]  # allow any variant weaver can parse
            # validation on outputs path
            assert output_values[out_key] in output_ref_any
            # validation on results path
            assert results[out_key]["href"] in output_ref_any

        # check that outputs are indeed stored in S3 buckets
        mocked_s3 = boto3.client("s3", region_name=MOCK_AWS_REGION)
        resp_json = mocked_s3.list_objects_v2(Bucket=output_bucket)
        bucket_file_keys = [obj["Key"] for obj in resp_json["Contents"]]
        for out_file in [input_file_s3, input_file_http]:
            out_key = f"{job_id}/{out_file}"
            assert out_key in bucket_file_keys

        # check that outputs are NOT copied locally, but that XML status does exist
        # counter validate path with file always present to ensure outputs are not 'missing' just because of wrong dir
        wps_outdir = self.settings["weaver.wps_output_dir"]
        for out_file in [input_file_s3, input_file_http]:
            assert not os.path.exists(os.path.join(wps_outdir, out_file))
            assert not os.path.exists(os.path.join(wps_outdir, job_id, out_file))
            assert not os.path.exists(os.path.join(wps_outdir, wps_uuid, out_file))
        assert os.path.isfile(os.path.join(wps_outdir, f"{job_id}.xml"))

    # FIXME: implement
    @pytest.mark.skip(reason="OAS execute parse/validate values not implemented")
    def test_execute_job_with_oas_validation(self):
        """
        Process with :term:`OpenAPI` I/O definitions validates the schema of the submitted :term:`JSON` data.
        """
        raise NotImplementedError

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
            assert resp.status_code in [200, 201], f"Failed with: [{resp.status_code}]\nReason:\n{resp.json}"
            status_url = resp.json["location"]
            job_id = resp.json["jobID"]

            results = self.monitor_job(status_url)

            # check that outputs are S3 bucket references
            output_bucket = self.settings["weaver.wps_output_s3_bucket"]
            output_loc = results["output_dir"]["href"]
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
