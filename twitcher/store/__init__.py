"""
Factories to create storage backends.
"""

# Factories
from twitcher.db import mongodb as mongodb_factory
# Interfaces
from twitcher.store.memory import MemoryTokenStore, MemoryServiceStore, MemoryJobStore
from twitcher.store.mongodb import MongodbTokenStore, MongodbServiceStore, MongodbJobStore

# TODO: add any other db factory configuration here as needed
DB_MONGODB = 'mongodb'
DB_MEMORY = 'memory'
SUPPORTED_DB_FACTORIES = frozenset([DB_MONGODB, DB_MEMORY])


def get_db_factory(registry):
    """
    Obtains `twitcher.db_factory` from `config.registry.settings` and validates it.
    :returns: A string representing the configured database factory. (default: 'mongodb')
    """
    settings = registry.settings
    db_factory = settings.get('twitcher.db_factory', DB_MONGODB)
    if db_factory in SUPPORTED_DB_FACTORIES:
        return db_factory
    raise NotImplementedError("Unknown settings `twitcher.db_factory` == `{}`.".format(str(db_factory)))


def tokenstore_factory(registry):
    """
    Creates a token store with the interface of :class:`twitcher.store.AccessTokenStore`.
    By default the mongodb implementation will be used.

    :param registry: Application registry defining `twitcher.db_factory`.
    :return: An instance of :class:`twitcher.store.AccessTokenStore`.
    """
    database = get_db_factory(registry)
    if database == DB_MONGODB:
        db = mongodb_factory(registry)
        store = MongodbTokenStore(db.tokens)
    else:
        store = MemoryTokenStore()
    return store


def servicestore_defaultfactory(registry):
    """
    Creates a service store with the interface of :class:`twitcher.store.ServiceStore`.

    :param registry: Application registry defining `twitcher.db_factory`.
    :return: An instance of :class:`twitcher.store.ServiceStore`.
    """
    database = get_db_factory(registry)
    if database == DB_MONGODB:
        db = mongodb_factory(registry)
        store = MongodbServiceStore(collection=db.services)
    else:
        store = MemoryServiceStore()
    return store


def jobstore_defaultfactory(registry):
    """
    Creates a job store with the interface of :class:`twitcher.store.JobStore`.

    :param registry: Application registry defining `twitcher.db_factory`.
    :return: An instance of :class:`twitcher.store.JobStore`.
    """
    database = get_db_factory(registry)
    if database == DB_MONGODB:
        db = mongodb_factory(registry)
        store = MongodbJobStore(collection=db.jobs)
    else:
        store = MemoryJobStore()
    return store
