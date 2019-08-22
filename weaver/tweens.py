from pyramid.tweens import INGRESS, EXCVIEW, MAIN
from pyramid.httpexceptions import HTTPSuccessful, HTTPRedirection, HTTPException, HTTPInternalServerError
from weaver.owsexceptions import OWSException, OWSNotImplemented  # noqa: F401
from weaver.utils import fully_qualified_name
import logging
LOGGER = logging.getLogger(__name__)

OWS_TWEEN_HANDLED = "OWS_TWEEN_HANDLED"


def ows_response_tween(request, handler):
    try:
        result = handler(request)
        if hasattr(handler, OWS_TWEEN_HANDLED):
            if isinstance(result, Exception) and not isinstance(result, (HTTPSuccessful, HTTPRedirection)):
                raise result    # let the previous tween handler handle this case
        return result
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
    def handle_ows_tween(request):
        # because the EXCVIEW will also wrap any exception raised that should before be handled by OWS response
        # to allow conversions to occur, use a flag that will re-raise the result
        setattr(handler, OWS_TWEEN_HANDLED, True)
        return ows_response_tween(request, handler)
    return handle_ows_tween


# names must differ to avoid conflicting configuration error
OWS_RESPONSE_EXCVIEW = fully_qualified_name(ows_response_tween_factory_excview)
OWS_RESPONSE_INGRESS = fully_qualified_name(ows_response_tween_factory_ingress)


def includeme(config):
    # using 'INGRESS' to run `weaver.wps_restapi.api` views that fix HTTP code before OWS response
    config.add_tween(OWS_RESPONSE_INGRESS, under=INGRESS)
    # using 'EXCVIEW' to run over any other 'valid' exception raised to adjust formatting and log
    config.add_tween(OWS_RESPONSE_EXCVIEW, over=EXCVIEW)
