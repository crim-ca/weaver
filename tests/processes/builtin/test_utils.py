import itertools

import pytest

from weaver.processes.builtin.utils import is_geojson_url, is_netcdf_url, validate_reference


@pytest.mark.parametrize(
    "invalid_url",
    [
        object(),
        True,
        "no",
        "https://example.com/",
        "https://example.com/netcdf.nc",
    ],
)
def test_is_geojson_url_invalid(invalid_url):
    assert not is_geojson_url(invalid_url)


@pytest.mark.parametrize(
    "invalid_url",
    [
        "https://example.com/test.json",
        "https://example.com/nested/dir/test.json",
    ],
)
def test_is_geojson_url_valid(invalid_url):
    assert is_geojson_url(invalid_url)


@pytest.mark.parametrize(
    "invalid_url",
    [
        object(),
        True,
        "no",
        "https://example.com/",
    ],
)
def test_is_netcdf_url_invalid(invalid_url):
    assert not is_netcdf_url(invalid_url)


@pytest.mark.parametrize(
    "invalid_url",
    [
        "https://example.com/netcdf.nc",
        "https://example.com/nested/dir/netcdf.nc",
    ],
)
def test_is_netcdf_url_valid(invalid_url):
    assert is_netcdf_url(invalid_url)


@pytest.mark.parametrize(
    ["invalid_url", "is_file"],
    itertools.chain(
        itertools.product(
            [
                object(),
                True,
                "no",
            ],
            [True, False],
        ),
        [
            ("https://example.com/", True),
            ("https://example.com/test.json", False)
        ],
    )
)
def test_validate_reference_invalid(invalid_url, is_file):
    with pytest.raises((TypeError, ValueError)):  # type: ignore
        validate_reference(invalid_url, is_file)


@pytest.mark.parametrize(
    ["invalid_url", "is_file"],
    [
        ("https://example.com/", False),
        ("https://example.com/test.json", True)
    ],
)
def test_validate_reference_valid(invalid_url, is_file):
    validate_reference(invalid_url, is_file)  # not raised
