import pytest

from weaver import ogc_definitions as ogc_defs
from weaver.wps_restapi import swagger_definitions as sd


@pytest.mark.parametrize(
    ["input_uri", "expect_uri"],
    [
        ("https://www.opengis.net/def/profile/OGC/0/ogc-results", "[ogc-profile:ogc-results]"),
        ("https://www.opengis.net/def/rel/ogc/1.0/process-desc", "[ogc-rel:process-desc]"),
        ("https://www.opengis.net/def/crs/OGC/0/CRS84h", "[ogc-crs:CRS84h]"),
        ("[ogc-rel:process-desc]", "[ogc-rel:process-desc]"),
    ],
)
def test_curie(input_uri, expect_uri):
    assert ogc_defs.curie(input_uri) == expect_uri


@pytest.mark.parametrize(
    ["input_uri", "expect_uri", "secure"],
    [
        (sd.OGC_API_PROC_REL_PROCESS_DESC_URI, sd.OGC_API_PROC_REL_PROCESS_DESC_URI, True),
        (ogc_defs.OGC_DEF_CRS_EPSG4326_URN, ogc_defs.OGC_DEF_CRS_EPSG4326_URI, False),
        ("[ogc-rel:process-desc]", sd.OGC_API_PROC_REL_PROCESS_DESC_URI, True),
        ("https://www.opengis.net/def/crs/OGC/1.3/CRS84", "https://www.opengis.net/def/crs/OGC/0/CRS84", True),
        ("https://www.opengis.net/def/crs/OGC/0/CRS84h", "https://www.opengis.net/def/crs/OGC/0/CRS84h", True),
        # # edge cases handled on their own due to inconsistent structure with others
        # ("urn:ogc:def:crs:OGC:2:84", "https://www.opengis.net/def/crs/OGC/0/CRS84"),
        # ("urn:ogc:def:crs:CRS::84", "https://www.opengis.net/def/crs/OGC/0/CRS84"),
    ],
)
def test_normalize(input_uri, expect_uri, secure):
    assert ogc_defs.normalize(input_uri, secure=secure) == expect_uri


@pytest.mark.parametrize(
    ["input_uri", "expect_uri", "version"],
    [
        (
            "https://www.opengis.net/def/crs/OGC/0/CRS84",
            "https://www.opengis.net/def/crs/OGC/1.3/CRS84",
            "1.3",
        ),
        (
            "[ogc-rel:process-desc]",
            "https://www.opengis.net/def/rel/ogc/2.0/process-desc",
            "2.0",
        ),
        (
            "[ogc-rel:process-desc]",
            "https://www.opengis.net/def/rel/ogc/0/process-desc",
            "0",
        ),
        (
            "https://www.opengis.net/def/rel/ogc/1.3/process-desc",
            "https://www.opengis.net/def/rel/ogc/0/process-desc",
            "0",
        ),
        # when version is unspecified and missing in original reference
        # the normalized URI uses the approprite default (depending on link type)
        (
            # this is also a special case because of the duplicate 'ogc-'
            # ensure it gets expanded properly (not double URI)
            "[ogc-profile:ogc-results]",
            "https://www.opengis.net/def/profile/ogc/0/ogc-results",
            None,
        ),
        (
            "[ogc-rel:process-desc]",
            "https://www.opengis.net/def/rel/ogc/1.0/process-desc",
            None,
        )
    ]
)
def test_normalize_alternate_versions(input_uri, expect_uri, version):
    assert ogc_defs.normalize(input_uri, version=version) == expect_uri
