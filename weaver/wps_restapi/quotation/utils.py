import logging
from typing import TYPE_CHECKING

from pyramid.settings import asbool

from weaver.config import WeaverFeature, get_weaver_configuration
from weaver.utils import get_settings

if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer


LOGGER = logging.getLogger(__name__)


def check_quotation_supported(container):
    # type: (AnySettingsContainer) -> bool
    """
    Request view decorator that validates the instance configuration permits the quotation extension.

    .. seealso::
        https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/quotation
    """

    settings = get_settings(container)
    weaver_quotes = asbool(settings.get("weaver.quotation", True))
    if not weaver_quotes:
        LOGGER.info("Unsupported quotation requests disabled for this instance.")
        return False
    weaver_config = get_weaver_configuration(settings)
    if weaver_config not in WeaverFeature.QUOTING:
        LOGGER.info(f"Unsupported quotation requests for configuration '%s'.", weaver_config)
        return False
    return True
