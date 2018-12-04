"""
Factories to create storage backends.
"""

# Factories
from twitcher.db import get_mongodb_engine
# Interfaces
from twitcher.store.memory import (
    MemoryTokenStore,
    MemoryServiceStore,
    MemoryProcessStore,
    MemoryJobStore,
    MemoryQuoteStore,
    MemoryBillStore,
)
from twitcher.store.mongodb import (
    MongodbTokenStore,
    MongodbServiceStore,
    MongodbProcessStore,
    MongodbJobStore,
    MongodbQuoteStore,
    MongodbBillStore,
)
from twitcher.processes import default_processes

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
        db = get_mongodb_engine(registry)
        store = MongodbTokenStore(db.tokens)
    else:
        store = MemoryTokenStore()
    return store


service_store = None


def servicestore_defaultfactory(registry):
    """
    Creates a service store with the interface of :class:`twitcher.store.ServiceStore`.

    :param registry: Application registry defining `twitcher.db_factory`.
    :return: An instance of :class:`twitcher.store.ServiceStore`.
    """
    database = get_db_factory(registry)
    if database == DB_MONGODB:
        db = get_mongodb_engine(registry)
        return MongodbServiceStore(collection=db.services)
    global service_store
    if service_store is None:
        service_store = MemoryServiceStore()
    return service_store


def processstore_defaultfactory(registry):
    """
    Creates a process store with the interface of :class:`twitcher.store.ProcessStore`.
    By default the mongodb implementation will be used.

    :return: An instance of :class:`twitcher.store.ProcessStore`.
    """
    database = get_db_factory(registry)
    if database == DB_MONGODB:
        db = get_mongodb_engine(registry)
        store = MongodbProcessStore(collection=db.processes, settings=registry.settings,
                                    default_processes=default_processes)
    else:
        store = MemoryProcessStore(default_processes)
    return store


def jobstore_defaultfactory(registry):
    """
    Creates a job store with the interface of :class:`twitcher.store.JobStore`.

    :param registry: Application registry defining `twitcher.db_factory`.
    :return: An instance of :class:`twitcher.store.JobStore`.
    """
    database = get_db_factory(registry)
    if database == DB_MONGODB:
        db = get_mongodb_engine(registry)
        store = MongodbJobStore(collection=db.jobs)
    else:
        store = MemoryJobStore()
    return store


def quotestore_defaultfactory(registry):
    """
    Creates a quote store with the interface of :class:`twitcher.store.QuoteStore`.

    :param registry: Application registry defining `twitcher.db_factory`.
    :return: An instance of :class:`twitcher.store.QuoteStore`.
    """
    database = get_db_factory(registry)
    if database == DB_MONGODB:
        db = get_mongodb_engine(registry)
        store = MongodbQuoteStore(collection=db.quotes)
    else:
        store = MemoryQuoteStore()
    return store


def billstore_defaultfactory(registry):
    """
    Creates a bill store with the interface of :class:`twitcher.store.BillStore`.

    :param registry: Application registry defining `twitcher.db_factory`.
    :return: An instance of :class:`twitcher.store.BillStore`.
    """
    database = get_db_factory(registry)
    if database == DB_MONGODB:
        db = get_mongodb_engine(registry)
        store = MongodbBillStore(collection=db.bills)
    else:
        store = MemoryBillStore()
    return store
