import logging
import sys
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPException, HTTPInternalServerError, HTTPRedirection, HTTPSuccessful
from pyramid.tweens import EXCVIEW, INGRESS

from weaver.formats import ContentType, guess_target_format
from weaver.owsexceptions import OWSException, OWSNotImplemented
from weaver.utils import clean_json_text_body, fully_qualified_name
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Callable, Union

    from pyramid.config import Configurator
    from pyramid.registry import Registry

    from weaver.typedefs import AnyViewResponse, PyramidRequest

    ViewHandler = Callable[[PyramidRequest], AnyViewResponse]

LOGGER = logging.getLogger(__name__)

OWS_TWEEN_HANDLED = "OWS_TWEEN_HANDLED"


def validate_accept_header_tween(handler, registry):    # noqa: F811
    # type: (ViewHandler, Registry) -> ViewHandler
    """
    Tween that validates that the specified request ``Accept`` header or format queries (if any) is supported.

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
        sd.AcceptHeader.validator.choices
        if not is_magpie_ui_path(request):
            accept, _ = guess_target_format(request)
            http_msg = s.NotAcceptableResponseSchema.description
            content = get_request_info(request, default_message=http_msg)
            ax.verify_param(accept, is_in=True, param_compare=SUPPORTED_ACCEPT_TYPES,
                            param_name="Accept Header or Format Query",
                            http_error=HTTPNotAcceptable, msg_on_fail=http_msg,
                            content=content, content_type=CONTENT_TYPE_JSON)  # enforce type to avoid recursion
        return handler(request)
    return validate_format


def apply_response_format_tween(handler, registry):    # noqa: F811
    # type: (Callable[[PyramidRequest], HTTPException], Registry) -> Callable[[PyramidRequest], PyramidResponse]
    """
    Tween that applies the response ``Content-Type`` according to the requested ``Accept`` header or ``format`` query.

    The target ``Content-Type`` is expected to have been validated by :func:`validate_accept_header_tween` beforehand
    to handle not-acceptable errors. If an invalid format is detected at this stage, JSON is used by default.
    This can be the case for example for :func:`validate_accept_header_tween` itself that raises the error about
    the invalid ``Accept`` header or ``format`` query, but detects these inadequate parameters from incoming request.

    The tween also ensures that additional request metadata extracted from :func:`get_request_info` is applied to
    the response body if not already provided by a previous operation.
    """
    def apply_format(request):
        # type: (Request) -> HTTPException
        """
        Validates the specified request according to its ``Accept`` header, ignoring UI related routes that request more
        content-types than the ones supported by the application for display purposes (styles, images etc.).

        Alternatively, if no ``Accept`` header is found, look for equivalent value provided via query parameter.
        """
        # all magpie API routes expected to either call 'valid_http' or 'raise_http' of 'magpie.api.exception' module
        # an HTTPException is always returned, and content is a JSON-like string
        content_type, is_header = guess_target_format(request)
        if not is_header:
            # NOTE:
            # enforce the accept header in case it was specified with format query, since some renderer implementations
            # will afterward erroneously overwrite the 'content-type' value that we enforce when converting the response
            # from the HTTPException. See:
            #   - https://github.com/Pylons/webob/issues/204
            #   - https://github.com/Pylons/webob/issues/238
            #   - https://github.com/Pylons/pyramid/issues/1344
            request.accept = content_type
        resp = handler(request)  # no exception when EXCVIEW tween is placed under this tween
        if is_magpie_ui_path(request):
            if not resp.content_type:
                resp.content_type = CONTENT_TYPE_HTML
            return resp
        # return routes already converted (valid_http/raise_http where not used, pyramid already generated response)
        if not isinstance(resp, HTTPException):
            return resp
        # forward any headers such as session cookies to be applied
        metadata = get_request_info(request)
        resp_kwargs = {"headers": resp.headers}
        # patch any invalid content-type that should have been validated
        if content_type not in SUPPORTED_ACCEPT_TYPES:
            content_type = CONTENT_TYPE_JSON
        return ax.generate_response_http_format(type(resp), resp_kwargs, resp.text, content_type, metadata)
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
    err_repr = str(http_err)
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


def includeme(config):
    # type: (Configurator) -> None

    # using 'INGRESS' to run `weaver.wps_restapi.api` views that fix HTTP code before OWS response
    config.add_tween(OWS_RESPONSE_INGRESS, under=INGRESS)
    # using 'EXCVIEW' to run over any other 'valid' exception raised to adjust formatting and log
    config.add_tween(OWS_RESPONSE_EXCVIEW, over=EXCVIEW)
