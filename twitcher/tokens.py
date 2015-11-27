"""
Classes to manage access tokens used in the security middleware.

The implementation is based on `python-oauth2 <http://python-oauth2.readthedocs.org/>`_

See access token examples:

* https://www.mapbox.com/developers/api/
* http://python-oauth2.readthedocs.org/en/latest/store.html
"""

import uuid
from datetime import timedelta

from twitcher.utils import now, localize_datetime
from twitcher.exceptions import AccessTokenNotFound
from twitcher.db import mongodb

import logging
logger = logging.getLogger(__name__)

# defaults
DEFAULT_VALID_IN_HOURS = 1


def tokenstore_factory(registry):
    db = mongodb(registry)
    return MongodbStore(db.tokens)


def tokengenerator_factory(registry):
    return UuidGenerator()


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



class MongodbStore(AccessTokenStore):
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
    def create_access_token(self, valid_in_hours=DEFAULT_VALID_IN_HOURS, user_environ=None):
        """
        Creates an access token.

        TODO: check valid in hours
        TODO: maybe specify how often a token can be used
        """
        access_token = AccessToken(
            token = self.generate(),
            creation_time = now(),
            valid_in_hours = valid_in_hours,
            user_environ = user_environ)
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
        :rtype: str
        """
        return uuid.uuid4().get_hex()

    
class AccessToken(dict):
    """
    Dictionary that contains access token. It always has ``'access_token'`` key.
    """
    
    def __init__(self, *args, **kwargs):
        super(AccessToken, self).__init__(*args, **kwargs)
        if 'token' not in self:
            raise TypeError("'token' is required")
        if 'creation_time' not in self:
            raise TypeError("'creation_time' is required")

            
    @property
    def token(self):
        """Access token."""
        return self['token']

        
    @property
    def creation_time(self):
        return self['creation_time']

    
    @property
    def valid_in_hours(self):
        return self.get('valid_in_hours', DEFAULT_VALID_IN_HOURS)

    
    def not_before(self):
        """
        Access token is not valid before this time.
        """
        return localize_datetime(self.creation_time)

    
    def not_after(self):
        """
        Access token is not valid after this time.
        """
        return self.not_before() + timedelta(hours=self.valid_in_hours)

    
    def is_valid(self):
        """
        Checks if token is valid.
        """
        return self.not_before() <= now() and now() <= self.not_after()


    @property
    def user_environ(self):
        environ = self['user_environ'] or {}
        return environ

    
    def __str__(self):
        return self.token

    
    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)



    




