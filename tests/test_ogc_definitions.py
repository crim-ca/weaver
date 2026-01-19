import pytest

from weaver import ogc_definitions as ogc_defs


@pytest.mark.parametrize(
    ["input_uri", "expect_uri"],
    [
        ("http://www.opengis.net/def/profile/OGC/0/ogc-results", "[ogc-profile:ogc-results]"),
        ("http://www.opengis.net/def/rel/ogc/1.0/process-desc", "[ogc-rel:process-desc]"),
        ("http://www.opengis.net/def/crs/OGC/0/CRS84h", "[ogc-crs:CRS84h]"),
        ("[ogc-rel:process-desc]", "[ogc-rel:process-desc]"),
    ],
)
def test_curie(input_uri, expect_uri):
    assert ogc_defs.curie(input_uri) == expect_uri


@pytest.mark.parametrize(
    ["input_uri", "expect_uri"],
    [
        ("http://www.opengis.net/def/rel/ogc/1.0/process-desc", "http://www.opengis.net/def/rel/ogc/1.0/process-desc"),
        ("urn:ogc:def:crs:EPSG::4326", "http://www.opengis.net/def/crs/EPSG/0/4326"),
        ("[ogc-rel:process-desc]", "http://www.opengis.net/def/rel/ogc/1.0/process-desc"),
        ("http://www.opengis.net/def/crs/OGC/1.3/CRS84", "http://www.opengis.net/def/crs/OGC/0/CRS84"),
        ("http://www.opengis.net/def/crs/OGC/0/CRS84h", "http://www.opengis.net/def/crs/OGC/0/CRS84h"),
        # # edge cases handled on their own due to inconsistent structure with others
        # ("urn:ogc:def:crs:OGC:2:84", "http://www.opengis.net/def/crs/OGC/0/CRS84"),
        # ("urn:ogc:def:crs:CRS::84", "http://www.opengis.net/def/crs/OGC/0/CRS84"),
    ],
)
def test_normalize(input_uri, expect_uri):
    assert ogc_defs.normalize(input_uri) == expect_uri


@pytest.mark.parametrize(
    ["input_uri", "expect_uri", "version"],
    [
        (
            "http://www.opengis.net/def/crs/OGC/0/CRS84",
            "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            "1.3",
        ),
        (
            "[ogc-rel:process-desc]",
            "http://www.opengis.net/def/rel/ogc/2.0/process-desc",
            "2.0",
        )
    ]
)
def test_normalize_alternate_versions(input_uri, expect_uri, version):
    assert ogc_defs.normalize(input_uri, version=version) == expect_uri
