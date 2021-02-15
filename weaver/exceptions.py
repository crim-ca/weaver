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
    HTTPInternalServerError,
    HTTPNotFound
)
from pyramid.request import Request as PyramidRequest
from pyramid.testing import DummyRequest
from requests import Request as RequestsRequest
from werkzeug.wrappers import Request as WerkzeugRequest

from weaver.formats import CONTENT_TYPE_TEXT_XML
from weaver.owsexceptions import (
    OWSAccessForbidden,
    OWSException,
    OWSInvalidParameterValue,
    OWSMissingParameterValue,
    OWSNoApplicableCode,
    OWSNotFound
)

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import Any, Callable, Type


class WeaverException(Exception):
    """Base class of exceptions defined by :mod:`weaver` package."""
    message = ""


class InvalidIdentifierValue(WeaverException, ValueError, HTTPBadRequest, OWSInvalidParameterValue):
    """
    Error indicating that an ID to be employed for following operations
    is not considered as valid to allow further processed or usage.
    """
    status_code = 400
    locator = "identifier"


class MissingIdentifierValue(WeaverException, ValueError, HTTPBadRequest, OWSMissingParameterValue):
    """
    Error indicating that an ID to be employed for following operations
    was missing and cannot continue further processing or usage.
    """
    status_code = 400
    locator = "identifier"


class ServiceException(WeaverException, OWSException):
    """Base exception related to a :class:`weaver.datatype.Service`."""
    locator = "service"


class ServiceNotAccessible(ServiceException, HTTPForbidden, OWSAccessForbidden):
    """
    Error indicating that a WPS service exists but is not visible to retrieve
    from the storage backend of an instance of :class:`weaver.store.ServiceStore`.
    """


class ServiceNotFound(ServiceException, HTTPNotFound, OWSNotFound):
    """
    Error indicating that an OWS service could not be read from the
    storage backend by an instance of :class:`weaver.store.ServiceStore`.
    """


class ServiceRegistrationError(ServiceException):
    """
    Error indicating that an OWS service could not be registered in the
    storage backend by an instance of :class:`weaver.store.ServiceStore`.
    """


class ProcessException(WeaverException, OWSException):
    """Base exception related to a :class:`weaver.datatype.Process`."""
    locator = "process"


class ProcessNotAccessible(ProcessException, HTTPForbidden, OWSAccessForbidden):
    """
    Error indicating that a local WPS process exists but is not visible to retrieve
    from the storage backend of an instance of :class:`weaver.store.ProcessStore`.
    """


class ProcessNotFound(ProcessException, HTTPNotFound, OWSNotFound):
    """
    Error indicating that a local WPS process could not be read from the
    storage backend by an instance of :class:`weaver.store.ProcessStore`.
    """


class ProcessRegistrationError(ProcessException):
    """
    Error indicating that a WPS process could not be registered in the
    storage backend by an instance of :class:`weaver.store.ProcessStore`.
    """


class ProcessInstanceError(ProcessException):
    """
    Error indicating that the process instance passed is not supported with
    storage backend by an instance of :class:`weaver.store.ProcessStore`.
    """


class JobException(WeaverException):
    """Base exception related to a :class:`weaver.datatype.Job`."""
    locator = "job"


class JobNotFound(JobException, HTTPNotFound, OWSNotFound):
    """
    Error indicating that a job could not be read from the
    storage backend by an instance of :class:`weaver.store.JobStore`.
    """


class JobRegistrationError(JobException):
    """
    Error indicating that a job could not be registered in the
    storage backend by an instance of :class:`weaver.store.JobStore`.
    """


class JobUpdateError(JobException):
    """
    Error indicating that a job could not be updated in the
    storage backend by an instance of :class:`weaver.store.JobStore`.
    """


class PackageException(WeaverException):
    """Base exception related to a :class:`weaver.processes.wps_package.Package`."""
    locator = "package"


class PackageTypeError(PackageException):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly parse input/output type(s) for package deployment or execution.
    """


class PackageRegistrationError(PackageException):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly be registered for package deployment because of invalid prerequisite.
    """


class PackageExecutionError(PackageException):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly execute the package using provided inputs and package definition.
    """


class PackageNotFound(PackageException, HTTPNotFound, OWSNotFound):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly retrieve the package definition using provided references.
    """


class PayloadNotFound(PackageException):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.WpsPackage`
    could not properly retrieve the package deploy payload using provided references.
    """


class QuoteException(WeaverException):
    """Base exception related to a :class:`weaver.datatype.Quote`."""
    locator = "quote"


class QuoteNotFound(QuoteException, HTTPNotFound, OWSNotFound):
    """
    Error indicating that a quote could not be read from the
    storage backend by an instance of :class:`weaver.store.QuoteStore`.
    """


class QuoteRegistrationError(QuoteException):
    """
    Error indicating that a quote could not be registered in the
    storage backend by an instance of :class:`weaver.store.QuoteStore`.
    """


class QuoteInstanceError(QuoteException):
    """
    Error indicating that a given object doesn't correspond to an expected
    instance of :class:`weaver.datatype.Quote`.
    """


class BillException(WeaverException):
    """Base exception related to a :class:`weaver.datatype.Bill`."""
    locator = "bill"


class BillNotFound(BillException, HTTPNotFound, OWSNotFound):
    """
    Error indicating that a bill could not be read from the
    storage backend by an instance of :class:`weaver.store.BillStore`.
    """


class BillRegistrationError(BillException):
    """
    Error indicating that a bill could not be registered in the
    storage backend by an instance of :class:`weaver.store.BillStore`.
    """


class BillInstanceError(BillException):
    """
    Error indicating that a given object doesn't correspond to an expected
    instance of :class:`weaver.datatype.Bill`.
    """


def handle_known_exceptions(function):
    # type: (Callable[[Any, Any], Any]) -> Callable
    """
    Decorator that catches lower-level raised exception that are known to :mod:`weaver` but not by :mod:`pywps`.

    .. seealso::
        :class:`weaver.wps.service.WorkerService`

        Without prior handling of known internal exception, :mod:`pywps` generates by default ``500`` internal server
        error response since it doesn't know how to interpret more specific exceptions defined in :mod:`weaver`.

    The decorator simply returns the known exception such that :func:`weaver.tweens.ows_response_tween` can later
    handle it appropriately.
    """

    @functools.wraps(function)
    def wrapped(*_, **__):
        try:
            return function(*_, **__)
        except (WeaverException, OWSException, HTTPException) as exc:
            if isinstance(exc, WeaverException) and not isinstance(exc, OWSException):
                return OWSNoApplicableCode(str(exc), locator="service", content_type=CONTENT_TYPE_TEXT_XML)
            return exc  # return to avoid raising, raise would be caught by parent pywps call wrapping 'function'
        # any other unknown exception by weaver will be raised here as normal, and pywps should repackage them as 500

    return wrapped


def log_unhandled_exceptions(logger=LOGGER, message="Unhandled exception occurred.", exception=Exception,
                             force=False, require_http=True, is_request=True):
    # type: (logging.Logger, str, Type[Exception], bool, bool, bool) -> Callable
    """
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
