import copy
import glob
import os
import uuid
from typing import TYPE_CHECKING

import colander
import mock
import pytest

from weaver.formats import ContentType
from weaver.utils import load_file
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from weaver.typedefs import CWL, JSON

TEST_DIR = os.path.dirname(os.path.dirname(__file__))


def test_process_id_with_version_tag_deploy_invalid():
    """
    Validate process ID with version label is not allowed as definition during deployment or update.

    To take advantage of auto-resolution of unique :meth:`StoreProcesses.fetch_by_id` with version references injected
    in the process ID stored in the database, deployment and description of processes must not allow it to avoid
    conflicts. The storage should take care of replacing the ID value transparently after it was resolved.
    """
    test_id_version_invalid = [
        "process:1.2.3",
        "test-process:4.5.6",
        "other_process:1",
        "invalid-process:1_2_3",
        f"{uuid.uuid4()}:7.8.9",
    ]
    for test_id in test_id_version_invalid:
        with pytest.raises(colander.Invalid):
            sd.ProcessIdentifier().deserialize(test_id)
    for test_id in test_id_version_invalid:
        test_id = test_id.split(":", 1)[0]
        assert sd.ProcessIdentifier().deserialize(test_id) == test_id


def test_process_id_with_version_tag_get_valid():
    """
    Validate that process ID with tagged version is permitted for request path parameter to retrieve it.
    """
    test_id_version_valid = [
        "test-ok",
        "test-ok1",
        "test-ok:1",
        "test-ok:1.2.3",
        "also_ok:1.3",
    ]
    test_id_version_invalid = [
        "no-:1.2.3",
        "not-ok1.2.3",
        "no:",
        "not-ok:",
        "not-ok11:",
        "not-ok1.2.3:",
    ]
    for test_id in test_id_version_invalid:
        with pytest.raises(colander.Invalid):
            sd.ProcessIdentifierTag().deserialize(test_id)
    for test_id in test_id_version_valid:
        assert sd.ProcessIdentifierTag().deserialize(test_id) == test_id


@pytest.mark.parametrize(
    ["test_data", "expect_result"],
    [
        (
            {"input": "abc"},
            {"input": "abc"},
        ),
        (
            {"input": 123},
            {"input": 123},
        ),
        (
            {"input": {"custom": 123}},
            colander.Invalid,  # not nested under 'value'
        ),
        (
            {"input": ["abc"]},
            {"input": ["abc"]},
        ),
        (
            {"input": [123]},
            {"input": [123]},
        ),
        (
            {"input": [{"custom": 123}]},
            colander.Invalid,  # not nested under 'value'
        ),
        (
            {"input": {"value": "abc"}},
            {"input": {"value": "abc", "mediaType": ContentType.TEXT_PLAIN}},
        ),
        (
            {"input": {"value": 123}},
            {"input": {"value": 123, "mediaType": ContentType.TEXT_PLAIN}},
        ),
        (
            {"input": {"value": "abc"}},
            {"input": {"value": "abc", "mediaType": ContentType.TEXT_PLAIN}},
        ),
        (
            {"input": {"value": {"custom": 123}}},
            {"input": {"value": {"custom": 123}, "mediaType": ContentType.APP_JSON}},
        ),
        (
            # array of custom schema
            {"input": [{"custom": 123}]},
            colander.Invalid,  # each item must be nested by 'qualifiedValue'
        ),
        (
            # array of custom schema
            {"input": [{"value": {"custom": 123}}]},
            {"input": [{"value": {"custom": 123}, "mediaType": ContentType.APP_JSON}]},
        ),
        (
            # custom schema, which happens to be an array of objects
            {"input": {"value": [{"custom": 123}]}},
            colander.Invalid,
        ),
        # special object allowed directly
        (
            {"input": {"bbox": [1, 2, 3, 4]}},
            {"input": {
                "$schema": sd.OGC_API_BBOX_SCHEMA,
                "bbox": [1, 2, 3, 4],
                "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            }},
        ),
        (
            {"input": [{"bbox": [1, 2, 3, 4]}, {"bbox": [5, 6, 7, 8, 9, 0]}]},
            {
                "input": [
                    {
                        "$schema": sd.OGC_API_BBOX_SCHEMA,
                        "bbox": [1, 2, 3, 4],
                        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                    },
                    {
                        "$schema": sd.OGC_API_BBOX_SCHEMA,
                        "bbox": [5, 6, 7, 8, 9, 0],
                        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
                    }
                ]
            },
        ),
        # special known object, but still not allowed directly
        (
            {"input": {"measurement": 1, "uom": "m"}},
            colander.Invalid,
        ),
        (
            {"input": {"value": {"measurement": 1, "uom": "m"}}},
            {"input": {"value": {"measurement": 1, "uom": "m"}, "mediaType": ContentType.APP_JSON}},
        ),
        (
            {"input": [{"value": {"measurement": 1, "uom": "m"}}]},
            {"input": [{"value": {"measurement": 1, "uom": "m"}, "mediaType": ContentType.APP_JSON}]},
        ),
    ]
)
def test_execute_input_inline_object_invalid(test_data, expect_result):
    """
    Ensure that generic data objects provided inline are disallowed, but known objects are permitted.

    This validates that schema definitions are not ambiguous. In such case, overly generic objects that can be
    validated against multiple schemas (e.g.: ``oneOf``) will raise :class:`colander.Invalid` with relevant details.
    """
    schema = sd.ExecuteInputValues()
    if expect_result is colander.Invalid:
        with pytest.raises(colander.Invalid):
            schema.deserialize(test_data)
    else:
        result = schema.deserialize(test_data)
        assert result == expect_result


@pytest.mark.parametrize(
    "cwl_path",
    glob.glob(
        os.path.join(TEST_DIR, "**/*.cwl"),
        recursive=True,
    )
)
def test_cwl_package(cwl_path):
    # type: (str) -> None
    """
    Test that our :term:`CWL` schema definition works with the many examples used for testsing.
    """
    cwl = load_file(cwl_path)  # type: CWL
    cwl_check = sd.CWL().deserialize(cwl)
    cwl_check.pop("$schema", None)  # our definition injects this reference
    assert cwl_check == cwl


@pytest.mark.parametrize(
    "input_data",
    [
        {
            "collection": "https://example.com/collections/test"
        },
        {
            "collection": "https://example.com/collections/test",
            "filter": {"op": "gt", "args": [{"property": "eo:cloud_cover"}, 0.1]},
            "filter-lang": "cql2-json",
        },
        {
            "collection": "https://example.com/collections/test",
            "filter": "properties.eo:cloud_cover > 0.1",
            "filter-lang": "cql2-text",
        },
        {
            "collection": "https://example.com/collections/test",
            "filter": "INTERSECTS(geom, POINT (1 2))",
            "filter-lang": "simple-cql",
            "sortBy": "-eo:cloud_cover,+title",
        },
        {
            "collection": "https://example.com/collections/test",
            # examples: https://docs.ogc.org/is/09-026r2/09-026r2.html#107
            "filter-lang": "fes",
            "filter": """
                <?xml version="1.0"?>
                <fes:Filter
                   xmlns:fes="http://www.opengis.net/fes/2.0"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xsi:schemaLocation="http://www.opengis.net/fes/2.0
                   http://schemas.opengis.net/filter/2.0.02.0/filterAll.xsd">
                  <fes:PropertyIsEqualTo>
                    <fes:ValueReference>SomeProperty</fes:ValueReference>
                    <fes:Literal>100</fes:Literal>
                  </fes:PropertyIsEqualTo>
                </fes:Filter>
            """,
        }
    ]
)
def test_collection_input_parsing(input_data):
    # type: (JSON) -> None
    """
    Validate that the schema definition for a ``collection`` input resolves as expected.
    """
    expect = copy.deepcopy(input_data)
    result = sd.ExecuteCollectionInput().deserialize(input_data)
    result.pop("format", None)
    assert result == expect


@pytest.mark.parametrize(
    ["sort_by", "expect"],
    [
        ({}, {}),
        ({"sortBy": "-eo:cloud_cover"}, {"sortBy": "-eo:cloud_cover"}),
        ({"sortby": "-eo:cloud_cover"}, {"sortBy": "-eo:cloud_cover"}),
        ({"sortby": "+name,-eo:cloud_cover"}, {"sortBy": "+name,-eo:cloud_cover"}),
        ({"sortBy": "+name", "sortby": "-name"}, {"sortBy": "+name"}),
    ]
)
def test_collection_input_sortby(sort_by, expect):
    # type: (JSON, JSON) -> None
    input_data = {"collection": "https://example.com/collections/test"}
    expect.update(copy.deepcopy(input_data))
    input_data.update(sort_by)
    result = sd.ExecuteCollectionInput().deserialize(input_data)
    result.pop("format")
    assert result == expect


def test_collection_input_sortby_missing():
    assert sd.SortBySchema().deserialize({}) in [colander.drop, {}]


def test_collection_input_filter_lang_case_insensitive():
    col = {
        "collection": "https://example.com/collections/test",
        "filter": {"op": "gt", "args": [{"property": "eo:cloud_cover"}, 0.1]},
        "filter-lang": "CQL2-JSON",  # case-insensitive
    }
    result = sd.ExecuteCollectionInput().deserialize(col)
    assert result["filter-lang"] == "cql2-json"


@pytest.mark.parametrize(
    "input_data",
    [
        # other 'valid' input types, to ensure the schema can distinguish them
        {
            "value": "https://example.com/collections/test"
        },
        {
            "href": "https://example.com/collections/test",
            "type": ContentType.APP_GEOJSON,
        },
        # malformed collection properties
        {
            "collection": "https://example.com/collections/test",
            "filter": "",
        },
        {
            "collection": "https://example.com/collections/test",
            "filter": [],
        },
        {
            "collection": "https://example.com/collections/test",
            "filter": {},
        },
        {
            "collection": "https://example.com/collections/test",
            "filter": "PROPERTY = 123",
            "filter-lang": "cql2-json",
        },
        {
            "collection": "https://example.com/collections/test",
            "filter-lang": "cql2-json",
        },
        {
            "collection": "https://example.com/collections/test",
            "filter-crs": "EPSG:4326",
        },
        {
            "collection": "https://example.com/collections/test",
            "sortBy": ["name"],
        },
    ]
)
def test_collection_input_invalid(input_data):
    # type: (JSON) -> None
    """
    Validate that the invalid definition for a ``collection`` input raises against the schema and filter language.
    """
    with pytest.raises(colander.Invalid):
        sd.ExecuteCollectionInput().deserialize(input_data)


@pytest.mark.parametrize(
    ["filter_data", "filter_lang"],
    [
        ("test = bad", "cql2-json"),
        ("test = bad", "cql-json"),
        ("test = bad", "jfe"),
        ({"test": "bad"}, "cql-text"),
        ({"test": "bad"}, "cql2-text"),
        ({"test": "bad"}, "ecql"),
        ({"test": "bad"}, "cql"),
        ({"test": "bad"}, "simple-cql"),
        ({"test": "bad"}, "fes"),
    ]
)
def test_collection_input_filter_parsing_error(filter_data, filter_lang):
    input_data = {
        "collection": "https://example.com/collections/test",
        "filter": filter_data,
        "filter-lang": filter_lang,
    }
    with pytest.raises(colander.Invalid) as exc:
        sd.FilterSchema.parse.__wrapped__.cache_clear()  # noqa
        sd.ExecuteCollectionInput().deserialize(input_data)
    assert exc.value.msg == "Invalid filter expression could not be parsed against specified language."


def test_collection_input_filter_interpreter_error():
    input_data = {
        "collection": "https://example.com/collections/test",
        "filter": {},
    }
    with mock.patch("weaver.wps_restapi.swagger_definitions.FilterSchema.validate", return_value=None):
        with pytest.raises(colander.Invalid) as exc:
            sd.ExecuteCollectionInput().deserialize(input_data)
    assert exc.value.msg == "Invalid filter expression could not be interpreted."


def test_collection_input_filter_unresolved_error():
    with pytest.raises(colander.Invalid) as exc:
        sd.FilterSchema().parse({}, "unknown-language")  # noqa
    assert exc.value.msg == "Unresolved filter expression language."


def test_collection_input_filter_missing():
    assert sd.FilterSchema().deserialize({}) in [colander.drop, {}]
