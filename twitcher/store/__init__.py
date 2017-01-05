"""
Store adapters to persist and retrieve data during the twitcher process or
for later use. For example an access token storage and a service registry.

This module provides base classes that can be extended to implement your own
solution specific to your needs.

The implementation is based on `python-oauth2 <http://python-oauth2.readthedocs.io/en/latest/>`_.
"""


def tokenstore_factory(registry, database=None):
    """
    Creates a token store with the interface of :class:`twitcher.store.AccessTokenStore`.
    By default the mongodb implementation will be used.

    :param database: A string with the store implementation name: "mongodb" or "memory".
    :return: An instance of :class:`twitcher.store.AccessTokenStore`.
    """
    database = database or 'mongodb'
    if database == 'mongodb':
        from twitcher.db import mongodb as _mongodb
        from twitcher.store.mongodb import MongodbTokenStore
        db = _mongodb(registry)
        store = MongodbTokenStore(db.tokens)
    else:
        from twitcher.store.memory import MemoryTokenStore
        store = MemoryTokenStore()
    return store


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
        :return: An instance of :class:`twitcher.datatype.AccessToken`.
        """
        raise NotImplementedError

    def clean_tokens(self):
        """
        Removes all tokens from database.
        """
        raise NotImplementedError
