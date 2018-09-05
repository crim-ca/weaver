"""
Errors raised during the Twitcher flow.
"""


class AccessTokenNotFound(Exception):
    """
    Error indicating that an access token could not be read from the
    storage backend by an instance of :class:`twitcher.store.AccessTokenStore`.
    """
    pass


class ServiceNotFound(Exception):
    """
    Error indicating that an OWS service could not be read from the
    storage backend by an instance of :class:`twitcher.store.ServiceStore`.
    """
    pass


class ServiceRegistrationError(Exception):
    """
    Error indicating that an OWS service could not be registered in the
    storage backend by an instance of :class:`twitcher.store.ServiceStore`.
    """
    pass


class ProcessNotFound(Exception):
    """
    Error indicating that a local WPS service could not be read from the
    storage backend by an instance of :class:`twitcher.store.ProcessStore`.
    """
    pass


class JobNotFound(Exception):
    """
    Error indicating that an job could not be read from the
    storage backend by an instance of :class:`twitcher.store.JobStore`.
    """
    pass


class ProcessRegistrationError(Exception):
    """
    Error indicating that a WPS process could not be registered in the
    storage backend by an instance of :class:`twitcher.store.ProcessStore`.
    """
    pass


class ProcessInstanceError(Exception):
    """
    Error indicating that the process instance passed is not supported with
    storage backend by an instance of :class:`twitcher.store.ProcessStore`.
    """
    pass


class JobRegistrationError(Exception):
    """
    Error indicating that an job could not be registered in the
    storage backend by an instance of :class:`twitcher.store.JobStore`.
    """
    pass


class JobUpdateError(Exception):
    """
    Error indicating that an job could not be updated in the
    storage backend by an instance of :class:`twitcher.store.JobStore`.
    """
    pass


class PackageTypeError(Exception):
    """
    Error indicating that an instance of :class:`twitcher.processes.wps_package.Package`
    could not properly parse input/output type(s) for package deployment or execution.
    """
    pass


class PackageRegistrationError(Exception):
    """
    Error indicating that an instance of :class:`twitcher.processes.wps_package.Package`
    could not properly be registered for package deployment because of invalid prerequisite.
    """
    pass


class PackageExecutionError(Exception):
    """
    Error indicating that an instance of :class:`twitcher.processes.wps_package.Package`
    could not properly execute the package using provided inputs and package definition.
    """
    pass
