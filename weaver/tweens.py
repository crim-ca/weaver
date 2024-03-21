import colander
import logging
import sys
from typing import TYPE_CHECKING

from pyramid.httpexceptions import (
    HTTPException,
    HTTPInternalServerError,
    HTTPNotAcceptable,
    HTTPRedirection,
    HTTPSuccessful
)
from pyramid.tweens import EXCVIEW, INGRESS, MAIN

from weaver.formats import ContentType, guess_target_format
from weaver.owsexceptions import OWSException, OWSNotImplemented
from weaver.utils import clean_json_text_body, fully_qualified_name
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
                "detail": f"Specified response format by query parameter or Accept header is not supported.",
                "status": HTTPNotAcceptable.code,
                "cause": invalid.value,
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
    Tween factory that applies the response ``Content-Type`` according to the requested format.

    Format can be provided by ``Accept`` header or ``format`` query.

    The target ``Content-Type`` is expected to have been validated by :func:`validate_accept_header_tween` beforehand
    to handle not-acceptable errors. If an invalid format is detected at this stage, JSON is used by default.
    This can be the case for example for :func:`validate_accept_header_tween` itself that raises the error about
    the invalid ``Accept`` header or ``format`` query, but detects these inadequate parameters from incoming request.

    The tween also ensures that additional request metadata extracted from :func:`get_request_info` is applied to
    the response body if not already provided by a previous operation.
    """
    def apply_format(request):
        # type: (PyramidRequest) -> HTTPException
        """
        Validates the specified request according to its ``Accept`` header, ignoring UI related routes that request more
        content-types than the ones supported by the application for display purposes (styles, images etc.).

        Alternatively, if no ``Accept`` header is found, look for equivalent value provided via query parameter.
        """
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


# def generate_response_http_format(http_class, http_kwargs, content, content_type=None):
#     # type: (Type[HTTPException], Optional[Dict[str, Any]], Union[JSON, str], Optional[str]) -> HTTPException
#     """
#     Formats the HTTP response content according to desired ``content_type`` using provided HTTP code and content.
#
#     :param http_class: `HTTPException` derived class to use for output (code, generic title/explanation, etc.)
#     :param http_kwargs: additional keyword arguments to pass to `http_class` when called
#     :param content: formatted JSON content or literal string content providing additional details for the response
#     :param content_type: One of the supported types by the application.
#     :return: `http_class` instance with requested information and content type if creation succeeds
#     :raises: `HTTPInternalServerError` instance details about requested information and content type if creation fails
#     """
#     content = str(content) if not isinstance(content, six.string_types) else content
#
#     # adjust additional keyword arguments and try building the http response class with them
#     http_kwargs = {} if http_kwargs is None else http_kwargs
#     http_headers = http_kwargs.get("headers", {})
#     # omit content-type and related headers that we override
#     for header in dict(http_headers):
#         if header.lower().startswith("content-"):
#             http_headers.pop(header, None)
#
#     try:
#         # Pass down Location if it is provided and should be given as input parameter for this HTTP class.
#         # Omitting this step would inject a (possibly extra) empty Location that defaults to the current application.
#         # When resolving HTTP redirects, injecting this extra Location when the requested one is not the current
#         # application will lead to redirection failures because all locations are appended in the header as CSV list.
#         if issubclass(http_class, HTTPRedirection):
#             location = get_header("Location", http_headers, pop=True)
#             if location and "location" not in http_kwargs:
#                 http_kwargs["location"] = location
#
#         # directly output json
#         if content_type == ContentType.APP_JSON:
#             content_type = "{}; charset=UTF-8".format(CONTENT_TYPE_JSON)
#             http_response = http_class(body=content, content_type=content_type, **http_kwargs)
#
#         # otherwise json is contained within the html <body> section
#         elif content_type == ContentType.TEXT_HTML:
#             if http_class is HTTPOk:
#                 http_class.explanation = "Operation successful."
#             if not http_class.explanation:
#                 http_class.explanation = http_class.title  # some don't have any defined
#             # add preformat <pre> section to output as is within the <body> section
#             html_status = "Exception" if http_class.code >= 400 else "Response"
#             html_header = "{}<br><h2>{} Details</h2>".format(http_class.explanation, html_status)
#             html_template = "<pre style='word-wrap: break-word; white-space: pre-wrap;'>{}</pre>"
#             content_type = "{}; charset=UTF-8".format(CONTENT_TYPE_HTML)
#             if json_content:
#                 html_body = html_template.format(json.dumps(json_content, indent=True, ensure_ascii=False))
#             else:
#                 html_body = html_template.format(content)
#             html_body = html_header + html_body
#             http_response = http_class(body_template=html_body, content_type=content_type, **http_kwargs)
#
#         elif content_type in [CONTENT_TYPE_APP_XML, CONTENT_TYPE_TXT_XML]:
#             xml_body = OutputFormat.convert(json_content, ContentType.APP_XML, item_root="response")
#             http_response = http_class(body=xml_body, content_type=CONTENT_TYPE_TXT_XML, **http_kwargs)
#
#         # default back to plain text
#         else:
#             http_response = http_class(body=content, content_type=CONTENT_TYPE_PLAIN, **http_kwargs)
#
#         return http_response
#     except Exception as exc:  # pylint: disable=W0703
#         raise HTTPInternalServerError(json={
#             "detail": "Failed to build HTTP response",
#             "cause": repr(exc),
#             "value": str(content_type),
#         })

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
