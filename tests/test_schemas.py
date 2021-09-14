"""
Generic schema tests.
"""
import colander
import pytest

from weaver.formats import CONTENT_TYPE_APP_JSON
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
            pytest.fail("Expected process ID to be raised as invalid: (test: {}, id: {})".format(i, _id))


def test_url_schemes():
    file_url = sd.ReferenceURL()
    href_url = sd.URL()
    test_file_valid = [
        "https://s3.region-name.amazonaws.com/bucket/file-key.txt",
        "https://s3.amazonaws.com/bucket/file-key.txt",
        "s3://bucket/5ca1093e-523d-4294-892d-d52d4819ef29/file-key.txt",
        "s3://bucket/file-key.txt"
        "file:///local-file/location.txt",
        "/local-file/location.txt",
    ]
    test_href_valid = [
        "http://some-location.org/example",
        "http://localhost:4002/processes",
        "https://some-location.org/somewhere_with_underscores",
        "https://some-location.org/somewhere/very/deep.txt",
        "https://some-location.org/somewhere/without/extension",
    ]
    # following are invalid because they are plain URL
    # they are valid only when specialized to FileURL
    test_href_invalid_file_valid = [
        "s3://remote-bucket"
    ]
    # following are always invalid because incorrectly formatted
    test_href_invalid_always = [
        "file:/missing/slash.txt",
        "file://missing/slash.txt",
        "file:////too/many/slash.txt",
        "missing/first/slash.txt",
    ]

    url = None
    try:
        for url in test_href_valid:
            assert href_url.deserialize(url) == url
        for url in test_file_valid:
            assert file_url.deserialize(url) == url
        for url in test_href_invalid_file_valid:
            assert file_url.deserialize(url) == url
    except colander.Invalid as invalid:
        pytest.fail("Raised invalid URL when expected to be valid for '{}' with [{}]".format(invalid.node, url))
    for url in test_href_invalid_file_valid:
        try:
            href_url.deserialize(url)
        except colander.Invalid:
            pass
        else:
            pytest.fail("Expected URL to be raised as invalid for non-file reference: [{}]".format(url))
    for url in test_href_invalid_always:
        try:
            href_url.deserialize(url)
        except colander.Invalid:
            pass
        else:
            pytest.fail("Expected URL to be raised as invalid for incorrectly formatted reference: [{}]".format(url))


def test_format_variations():
    format_schema = sd.DeploymentFormat()
    schema = "https://www.iana.org/assignments/media-types/{}".format(CONTENT_TYPE_APP_JSON)
    test_valid_fmt_deploy = [
        (
            {"mimeType": CONTENT_TYPE_APP_JSON},
            {"mimeType": CONTENT_TYPE_APP_JSON, "default": False}),
        (
            {"mediaType": CONTENT_TYPE_APP_JSON},
            {"mediaType": CONTENT_TYPE_APP_JSON, "default": False}),
        (
            {"mediaType": CONTENT_TYPE_APP_JSON, "maximumMegabytes": 200},
            {"mediaType": CONTENT_TYPE_APP_JSON, "maximumMegabytes": 200, "default": False}),
        (
            {"mediaType": CONTENT_TYPE_APP_JSON, "maximumMegabytes": None},
            {"mediaType": CONTENT_TYPE_APP_JSON, "default": False}),
        (
            {"mediaType": CONTENT_TYPE_APP_JSON, "default": False},
            {"mediaType": CONTENT_TYPE_APP_JSON, "default": False}),
        (
            {"mediaType": CONTENT_TYPE_APP_JSON, "default": True},
            {"mediaType": CONTENT_TYPE_APP_JSON, "default": True}),
        (
            {"mediaType": CONTENT_TYPE_APP_JSON, "schema": None},
            {"mediaType": CONTENT_TYPE_APP_JSON, "default": False}),
        (
            {"mediaType": CONTENT_TYPE_APP_JSON, "schema": schema},
            {"mediaType": CONTENT_TYPE_APP_JSON, "schema": schema, "default": False}),
    ]
    for fmt, res in test_valid_fmt_deploy:
        try:
            assert format_schema.deserialize(fmt) == res
        except colander.Invalid:
            pytest.fail("Expected format to be valid: [{}]".format(fmt))
