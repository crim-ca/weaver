from pyramid.tweens import INGRESS, EXCVIEW
from pyramid.httpexceptions import HTTPException, HTTPInternalServerError
from weaver.owsexceptions import OWSException, OWSNotImplemented  # noqa: F401
from weaver.utils import fully_qualified_name

import logging
LOGGER = logging.getLogger(__name__)


def ows_response_tween(request, handler):
    try:
        return handler(request)
    except HTTPException as err:
        LOGGER.debug("http exception -> ows exception response.")
        # Use the same json formatter than OWSException
        err._json_formatter = OWSException.json_formatter
        r_err = err
    except OWSException as err:
        LOGGER.debug('direct ows exception response')
        LOGGER.exception("Raised exception: [{!r}]\nReturned exception: {!r}".format(err, err))
        r_err = err
    except NotImplementedError as err:
        LOGGER.debug('not implemented error -> ows exception response')
        r_err = OWSNotImplemented(str(err))
    except Exception as err:
        LOGGER.debug("unhandled {!s} exception -> ows exception response".format(type(err).__name__))
        r_err = OWSException(detail=str(err), status=HTTPInternalServerError)
    LOGGER.exception("Raised exception: [{!r}]\nReturned exception: {!r}".format(err, r_err))
    return r_err


def ows_response_tween_factory_excview(handler, registry):
    """A tween factory which produces a tween which transforms common exceptions into OWS specific exceptions."""
    return lambda request: ows_response_tween(request, handler)


def ows_response_tween_factory_ingress(handler, registry):
    """A tween factory which produces a tween which transforms common exceptions into OWS specific exceptions."""
    return lambda request: ows_response_tween(request, handler)


# names must differ to avoid conflicting configuration error
OWS_RESPONSE_EXCVIEW = fully_qualified_name(ows_response_tween_factory_excview)
OWS_RESPONSE_INGRESS = fully_qualified_name(ows_response_tween_factory_ingress)


def includeme(config):
    # using 'INGRESS' to run `weaver.wps_restapi.api` views that fix HTTP code before OWS response
    config.add_tween(OWS_RESPONSE_INGRESS, under=INGRESS)
    # using 'EXCVIEW' to run after any other 'valid' exception raised to adjust formatting and log
    config.add_tween(OWS_RESPONSE_EXCVIEW, under=EXCVIEW)
