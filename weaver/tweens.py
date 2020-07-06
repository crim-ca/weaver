import logging
import sys
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPException, HTTPInternalServerError, HTTPRedirection, HTTPSuccessful
from pyramid.tweens import EXCVIEW, INGRESS

from weaver.owsexceptions import OWSException, OWSNotImplemented
from weaver.utils import fully_qualified_name

if TYPE_CHECKING:
    from typing import Union

LOGGER = logging.getLogger(__name__)

OWS_TWEEN_HANDLED = "OWS_TWEEN_HANDLED"


# FIXME:
#   https://github.com/crim-ca/weaver/issues/215
#   define common Exception classes that won't require this type of conversion
def error_repr(http_err):
    # type: (Union[HTTPException, OWSException, Exception]) -> str
    """
    Returns a cleaned up representation string of the HTTP error, but with similar and even extended details to
    facilitate later debugging.
    """
    err_type = type(http_err).__name__
    if not isinstance(http_err, (HTTPException, OWSException)):
        return "({}) {!s}".format(err_type, http_err)
    err_code = getattr(http_err, "code", getattr(http_err, "status_code", 500))
    err_repr = "({}) <{}> {!s}".format(err_type, err_code, http_err)
    return err_repr


def ows_response_tween(request, handler):
    """Tween that wraps any API request with appropriate dispatch of error conversion to handle formatting."""
    exc_log_lvl = logging.WARNING
    try:
        result = handler(request)
        if hasattr(handler, OWS_TWEEN_HANDLED):
            if isinstance(result, Exception) and not isinstance(result, (HTTPSuccessful, HTTPRedirection)):
                raise result    # let the previous tween handler handle this case
        return result
    # NOTE:
    #   Handle exceptions from most explicit definitions to least explicit.
    #   Exceptions in 'weaver.exceptions' sometimes derive from 'OWSException' to provide additional details.
    #   Furthermore, 'OWSException' have extensive details with references to 'HTTPException' and 'pywps.exceptions'.
    except HTTPException as err:
        LOGGER.debug("http exception -> ows exception response.")
        # Use the same json formatter than OWSException
        raised_error = err
        raised_error._json_formatter = OWSException.json_formatter
        return_error = raised_error
        exc_info_err = False
        exc_log_lvl = logging.WARNING if err.status_code < 500 else logging.ERROR
    except OWSException as err:  # could be 'WeaverException' with 'OWSException' base
        LOGGER.debug("direct ows exception response")
        raised_error = err
        return_error = err
        exc_info_err = False
    except NotImplementedError as err:
        LOGGER.debug("not implemented error -> ows exception response")
        raised_error = err
        return_error = OWSNotImplemented(str(err))
        exc_info_err = sys.exc_info()
    except Exception as err:
        LOGGER.debug("unhandled %s exception -> ows exception response", type(err).__name__)
        raised_error = err
        return_error = OWSException(detail=str(err), status=HTTPInternalServerError)
        exc_info_err = sys.exc_info()
        exc_log_lvl = logging.ERROR
    # FIXME:
    #   https://github.com/crim-ca/weaver/issues/215
    #   convivial generation of this repr format should be directly in common exception class
    err_msg = "\n  Cause:  [{} {}]".format(request.method, request.url)
    raised_error_repr = error_repr(raised_error)
    if raised_error != return_error:
        err_msg += "\n  Raised: [{}]\n  Return: [{}]".format(raised_error_repr, error_repr(return_error))
    else:
        err_msg += "\n  Raised: [{}]".format(raised_error_repr)
    LOGGER.log(exc_log_lvl, "Handled request exception:%s", err_msg, exc_info=exc_info_err)
    LOGGER.debug("Handled request details:\n%s\n%s", raised_error_repr, getattr(raised_error, "text", ""))
    return return_error


def ows_response_tween_factory_excview(handler, registry):  # noqa: F811
    """A tween factory which produces a tween which transforms common exceptions into OWS specific exceptions."""
    return lambda request: ows_response_tween(request, handler)


def ows_response_tween_factory_ingress(handler, registry):  # noqa: F811
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
