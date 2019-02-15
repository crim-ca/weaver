"""
Errors raised during the weaver flow.
"""


class InvalidIdentifierValue(ValueError):
    """
    Error indicating that an id to be employed for following operations
    is not considered as valid to allow further processed or usage.
    """
    pass


class AccessTokenNotFound(Exception):
    """
    Error indicating that an access token could not be read from the
    storage backend by an instance of :class:`weaver.store.AccessTokenStore`.
    """
    pass


class ServiceNotAccessible(Exception):
    """
    Error indicating that a WPS service exists but is not visible to retrieve
    from the storage backend of an instance of :class:`weaver.store.ServiceStore`.
    """
    pass


class ServiceNotFound(Exception):
    """
    Error indicating that an OWS service could not be read from the
    storage backend by an instance of :class:`weaver.store.ServiceStore`.
    """
    pass


class ServiceRegistrationError(Exception):
    """
    Error indicating that an OWS service could not be registered in the
    storage backend by an instance of :class:`weaver.store.ServiceStore`.
    """
    pass


class ProcessNotAccessible(Exception):
    """
    Error indicating that a local WPS process exists but is not visible to retrieve
    from the storage backend of an instance of :class:`weaver.store.ProcessStore`.
    """
    pass


class ProcessNotFound(Exception):
    """
    Error indicating that a local WPS process could not be read from the
    storage backend by an instance of :class:`weaver.store.ProcessStore`.
    """
    pass


class ProcessRegistrationError(Exception):
    """
    Error indicating that a WPS process could not be registered in the
    storage backend by an instance of :class:`weaver.store.ProcessStore`.
    """
    pass


class ProcessInstanceError(Exception):
    """
    Error indicating that the process instance passed is not supported with
    storage backend by an instance of :class:`weaver.store.ProcessStore`.
    """
    pass


class JobNotFound(Exception):
    """
    Error indicating that a job could not be read from the
    storage backend by an instance of :class:`weaver.store.JobStore`.
    """
    pass


class JobRegistrationError(Exception):
    """
    Error indicating that a job could not be registered in the
    storage backend by an instance of :class:`weaver.store.JobStore`.
    """
    pass


class JobUpdateError(Exception):
    """
    Error indicating that a job could not be updated in the
    storage backend by an instance of :class:`weaver.store.JobStore`.
    """
    pass


class PackageTypeError(Exception):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly parse input/output type(s) for package deployment or execution.
    """
    pass


class PackageRegistrationError(Exception):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly be registered for package deployment because of invalid prerequisite.
    """
    pass


class PackageExecutionError(Exception):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly execute the package using provided inputs and package definition.
    """
    pass


class PackageNotFound(Exception):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly retrieve the package definition using provided references.
    """
    pass


class PayloadNotFound(Exception):
    """
    Error indicating that an instance of :class:`weaver.processes.wps_package.Package`
    could not properly retrieve the package deploy payload using provided references.
    """
    pass


class QuoteNotFound(Exception):
    """
    Error indicating that a quote could not be read from the
    storage backend by an instance of :class:`weaver.store.QuoteStore`.
    """
    pass


class QuoteRegistrationError(Exception):
    """
    Error indicating that a quote could not be registered in the
    storage backend by an instance of :class:`weaver.store.QuoteStore`.
    """
    pass


class QuoteInstanceError(Exception):
    """
    Error indicating that a given object doesn't correspond to an expected
    instance of :class:`weaver.datatype.Quote`.
    """
    pass


class BillNotFound(Exception):
    """
    Error indicating that a bill could not be read from the
    storage backend by an instance of :class:`weaver.store.BillStore`.
    """
    pass


class BillRegistrationError(Exception):
    """
    Error indicating that a bill could not be registered in the
    storage backend by an instance of :class:`weaver.store.BillStore`.
    """
    pass


class BillInstanceError(Exception):
    """
    Error indicating that a given object doesn't correspond to an expected
    instance of :class:`weaver.datatype.Bill`.
    """
    pass
