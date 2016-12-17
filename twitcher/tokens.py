"""
Classes to manage access tokens used in the security middleware.

The implementation is based on `python-oauth2 <http://python-oauth2.readthedocs.io/en/latest/>`_

See access token examples:

* https://www.mapbox.com/developers/api/
* http://python-oauth2.readthedocs.io/en/latest/store.html
"""

import uuid
import time

from twitcher.utils import now_secs
from twitcher.exceptions import AccessTokenNotFound
from twitcher.db import mongodb

import logging
logger = logging.getLogger(__name__)


def tokenstore_factory(registry):
    db = mongodb(registry)
    return MongodbAccessTokenStore(db.tokens)


def tokengenerator_factory(registry):
    return UuidGenerator()


def expires_at(hours=1):
    return now_secs() + hours * 3600


class AccessTokenStore(object):

    def save_token(self, access_token):
        """
        Stores an access token with additional data.
        """
        raise NotImplementedError

    def delete_token(self, token):
        """
        Deletes an access token from the store using its token string to identify it.
        This invalidates both the access token and the token.

        :param token: A string containing the token.
        :return: None.
        """
        raise NotImplementedError

    def fetch_by_token(self, token):
        """
        Fetches an access token from the store using its token string to
        identify it.

        :param token: A string containing the token.
        :return: An instance of :class:`twitcher.tokens.AccessToken`.
        """
        raise NotImplementedError

    def clean_tokens(self):
        """
        Removes all tokens from database.
        """
        raise NotImplementedError


class MongodbAccessTokenStore(AccessTokenStore):
    def __init__(self, collection):
        self.collection = collection

    def save_token(self, access_token):
        self.collection.insert_one(access_token)

    def delete_token(self, token):
        self.collection.delete_one({'token': token})

    def fetch_by_token(self, token):
        token = self.collection.find_one({'token': token})
        if not token:
            raise AccessTokenNotFound
        return AccessToken(token)

    def clean_tokens(self):
        self.collection.drop()


class AccessTokenGenerator(object):
    """
    Base class for access token generators.
    """
    def create_access_token(self, valid_in_hours=1, user_environ=None):
        """
        Creates an access token.

        TODO: check valid in hours
        TODO: maybe specify how often a token can be used
        """
        access_token = AccessToken(
            token=self.generate(),
            expires_at=expires_at(hours=valid_in_hours),
            user_environ=user_environ)
        return access_token

    def generate(self):
        raise NotImplementedError


class UuidGenerator(AccessTokenGenerator):
    """
    Generate a token using uuid4.
    """
    def generate(self):
        """
        :return: A new token
        """
        return uuid.uuid4().get_hex()


class AccessToken(dict):
    """
    Dictionary that contains access token. It always has ``'token'`` key.
    """

    def __init__(self, *args, **kwargs):
        super(AccessToken, self).__init__(*args, **kwargs)
        if 'token' not in self:
            raise TypeError("'token' is required")

        self.expires_at = int(self.get("expires_at", 0))

    @property
    def token(self):
        """Access token string."""
        return self['token']

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
    def user_environ(self):
        environ = self.get('user_environ') or {}
        return environ

    def __str__(self):
        return self.token

    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)
