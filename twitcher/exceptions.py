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
