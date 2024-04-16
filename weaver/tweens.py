import logging
import sys
from typing import TYPE_CHECKING

import colander
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

from weaver.formats import ContentType, guess_target_format
from weaver.owsexceptions import OWSException, OWSNotImplemented
from weaver.utils import clean_json_text_body, fully_qualified_name, get_settings
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

    Supported values are defined by :py:data:`SUPPORTED_ACCEPT_TYPES` and for the given context of API or UI.

    :raises HTTPNotAcceptable: if desired ``Accept`` or ``format`` specifier of content-type is not supported.
    """
    def validate_format(request):
        # type: (PyramidRequest) -> AnyViewResponse
        """
        Validates the specified request according to its ``Accept`` header or ``format`` query, ignoring UI related
        routes that require more content-types than the ones supported by the API for displaying purposes of other
        elements (styles, images, etc.).
        """
        try:
            content_type = guess_target_format(request)
            sd.AcceptHeader().deserialize(content_type)  # raise on invalid/unacceptable
        except colander.Invalid as invalid:
            raise HTTPNotAcceptable(json={
                "type": "NotAcceptable",
                "title": "Response format is not acceptable.",
                "detail": "Specified response format by query parameter or Accept header is not supported.",
                "status": HTTPNotAcceptable.code,
                "cause": invalid.value,
            })
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


# FIXME:
#   - auto resolve predefined formatter (mako) based on mapped router + cornice service spec
#   - apply auto-converters based on mapped router path + cornice service spec
#   - allow/disallow (by service config?) some specific path formats (ex: /package CWL in JSON/YAML ok, but not others)
def http_apply_response_format_tween_factory(handler, registry):    # noqa: F811
    # type: (ViewHandler, Registry) -> Callable[[PyramidRequest], AnyViewResponse]
    """
    Tween factory that applies the request ``Accept`` header according to the requested format.

    Format can be provided by ``Accept`` header or ``format`` query. The resulting request will unify the format
    under the ``Accept`` header, such that a single reference can be considered by the following code.

    If validation of allowed ``Accept`` header values must be done, it is expected to be validated by
    :func:`cornice.validators.colander_headers_validator` or :func:`cornice.validators.colander_validator`
    with the relevant `validators` definition applied onto the :class:`cornice.service.Service` decorating
    the specific view.

    Since browsers will typically inject :term:`HTML`-related media-types in the ``Accept` header, specific
    combinations of browser ``User-Agent`` will ignore those values to provide :term:`JSON` by default, unless
    an explicit ``text/html`` or ``f=html`` is specified. In the case of non-browser ``User-Agent``, headers will
    be interpreted normally.
    """
    def apply_format(request):
        # type: (PyramidRequest) -> HTTPException
        content_type = guess_target_format(request)
        # NOTE:
        # enforce the accept header in case it was specified with format query, since some renderer implementations
        # will afterward erroneously overwrite the 'content-type' value that we enforce when converting the response
        # from the HTTPException. See:
        #   - https://github.com/Pylons/webob/issues/204
        #   - https://github.com/Pylons/webob/issues/238
        #   - https://github.com/Pylons/pyramid/issues/1344
        request.accept = content_type
        resp = handler(request)  # no exception when EXCVIEW tween is placed under this tween
        # return routes already converted (pyramid already generated response)
        if not isinstance(resp, HTTPException):
            return resp
        # forward any headers such as session cookies to be applied
        resp_kwargs = {"headers": resp.headers}
        # patch any invalid content-type that should have been validated
        if content_type not in sd.AcceptHeader.validator.choices:
            content_type = ContentType.APP_JSON
        ###return generate_response_http_format(type(resp), resp_kwargs, resp.text, content_type)
        return resp
    return apply_format


# FIXME:
#   https://github.com/crim-ca/weaver/issues/215
#   define common Exception classes that won't require this type of conversion
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
    # in some cases, cornice will wrap HTTPError incorrectly without 'detail'
    # (see https://github.com/Cornices/cornice/issues/586)
    try:
        err_repr = str(http_err)
    except (AttributeError, NameError):
        err_repr = err_type
    try:
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
#HTTP_FORMAT_VALIDATE = fully_qualified_name(http_validate_response_format_tween_factory)
HTTP_FORMAT_RESPONSE = fully_qualified_name(http_apply_response_format_tween_factory)


def includeme(config):
    # type: (Configurator) -> None

    # using 'INGRESS' to run `weaver.wps_restapi.api` views that fix HTTP code before OWS response
    config.add_tween(OWS_RESPONSE_INGRESS, under=INGRESS)

    # intermediate tweens to modify the request/response
    #config.add_tween(HTTP_FORMAT_VALIDATE, over=MAIN)
    config.add_tween(HTTP_FORMAT_RESPONSE, over=OWS_RESPONSE_EXCVIEW)

    # using 'EXCVIEW' to run over any other 'valid' exception raised to adjust formatting and log
    config.add_tween(OWS_RESPONSE_EXCVIEW, over=EXCVIEW)
