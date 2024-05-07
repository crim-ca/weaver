import pytest
from pyramid.testing import tearDown

from weaver.processes.sources import fetch_data_sources, retrieve_data_source_url
from weaver.utils import get_settings


@pytest.mark.parametrize("settings", [None, {}])
def test_retrieve_data_source_url_no_settings(settings):
    """
    Validate that :term:`Data Source` lookup without settings does not raise an error.

    When using a package definition with the :term:`CLI` or Python client,
    the :mod:`pyramid` registry is undefined, potentially leading to an error
    since the settings cannot be resolved as usually in the :term:`API` context
    (i.e.: :func:`get_settings` can return ``None``).

    However, even if the settings use an alternate resolution method (to avoid ``None``),
    the :term:`Data Source` should raise a relevant error if it could not be resolved when required.
    This ensures that the raised exception is more specific to the actual cause, rather than
    an obscure :class:`AttributeError` or :class:`KeyError` related to settings container.
    """
    tearDown()  # avoid left-over global registry to be found
    assert get_settings() is None, "Settings and Pyramid Registry must resolve to None for this test."
    with pytest.raises(ValueError, match="No data sources"):
        retrieve_data_source_url("", container=settings)


@pytest.mark.parametrize("settings", [None, {}])
def test_fetch_data_sources_no_settings(settings):
    """
    Validate that :term:`Data Source` lookup without settings does not raise an error.

    When using a package definition with the :term:`CLI` or Python client,
    the :mod:`pyramid` registry is undefined, potentially leading to an error
    since the settings cannot be resolved as usually in the :term:`API` context
    (i.e.: :func:`get_settings` can return ``None``).

    However, even if the settings use an alternate resolution method (to avoid ``None``),
    the :term:`Data Source` should raise a relevant error if it could not be resolved when required.
    This ensures that the raised exception is more specific to the actual cause, rather than
    an obscure :class:`AttributeError` or :class:`KeyError` related to settings container.
    """
    tearDown()  # avoid left-over global registry to be found
    assert get_settings() is None, "Settings and Pyramid Registry must resolve to None for this test."
    with pytest.raises(ValueError, match="No data sources"):
        fetch_data_sources(settings)
