"""
Definitions of types used by tokens.
"""

import time

from twitcher.utils import now_secs
from twitcher.exceptions import AccessTokenNotFound


import logging
logger = logging.getLogger(__name__)


class Service(dict):
    """
    Dictionary that contains OWS services. It always has ``'url'`` key.
    """
    def __init__(self, *args, **kwargs):
        super(Service, self).__init__(*args, **kwargs)
        if 'url' not in self:
            raise TypeError("'url' is required")

    @property
    def url(self):
        """Service URL."""
        return self['url']

    @property
    def name(self):
        """Service name."""
        return self.get('name', 'unknown')

    @property
    def type(self):
        """Service type."""
        return self.get('type', 'WPS')

    @property
    def public(self):
        """Flag if service has public access."""
        return self.get('public', False)

    @property
    def c4i(self):
        """Flag if service is by climate4impact."""
        return self.get('c4i', False)

    @property
    def params(self):
        return {'url': self.url, 'name': self.name, 'type': self.type, 'public': self.public, 'c4i': self.c4i}

    def __str__(self):
        return self.name

    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)


class AccessToken(dict):
    """
    Dictionary that contains access token. It always has ``'token'`` key.
    """

    def __init__(self, *args, **kwargs):
        super(AccessToken, self).__init__(*args, **kwargs)
        if 'token' not in self:
            raise TypeError("'token' is required")

    @property
    def token(self):
        """Access token string."""
        return self['token']

    @property
    def expires_at(self):
        return int(self.get("expires_at", 0))

    @property
    def expires_in(self):
        """
        Returns the time until the token expires.
        :return: The remaining time until expiration in seconds or 0 if the
                 token has expired.
        """
        time_left = self.expires_at - now_secs()

        if time_left > 0:
            return time_left
        return 0

    def is_expired(self):
        """
        Determines if the token has expired.
        :return: `True` if the token has expired. Otherwise `False`.
        """
        if self.expires_at is None:
            return True

        if self.expires_in > 0:
            return False

        return True

    @property
    def data(self):
        return self.get('data') or {}

    @property
    def params(self):
        return {'access_token': self.token, 'expires_at': self.expires_at}

    def __str__(self):
        return self.token

    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)
