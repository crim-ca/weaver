"""
Factories to create storage backends.
"""

# Factories
from twitcher.db import mongodb as _mongodb
# Interfaces
from twitcher.store.base import AccessTokenStore, ProcessStore
from twitcher.store.memory import MemoryTokenStore, MemoryProcessStore
from twitcher.store.mongodb import MongodbTokenStore, MongodbProcessStore
from twitcher.processes import default_processes


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


from twitcher.store.mongodb import MongodbServiceStore
from twitcher.store.memory import MemoryServiceStore


def servicestore_defaultfactory(registry, database=None):
    """
    Creates a service store with the interface of :class:`twitcher.store.ServiceStore`.
    By default the mongodb implementation will be used.

    :return: An instance of :class:`twitcher.store.ServiceStore`.
    """
    database = database or 'mongodb'
    if database == 'mongodb':
        db = _mongodb(registry)
        store = MongodbServiceStore(collection=db.services)
    else:
        store = MemoryServiceStore()
    return store


def processstore_defaultfactory(registry, database=None):
    """
    Creates a process store with the interface of :class:`twitcher.store.ProcessStore`.
    By default the mongodb implementation will be used.

    :return: An instance of :class:`twitcher.store.ProcessStore`.
    """
    database = database or 'mongodb'
    if database == 'mongodb':
        db = _mongodb(registry)
        store = MongodbProcessStore(collection=db.processes, settings=registry.settings,
                                    default_processes=default_processes)
    else:
        store = MemoryProcessStore(default_processes)
    return store
