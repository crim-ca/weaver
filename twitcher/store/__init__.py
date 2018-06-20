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
    #database = database or 'mongodb'
    database = None
    if database == 'mongodb':
        db = _mongodb(registry)
        store = MongodbTokenStore(db.tokens)
    else:
        store = MemoryTokenStore()
    return store


from twitcher.store.mongodb import MongodbServiceStore
from twitcher.store.memory import MemoryServiceStore
from twitcher.store.postgres import PostgresServiceStore


def my_import(name):
    components = name.split('.')
    mod = __import__(components[0])
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod


def servicestore_factory(registry, database=None, headers=None, db_session=None):
    """
    Creates a service store with the interface of :class:`twitcher.store.ServiceStore`.
    By default the mongodb implementation will be used.

    :return: An instance of :class:`twitcher.store.ServiceStore`.
    """
    settings = registry.settings
    if settings.get('twitcher.wps_provider_registry', 'default') != 'default':
        store_class = my_import(settings.get('twitcher.wps_provider_registry'))
        store = store_class(headers=headers)
    else:
        database = database or 'mongodb'
        if database == 'mongodb':
            db = _mongodb(registry)
            store = MongodbServiceStore(collection=db.services)
        elif database == 'postgres':
            store = PostgresServiceStore(db_session=db_session)
        else:
            store = MemoryServiceStore()
    return store
