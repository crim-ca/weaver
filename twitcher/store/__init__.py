"""
Factories to create storage backends.
"""

# Interfaces
from twitcher.store.base import AccessTokenStore

# Factories
from twitcher.db import mongodb as _mongodb
from twitcher.store.mongodb import MongodbTokenStore
from twitcher.store.memory import MemoryTokenStore


def tokenstore_factory(registry, database=None):
    """
    Creates a token store with the interface of :class:`twitcher.store.AccessTokenStore`.
    By default the mongodb implementation will be used.

    :param database: A string with the store implementation name: "mongodb" or "memory".
    :return: An instance of :class:`twitcher.store.AccessTokenStore`.
    """
    database = database or 'mongodb'
    if database == 'mongodb':
        db = _mongodb(registry)
        store = MongodbTokenStore(db.tokens)
    else:
        store = MemoryTokenStore()
    return store

from twitcher.store.mongodb import MongodbRegistryStore


def service_registry_factory(registry):
    """
    Creates a registry store with the interface of :class:`twitcher.store.ServiceRegistryStore`.

    :return: An instance of :class:`twitcher.store.ServiceRegistryStore`.
    """
    db = _mongodb(registry)
    return MongodbRegistryStore(collection=db.services)
