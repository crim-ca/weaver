"""
Errors raised during the Weaver flow.

Some of these error inherit from :class:`weaver.owsexceptions.OWSException` and their derived classes to allow
:mod:`pywps` to automatically understand and render those exception if raised by an underlying :mod:`weaver` operation.
"""
import functools
import logging
from typing import TYPE_CHECKING

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPForbidden,
    HTTPGone,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPUnprocessableEntity
)
from pyramid.request import Request as PyramidRequest
from pyramid.testing import DummyRequest
from requests import Request as RequestsRequest
from werkzeug.wrappers import Request as WerkzeugRequest

from weaver.formats import CONTENT_TYPE_TEXT_XML
from weaver.owsexceptions import (
    OWSAccessForbidden,
    OWSException,
    OWSGone,
    OWSInvalidParameterValue,
    OWSMissingParameterValue,
    OWSNoApplicableCode,
    OWSNotFound
)

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import Any, Callable, Type


class WeaverException(Exception):
    """
    Base class of exceptions defined by :mod:`weaver` package.
    """
    code = 500
    title = "Internal Server Error"
    detail = message = comment = explanation = "Unknown error"


class InvalidIdentifierValue(HTTPBadRequest, OWSInvalidParameterValue, WeaverException, ValueError):
    """
    Error related to an invalid identifier parameter.

    Error indicating that an ID to be employed for following operations
    is not considered as valid to allow further processing or usage.
    """
    code = 400
    locator = "identifier"


class MissingIdentifierValue(HTTPBadRequest, OWSMissingParameterValue, WeaverException, ValueError):
    """
    Error related to missing identifier parameter.

    Error indicating that an ID to be employed for following operations
    was missing and cannot continue further processing or usage.
    """
    code = 400
    locator = "identifier"


class ServiceException(OWSException, WeaverException):
    """
    Base exception related to a :class:`weaver.datatype.Service`.
    """
    locator = "service"


class ServiceParsingError(HTTPUnprocessableEntity, ServiceException):
    """
    Error related to parsing issue of the reference service definition (incorrectly formed XML/JSON contents).
    """


class ServiceNotAccessible(HTTPForbidden, OWSAccessForbidden, ServiceException):
    """
    Error related to forbidden access to a service.

    Error indicating that a WPS service exists but is not visible to retrieve
    from the storage backend of an instance of :class:`weaver.store.ServiceStore`.
    """


class ServiceNotFound(HTTPNotFound, OWSNotFound, ServiceException):
    """
    Error related to non existant service definition.

    Error indicating that an OWS service could not be read from the
    storage backend by an instance of :class:`weaver.store.ServiceStore`.
    """


class ServiceRegistrationError(HTTPInternalServerError, OWSNoApplicableCode, ServiceException):
    """
    Error related to a registration issue for a service.

    Error indicating that an OWS service could not be registered in the
    storage backend by an instance of :class:`weaver.store.ServiceStore`.
    """


class ProcessException(OWSException, WeaverException):
    """
    Base exception related to a :class:`weaver.datatype.Process`.
    """
    locator = "process"


class ProcessNotAccessible(HTTPForbidden, OWSAccessForbidden, ProcessException):
    """
    Error related to forbidden access to a process.

    Error indicating that a local WPS process exists but is not visible to retrieve
    from the storage backend of an instance of :class:`weaver.store.ProcessStore`.
    """


class ProcessNotFound(HTTPNotFound, OWSNotFound, ProcessException):
    """
    Error related to a non existant process definition.

    Error indicating that a local WPS process could not be read from the
    storage backend by an instance of :class:`weaver.store.ProcessStore`.
    """


class ProcessRegistrationError(HTTPInternalServerError, OWSNoApplicableCode, ProcessException):
    """
    Error related to a registration issue for a process.

    Error indicating that a WPS process could not be registered in the
    storage backend by an instance of :class:`weaver.store.ProcessStore`.
    """


class ProcessInstanceError(HTTPInternalServerError, OWSNoApplicableCode, ProcessException):
    """
    Error related to an invalid process definition.

    Error indicating that the process instance passed is not supported with
    storage backend by an instance of :class:`weaver.store.ProcessStore`.
    """


class JobException(WeaverException):
    """
    Base exception related to a :class:`weaver.datatype.Job`.
    """
    locator = "job"


class JobNotFound(HTTPNotFound, OWSNotFound, JobException):
    """
    Error related to a non existant job definition.

    Error indicating that a job could not be read from the
    storage backend by an instance of :class:`weaver.store.JobStore`.
    """


class JobGone(HTTPGone, OWSGone, JobException):
    """
    Error related to job resource that is gone.

    Error indicating that an existing job, although recognized, was
    dismissed and underlying resources including results are gone.
    """


class JobInvalidParameter(HTTPBadRequest, OWSInvalidParameterValue, JobException):
    """
    Error related to an invalid search parameter to filter jobs.
    """


class JobRegistrationError(HTTPInternalServerError, OWSNoApplicableCode, JobException):
    """
    Error related to a registration issue for a job.

    Error indicating that a job could not be registered in the
    storage backend by an instance of :class:`weaver.store.JobStore`.
    """


class JobUpdateError(HTTPInternalServerError, OWSNoApplicableCode, JobException):
    """
    Error related to an update issue for a job.

    Error indicating that a job could not be updated in the
    storage backend by an instance of :class:`weaver.store.JobStore`.
    """


class PackageException(WeaverException):
    """
    Base exception related to a :class:`weaver.processes.wps_package.Package`.
    """
    locator = "package"


class PackageTypeError(HTTPUnprocessableEntity, PackageException):
    """
    Error related to an invalid package definition.

    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly parse input/output type(s) for package deployment or execution.
    """


class PackageRegistrationError(HTTPInternalServerError, OWSNoApplicableCode, PackageException):
    """
    Error related to a registration issue for a package.

    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly be registered for package deployment because of invalid prerequisites.
    """


class PackageExecutionError(HTTPInternalServerError, OWSNoApplicableCode, PackageException):
    """
    Error related to a runtime issue during package execution.

    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly execute the package using provided inputs and package definition.
    """


class PackageNotFound(HTTPNotFound, OWSNotFound, PackageException):
    """
    Error related to a non existant package definition.

    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly retrieve the package definition using provided references.
    """


class PayloadNotFound(HTTPNotFound, OWSNotFound, PackageException):
    """
    Error related to a non existant deployment payload definition.

    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly retrieve the package deploy payload using provided references.
    """


class QuoteException(WeaverException):
    """
    Base exception related to a :class:`weaver.datatype.Quote`.
    """
    locator = "quote"


class QuoteNotFound(HTTPNotFound, OWSNotFound, QuoteException):
    """
    Error related to a non existant quote definition.

    Error indicating that a quote could not be read from the
    storage backend by an instance of :class:`weaver.store.QuoteStore`.
    """


class QuoteRegistrationError(HTTPInternalServerError, OWSNoApplicableCode, QuoteException):
    """
    Error related to an invalid registration issue for a quote.

    Error indicating that a quote could not be registered in the
    storage backend by an instance of :class:`weaver.store.QuoteStore`.
    """


class QuoteInstanceError(HTTPInternalServerError, OWSNoApplicableCode, QuoteException):
    """
    Error related to an invalid quote definition.

    Error indicating that a given object doesn't correspond to an expected
    instance of :class:`weaver.datatype.Quote`.
    """


class BillException(WeaverException):
    """
    Base exception related to a :class:`weaver.datatype.Bill`.
    """
    locator = "bill"


class BillNotFound(HTTPNotFound, OWSNotFound, BillException):
    """
    Error related to a non existant bill definition.

    Error indicating that a bill could not be read from the
    storage backend by an instance of :class:`weaver.store.BillStore`.
    """


class BillRegistrationError(HTTPInternalServerError, OWSNoApplicableCode, BillException):
    """
    Error related to a registration issue for a bill.

    Error indicating that a bill could not be registered in the
    storage backend by an instance of :class:`weaver.store.BillStore`.
    """


class BillInstanceError(HTTPInternalServerError, OWSNoApplicableCode, BillException):
    """
    Error related to an invalid bill definition.

    Error indicating that a given object doesn't correspond to an expected
    instance of :class:`weaver.datatype.Bill`.
    """


# FIXME:
#   https://github.com/crim-ca/weaver/issues/215
#   define common Exception classes that won't require this type of conversion
def handle_known_exceptions(function):
    # type: (Callable[[Any, Any], Any]) -> Callable
    """
    Decorator that catches lower-level raised exception that are known to :mod:`weaver` but not by :mod:`pywps`.

    .. seealso::
        :class:`weaver.wps.service.WorkerService`

        Without prior handling of known internal exception, :mod:`pywps` generates by default ``500`` internal server
        error response since it doesn't know how to interpret more specific exceptions defined in :mod:`weaver`.

    The decorator simply returns the known exception such that :func:`weaver.tweens.ows_response_tween` can later
    handle it appropriately. Exceptions derived from :exception:`weaver.owsexceptions.OWSException` are employed since
    they themselves have base references to :mod:`pywps.exceptions` classes that the service can understand.

    .. warning::
        In :mod:`pywps`, ``HTTPException`` refers to :exception:`werkzeug.exceptions.HTTPException` while in
        :mod:`weaver`, it is :exception:`pyramid.httpexceptions.HTTPException`. They both offer similar interfaces and
        functionalities (headers, body, status-code, etc.), but they are not intercepted in the same try/except blocks.
    """

    @functools.wraps(function)
    def wrapped(*_, **__):
        try:
            return function(*_, **__)
        except (WeaverException, OWSException, HTTPException) as exc:
            if isinstance(exc, WeaverException) and not isinstance(exc, OWSException):
                return OWSNoApplicableCode(str(exc), locator="service", content_type=CONTENT_TYPE_TEXT_XML)
            if isinstance(exc, HTTPException):
                # override default pre-generated plain text content-type such that
                # resulting exception generates the response content with requested accept or XML by default
                exc.headers.setdefault("Accept", CONTENT_TYPE_TEXT_XML)
                exc.headers.pop("Content-Type", None)
                if isinstance(exc, HTTPNotFound):
                    exc = OWSNotFound(str(exc), locator="service", status=exc)
                elif isinstance(exc, HTTPForbidden):
                    exc = OWSAccessForbidden(str(exc), locator="service", status=exc)
                else:
                    exc = OWSException(str(exc), locator="service", status=exc)
            return exc  # return to avoid raising, raise would be caught by parent pywps call wrapping 'function'
        # any other unknown exception by weaver will be raised here as normal, and pywps should repackage them as 500

    return wrapped


def log_unhandled_exceptions(logger=LOGGER, message="Unhandled exception occurred.", exception=Exception,
                             force=False, require_http=True, is_request=True):
    # type: (logging.Logger, str, Type[Exception], bool, bool, bool) -> Callable
    """
    Decorator for logging captured exceptions before re-raise.

    Decorator that will raise ``exception`` with specified ``message`` if an exception is caught while execution the
    wrapped function, after logging relevant details about the caught exception with ``logger``.

    :param logger: logger to use for logging (default: use :data:`weaver.exception.LOGGER`).
    :param message: message that will be logged with details and then raised with ``exception``.
    :param exception: exception type to be raised instead of the caught exception.
    :param force: force handling of any raised exception (default: only *known* unhandled exceptions are logged).
    :param require_http:
        consider non HTTP-like exceptions as *unknown* and raise one instead
        (default: ``True`` and raises :class:`HTTPInternalServerError`, unless ``exception`` is HTTP-like).
    :param is_request: specifies if the decorator is applied onto a registered request function to handle its inputs.
    :raises exception: if an *unknown* exception was caught (or forced) during the decorated function's execution.
    :raises Exception: original exception if it is *known*.
    """
    known_exceptions = [WeaverException]
    known_http_exceptions = [HTTPException, OWSException]
    if require_http:
        if not issubclass(exception, tuple(known_http_exceptions)):
            exception = HTTPInternalServerError
        known_exceptions.extend(known_http_exceptions)
    known_exceptions = tuple(known_exceptions)

    def wrap(function):
        # type: (Callable[[Any, Any], Any]) -> Callable
        @functools.wraps(function)
        def call(*args, **kwargs):
            try:
                # handle input arguments that are extended by various pyramid operations
                if is_request:
                    any_request_type = (RequestsRequest, PyramidRequest, DummyRequest, WerkzeugRequest)
                    while len(args) and not isinstance(args[0], any_request_type):
                        args = args[1:]
                return function(*args, **kwargs)
            except Exception as exc:
                # if exception was already handled by this wrapper from a previously wrapped function,
                # just re-raise the exception without over-logging it recursively
                handle = "__LOG_UNHANDLED_EXCEPTION__"
                if not hasattr(exc, handle):
                    setattr(exc, handle, True)  # mark as handled
                    # unless specified to log any type, raise only known exceptions
                    if force or not isinstance(exc, known_exceptions):
                        setattr(exception, handle, True)    # mark as handled
                        setattr(exception, "cause", exc)    # make original exception available through new one raised
                        logger.exception("%s%s[%r]", message, (" " if message else "") + "Exception: ", exc)
                        raise exception(message)
                raise exc
        return call
    return wrap
