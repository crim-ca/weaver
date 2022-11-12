"""
Generic schema tests.
"""
import colander
import pytest

from weaver.formats import ContentType
from weaver.wps_restapi import swagger_definitions as sd


def test_process_id_schemas():
    test_valid_ids = [
        "valid-slug-id",
        "valid_underscores",
        "valid_lower-and_CAP_MiXeD"
    ]
    test_invalid_ids = [
        "not valid to have spaces",
        "not-valid-!!!-characters",
        "not-valid/separators"
    ]
    for _id in test_valid_ids:
        assert sd.ProcessIdentifier().deserialize(_id) == _id
    for i, _id in enumerate(test_invalid_ids):
        try:
            sd.ProcessIdentifier().deserialize(_id)
        except colander.Invalid:
            pass
        else:
            pytest.fail(f"Expected process ID to be raised as invalid: (test: {i}, id: {_id})")


@pytest.mark.parametrize("url, schema, valid", [
    # valid references
    ("https://s3.region-name.amazonaws.com/bucket/file-key.txt", sd.ReferenceURL(), True),
    ("https://s3.amazonaws.com/bucket/file-key.txt", sd.ReferenceURL(), True),
    ("s3://bucket/5ca1093e-523d-4294-892d-d52d4819ef29/file-key.txt", sd.ReferenceURL(), True),
    ("s3://bucket/file-key.txt", sd.ReferenceURL(), True),
    ("file:///local-file/location.txt", sd.ReferenceURL(), True),
    ("/local-file/location.txt", sd.ReferenceURL(), True),
    ("http://some-location.org/example", sd.URL(), True),
    ("http://localhost:4002/processes", sd.URL(), True),
    ("https://some-location.org/somewhere_with_underscores", sd.URL(), True),
    ("https://some-location.org/somewhere/very/deep.txt", sd.URL(), True),
    ("https://some-location.org/somewhere/without/extension", sd.URL(), True),
    # following are invalid because they are plain URL
    # they are valid only when specialized to FileURL
    ("s3://remote-bucket/", sd.URL(), False),
    ("s3://remote-bucket/", sd.ReferenceURL(), True),
    # following are always invalid because incorrectly formatted
    ("file:/missing/slash.txt", sd.URL(), False),
    ("file:/missing/slash.txt", sd.ReferenceURL(), False),
    ("file://missing/slash.txt", sd.URL(), False),
    ("file://missing/slash.txt", sd.ReferenceURL(), False),
    ("file:///too/many//slash.txt", sd.URL(), False),
    ("file:///too/many//slash.txt", sd.ReferenceURL(), False),
    ("file:////too/many/slash.txt", sd.URL(), False),
    ("file:////too/many/slash.txt", sd.ReferenceURL(), False),
    ("http:///too.com/many/slash.txt", sd.URL(), False),
    ("http:///too.com/many/slash.txt", sd.ReferenceURL(), False),
    ("http://too.com//many/slash.txt", sd.URL(), False),
    ("http://too.com//many/slash.txt", sd.ReferenceURL(), False),
    ("http://too.com/many//slash.txt", sd.URL(), False),
    ("http://too.com/many//slash.txt", sd.ReferenceURL(), False),
    ("missing/first/slash.txt", sd.URL(), False),
    ("missing/first/slash.txt", sd.ReferenceURL(), False),
    ("s3://missing-dir-file-key-slash", sd.URL(), False),
    ("s3://missing-dir-file-key-slash", sd.ReferenceURL(), False),
])
def test_url_schemes(url, schema, valid):
    if valid:
        try:
            assert schema.deserialize(url) == url
        except colander.Invalid as invalid:
            pytest.fail(f"Raised invalid URL when expected to be valid for '{invalid.node}' with [{url}]")
    else:
        try:
            schema.deserialize(url)
        except colander.Invalid:
            pass
        else:
            pytest.fail(
                f"Expected URL to be raised as invalid for '{schema.__class__}' with "
                f"invalid format or non-file reference: [{url}]"
            )


def test_format_variations():
    """
    Test format parsing for deployment payload.

    .. versionchanged:: 4.11
        Omitted field ``default: False`` not added automatically *during deployment* anymore.
        It remains there if provided though, and will be added once again during process description parsing.

    .. seealso::
        Validation of above mentioned behavior is accomplished with
        :func:`tests.functional.test_wps_package.WpsPackageAppTest.test_deploy_process_io_no_format_default`.
    """
    format_schema = sd.DeploymentFormat()
    schema = f"https://www.iana.org/assignments/media-types/{ContentType.APP_JSON}"
    test_valid_fmt_deploy = [
        (
            {"mimeType": ContentType.APP_JSON},
            {"mimeType": ContentType.APP_JSON}),
        (
            {"mediaType": ContentType.APP_JSON},
            {"mediaType": ContentType.APP_JSON}),
        (
            {"mediaType": ContentType.APP_JSON, "maximumMegabytes": 200},
            {"mediaType": ContentType.APP_JSON, "maximumMegabytes": 200}),
        (
            {"mediaType": ContentType.APP_JSON, "maximumMegabytes": None},
            {"mediaType": ContentType.APP_JSON}),
        (
            {"mediaType": ContentType.APP_JSON, "default": False},
            {"mediaType": ContentType.APP_JSON, "default": False}),
        (
            {"mediaType": ContentType.APP_JSON, "default": True},
            {"mediaType": ContentType.APP_JSON, "default": True}),
        (
            {"mediaType": ContentType.APP_JSON, "schema": None},
            {"mediaType": ContentType.APP_JSON}),
        (
            {"mediaType": ContentType.APP_JSON, "schema": schema},
            {"mediaType": ContentType.APP_JSON, "schema": schema}),
    ]
    for fmt, res in test_valid_fmt_deploy:
        try:
            assert format_schema.deserialize(fmt) == res
        except colander.Invalid:
            pytest.fail(f"Expected format to be valid: [{fmt}]")
