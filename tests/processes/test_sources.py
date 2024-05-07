from weaver.processes.sources import retrieve_data_source_url
from weaver.utils import get_settings


def test_retrieve_data_source_url_no_settings():
    """
    Validate that data sources lookup without settings does not raise an error.

    When using a package definition with the :term:`CLI` or Python client,
    the :mod:`pyramid` registry is undefined, potentially leading to an error
    since the settings cannot be resolved as usually in the :term:`API` context.
    """
    assert get_settings() is None, "Settings should resolve to None for this test."
    retrieve_data_source_url(None)
