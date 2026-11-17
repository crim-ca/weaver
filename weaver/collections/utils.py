"""
Utilities shared by collection output representations.
"""
from typing import TYPE_CHECKING

from pyramid.settings import asbool

from weaver.utils import get_settings

if TYPE_CHECKING:
    from typing import Optional

    from weaver.typedefs import URL, AnySettingsContainer


def collection_enabled(container=None):
    # type: (Optional[AnySettingsContainer]) -> bool
    """
    Indicates if generation of collection representations of :term:`Job` results is enabled.
    """
    settings = get_settings(container) or {}
    return asbool(settings.get("weaver.job_collection", True))


def collection_api_url(container=None, staging=False):
    # type: (Optional[AnySettingsContainer], bool) -> Optional[URL]
    """
    Obtains the configured :term:`STAC` API URL for collection publication, if any.

    :param container: Employed to retrieve application settings.
    :param staging: Obtain the URL used to publish contents, falling back to the public URL.
    """
    settings = get_settings(container) or {}
    public = str(settings.get("weaver.job_collection_stac_api_public_url") or "").rstrip("/")
    staging_url = str(settings.get("weaver.job_collection_stac_api_staging_url") or "").rstrip("/")
    if staging:
        return staging_url or public or None
    return public or None
