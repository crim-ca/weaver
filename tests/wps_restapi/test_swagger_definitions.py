import uuid

import colander
import pytest

from weaver.formats import EDAM_NAMESPACE, EDAM_NAMESPACE_URL, IANA_NAMESPACE, IANA_NAMESPACE_URL, ContentType
from weaver.processes.constants import CWL_NAMESPACE, CWL_NAMESPACE_URL, CWL_NAMESPACE_WEAVER, CWL_NAMESPACE_WEAVER_URL
from weaver.wps_restapi import swagger_definitions as sd


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


@pytest.mark.parametrize("test_value", [
    {},
    {IANA_NAMESPACE: IANA_NAMESPACE_URL},
    {IANA_NAMESPACE: IANA_NAMESPACE_URL, EDAM_NAMESPACE: EDAM_NAMESPACE_URL},
    {IANA_NAMESPACE: IANA_NAMESPACE_URL, CWL_NAMESPACE: CWL_NAMESPACE_URL},
    {CWL_NAMESPACE: CWL_NAMESPACE_URL, CWL_NAMESPACE_WEAVER: CWL_NAMESPACE_WEAVER_URL},
    {CWL_NAMESPACE: CWL_NAMESPACE_URL, "random": "https://random.com"},
])
def test_cwl_namespaces(test_value):
    result = sd.CWLNamespaces().deserialize(test_value)
    assert result == test_value


@pytest.mark.parametrize("test_value", [
    {CWL_NAMESPACE: "bad"},
    {CWL_NAMESPACE: EDAM_NAMESPACE_URL},
    {"random": "bad"},
    {"random": 12345},
])
def test_cwl_namespaces_invalid_url(test_value):
    with pytest.raises(colander.Invalid):
        sd.CWLNamespaces().deserialize(test_value)


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
