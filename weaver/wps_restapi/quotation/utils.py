import logging
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPNotFound
from pyramid.settings import asbool

from weaver.config import WeaverFeature, get_weaver_configuration
from weaver.database import get_db
from weaver.exceptions import QuoteNotFound
from weaver.store.base import StoreQuotes
from weaver.utils import get_settings

if TYPE_CHECKING:
    from weaver.datatype import Quote
    from weaver.typedefs import AnyRequestType, AnySettingsContainer


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
        LOGGER.info("Unsupported quotation requests for configuration '%s'.", weaver_config)
        return False
    return True


def get_quote(request):
    # type: (AnyRequestType) -> Quote
    """
    Obtain the referenced :term:`Quote` by the request with validation.

    :param request:
    :return: Matched quote.
    :raises HTTPNotFound: If the quote could not be found.
    """
    quote_id = request.matchdict.get("quote_id")
    store = get_db(request).get_store(StoreQuotes)
    try:
        quote = store.fetch_by_id(quote_id)
    except QuoteNotFound:
        raise HTTPNotFound("Could not find quote with specified 'quote_id'.")
    return quote
