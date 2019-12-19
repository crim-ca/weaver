"""
Errors raised during the weaver flow.
"""
from typing import TYPE_CHECKING
from pyramid.httpexceptions import HTTPException, HTTPInternalServerError
from functools import wraps
import logging
LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from weaver.typedefs import LoggerType
    from typing import Any, AnyStr, Callable, Type


class WeaverException(Exception):
    """Base class of exceptions defined by :py:mod:`weaver` package."""


class InvalidIdentifierValue(WeaverException, ValueError):
    """
    Error indicating that an id to be employed for following operations
    is not considered as valid to allow further processed or usage.
    """
    
    
class ServiceException(WeaverException):
    """Base exception related to a :class:`weaver.datatype.Service`."""


class ServiceNotAccessible(ServiceException):
    """
    Error indicating that a WPS service exists but is not visible to retrieve
    from the storage backend of an instance of :class:`weaver.store.ServiceStore`.
    """


class ServiceNotFound(ServiceException):
    """
    Error indicating that an OWS service could not be read from the
    storage backend by an instance of :class:`weaver.store.ServiceStore`.
    """


class ServiceRegistrationError(ServiceException):
    """
    Error indicating that an OWS service could not be registered in the
    storage backend by an instance of :class:`weaver.store.ServiceStore`.
    """
    
    
class ProcessException(WeaverException):
    """Base exception related to a :class:`weaver.datatype.Process`."""


class ProcessNotAccessible(ProcessException):
    """
    Error indicating that a local WPS process exists but is not visible to retrieve
    from the storage backend of an instance of :class:`weaver.store.ProcessStore`.
    """


class ProcessNotFound(ProcessException):
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


class JobNotFound(JobException):
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
    

class PackageTypeError(PackageException):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly parse input/output type(s) for package deployment or execution.
    """


class PackageRegistrationError(PackageException):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly be registered for package deployment because of invalid prerequisite.
    """


class PackageExecutionError(PackageException):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly execute the package using provided inputs and package definition.
    """


class PackageNotFound(PackageException):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly retrieve the package definition using provided references.
    """


class PayloadNotFound(PackageException):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly retrieve the package deploy payload using provided references.
    """
    
    
class QuoteException(WeaverException):
    """Base exception related to a :class:`weaver.datatype.Quote`."""


class QuoteNotFound(QuoteException):
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


class BillNotFound(BillException):
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


def log_unhandled_exceptions(logger=LOGGER, message="Unhandled exception occurred.", exception=Exception,
                             force=False, require_http=True):
    # type: (LoggerType, AnyStr, Type[Exception], bool, bool) -> Callable
    """
    Decorator that will raise ``exception`` with specified ``message`` if an exception is caught while execution the
    wrapped function, after logging relevant details about the caught exception with ``logger``.

    :param logger: logger to use for logging (default: use :py:mod:`weaver.exception` logger).
    :param message: message that will be logged with details and then raised with ``exception``.
    :param exception: exception type to be raised instead of the caught exception.
    :param force: force handling of any raised exception (default: only *known* unhandled exceptions are logged).
    :param require_http:
        consider non HTTP-like exceptions as *unknown* and raise one instead
        (default: ``True`` and raises :class:`HTTPInternalServerError`, unless ``exception`` is HTTP-like).
    :raises exception: if an *unknown* exception was caught (or forced) during the decorated function's execution.
    :raises Exception: original exception if it is *known*.
    """
    from weaver.owsexceptions import OWSException   # avoid circular import error

    known_exceptions = [WeaverException]
    known_http_exceptions = [HTTPException, OWSException]
    if require_http:
        if not issubclass(exception, tuple(known_http_exceptions)):
            exception = HTTPInternalServerError
        known_exceptions.extend(known_http_exceptions)
    known_exceptions = tuple(known_exceptions)

    def wrap(function):
        # type: (Callable[[Any, Any], Any]) -> Callable
        @wraps(function)
        def call(*args, **kwargs):
            try:
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
                        setattr(exception, "error", exc)    # make original exception available through new one raised
                        logger.exception("%s%s[%r]", message, (" " if message else "") + "Exception: ", exc)
                        raise exception(message)
                raise exc
        return call
    return wrap
