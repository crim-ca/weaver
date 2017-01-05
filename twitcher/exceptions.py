"""
Errors raised during the Twitcher flow.
"""


class AccessTokenNotFound(Exception):
    """
    Error indicating that an access token could not be read from the
    storage backend by an instance of :class:`twitcher.store.AccessTokenStore`.
    """
    pass


class RegistrationException(Exception):
    pass
