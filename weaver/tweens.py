import colander
import logging
import sys
from typing import TYPE_CHECKING

from cornice.renderer import JSONError
from pyramid.httpexceptions import (
    HTTPException,
    HTTPInternalServerError,
    HTTPNotAcceptable,
    HTTPRedirection,
    HTTPSuccessful
)
from pyramid.settings import asbool
from pyramid.tweens import EXCVIEW, INGRESS, MAIN

from weaver.formats import ContentType, guess_target_format, repr_json
from weaver.owsexceptions import OWSException, OWSNotImplemented
from weaver.utils import bytes2str, clean_json_text_body, fully_qualified_name, get_settings
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, Optional, Type, Union

    from pyramid.config import Configurator
    from pyramid.registry import Registry

    from weaver.typedefs import JSON, AnyViewResponse, PyramidRequest, ViewHandler

LOGGER = logging.getLogger(__name__)

OWS_TWEEN_HANDLED = "OWS_TWEEN_HANDLED"


def http_validate_response_format_tween_factory(handler, registry):    # noqa: F811
    # type: (ViewHandler, Registry) -> ViewHandler
    """
    Tween factory that validates that the specified request ``Accept`` header or format queries (if any) is supported.

    .. note::
        This tween limits itself to the validation of :term:`HTML` support according to ``weaver.wps_restapi_html``
        configuration. Other endpoint-specific format or Content-Type support are handled and validated as per their
        corresponding endpoint :mod:`cornice` service definitions, which are also represented in the generated `OpenAPI`
        specification.

    :raises HTTPNotAcceptable: if desired ``Accept`` or ``format`` specifier of content-type is not supported.
    """
    def validate_format(request):
        # type: (PyramidRequest) -> AnyViewResponse
        """
        Validates the specified request according to its ``Accept`` header or ``format`` query for :term:`HTML`.
        """
        content_type = guess_target_format(request)
        if content_type == ContentType.TEXT_HTML:
            settings = get_settings(request)
            html_acceptable = asbool(settings.get("weaver.wps_restapi_html", True))
            if not html_acceptable:
                raise HTTPNotAcceptable(json={
                    "type": "NotAcceptable",
                    "title": "Response format is not acceptable.",
                    "detail": "This 'OGC API - Processes' implementation does not support HTML responses.",
                    "status": HTTPNotAcceptable.code,
                    "cause": {"weaver.wps_restapi_html": False}
                })
        return handler(request)
    return validate_format


def http_apply_response_format_tween_factory(handler, registry):    # noqa: F811
    # type: (ViewHandler, Registry) -> Callable[[PyramidRequest], AnyViewResponse]
    """
    Tween factory that applies the request ``Accept`` header according to the requested format for the response.

    The *requested format* in this case takes into account Web-Browsers automatically applying ``Accept`` with a
    combination of *visual rendering* headers, notably with ``text/html``. In such case, the format is considered
    to auto-resolve with the *default* response format of the specific endpoint.
    """
    def apply_format(request):
        # type: (PyramidRequest) -> HTTPException
        content_type, format_source = guess_target_format(request, return_source=True)
        # NOTE:
        #   Enforce the accept header in case it was specified with format query, since some renderer implementations
        #   will afterward erroneously overwrite the 'content-type' value when converting the HTTPException response.
        #   See:
        #       - https://github.com/Pylons/webob/issues/204
        #       - https://github.com/Pylons/webob/issues/238
        #       - https://github.com/Pylons/pyramid/issues/1344
        #   It is important to leave the 'Accept' header as-is if provided directly (or inferred without format query).
        #   Otherwise, we could be undoing some pre-resolutions performed during HTTP redirects between OWS/REST views.
        if format_source == "query":
            request.accept = content_type
        if format_source == "default":
            request.accept = "*/*"  # let per-endpoint resolution of their default
        resp = handler(request)
        return resp
    return apply_format


# FIXME:
#   https://github.com/crim-ca/weaver/issues/215
#   define common Exception classes that won't require this type of conversion
# FIXME:
#   Many view/error handlers will add details into 'request.errors' (see 'cornice.pyramidhook' for example).
#   Use them to better populate the error view with the cause (eg: specific Header, Body, Path, etc. that raised).
def error_repr(http_err):
    # type: (Union[HTTPException, OWSException, Exception]) -> str
    """
    Returns a cleaned up representation string of the HTTP error.

    Similar and even extended details relative to the HTTP error message are added to facilitate later debugging.
    """
    err_type = type(http_err).__name__
    if not isinstance(http_err, (HTTPException, OWSException)):
        return f"({err_type}) {http_err!s}"
    err_code = getattr(http_err, "code", getattr(http_err, "status_code", 500))
    err_repr = str(http_err)
    try:
        if not err_repr:
            err_repr = bytes2str(http_err.body or "")
        # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
        #        specific cleanup in case of string representation of colander.Invalid to help debug logged errors
        err_repr = clean_json_text_body(err_repr, remove_newlines=False, remove_indents=False)
        if "Invalid schema:" in err_repr:
            err_repr = err_repr.replace("Invalid schema: [", "Invalid schema: [\n")[:-1] + "\n]"
            err_repr = err_repr.replace(". 'Errors for each case:", ".\n Errors for each case:")
    except Exception:  # noqa: W0703 # nosec: B110
        pass
    return f"({err_type}) <{err_code}> {err_repr!s}"


def ows_response_tween(request, handler):
    # type: (PyramidRequest, ViewHandler) -> AnyViewResponse
    """
    Tween that wraps any API request with appropriate dispatch of error conversion to handle formatting.
    """
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
    except JSONError as err:
        # FIXME: https://github.com/Cornices/cornice/issues/586
        #   Workaround to handle missing 'detail' attribute  and invalid 'code' value under 'JSONError'
        #   which derives from 'HTTPException', but doesn't actually initialize it properly.
        raised_error = err
        raised_error.code = err.status_code
        raised_error.title = err.status.split(" ", 1)[-1]
        raised_error.request = request
        HTTPException.__init__(raised_error, json={
            "type": raised_error.title.replace(" ", ""),
            "title": raised_error.title,
            "detail": bytes2str(request.errors[0]["description"]),
            "status": raised_error.status_code,
        })
        return_error = raised_error
        exc_info_err = False
        exc_log_lvl = logging.WARNING if err.status_code < 500 else logging.ERROR
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
    err_msg = f"\n  Cause: [{request.method} {request.url}]"
    raised_error_repr = error_repr(raised_error)
    if raised_error != return_error:
        err_msg += f"\n  Error: [{raised_error_repr}]\n  Return: [{error_repr(return_error)}]"
    else:
        err_msg += f"\n  Error: [{raised_error_repr}]"
    LOGGER.log(exc_log_lvl, "Handled request exception:%s", err_msg, exc_info=exc_info_err)
    LOGGER.debug("Handled request details:\n%s\n%s", raised_error_repr, getattr(raised_error, "text", ""))
    return return_error


def ows_response_tween_factory_excview(handler, registry):  # noqa: F811
    # type: (ViewHandler, Registry) -> ViewHandler
    """
    Tween factory which produces a tween which transforms common exceptions into OWS specific exceptions.
    """
    return lambda request: ows_response_tween(request, handler)


def ows_response_tween_factory_ingress(handler, registry):  # noqa: F811
    # type: (ViewHandler, Registry) -> ViewHandler
    """
    Tween factory which produces a tween which transforms common exceptions into OWS specific exceptions.
    """
    def handle_ows_tween(request):
        # type: (PyramidRequest) -> AnyViewResponse

        # because the EXCVIEW will also wrap any exception raised that should before be handled by OWS response
        # to allow conversions to occur, use a flag that will re-raise the result
        setattr(handler, OWS_TWEEN_HANDLED, True)
        return ows_response_tween(request, handler)
    return handle_ows_tween


# names must differ to avoid conflicting configuration error
OWS_RESPONSE_EXCVIEW = fully_qualified_name(ows_response_tween_factory_excview)
OWS_RESPONSE_INGRESS = fully_qualified_name(ows_response_tween_factory_ingress)
HTTP_FORMAT_VALIDATE = fully_qualified_name(http_validate_response_format_tween_factory)
HTTP_FORMAT_RESPONSE = fully_qualified_name(http_apply_response_format_tween_factory)


def includeme(config):
    # type: (Configurator) -> None

    # using 'INGRESS' to run `weaver.wps_restapi.api` views that fix HTTP code before OWS response
    config.add_tween(OWS_RESPONSE_INGRESS, under=INGRESS)

    # intermediate tweens to modify the request/response
    config.add_tween(HTTP_FORMAT_VALIDATE, over=MAIN)
    config.add_tween(HTTP_FORMAT_RESPONSE, over=OWS_RESPONSE_EXCVIEW)

    # using 'EXCVIEW' to run over any other 'valid' exception raised to adjust formatting and log
    config.add_tween(OWS_RESPONSE_EXCVIEW, over=EXCVIEW)
