import pytest

from weaver import ogc_definitions as ogc_defs


@pytest.mark.parametrize(
    ["input_uri", "expect_uri"],
    [
        ("http://www.opengis.net/def/rel/ogc/1.0/process-desc", "[ogc-rel:process-desc]"),
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
    ],
)
def test_normalize(input_uri, expect_uri):
    assert ogc_defs.normalize(input_uri) == expect_uri
