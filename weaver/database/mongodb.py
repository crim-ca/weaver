# MongoDB
# http://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/database/mongodb.html
import warnings
from typing import TYPE_CHECKING, overload

import pymongo

from weaver.database.base import DatabaseInterface
from weaver.store.base import StoreInterface
from weaver.store.mongodb import (
    MongodbBillStore,
    MongodbJobStore,
    MongodbProcessStore,
    MongodbQuoteStore,
    MongodbServiceStore
)
from weaver.utils import get_settings

if TYPE_CHECKING:
    from typing import Any, Optional, Type, Union

    from pymongo.database import Database

    from weaver.database.base import StoreSelector
    from weaver.store.base import StoreBills, StoreJobs, StoreProcesses, StoreQuotes, StoreServices
    from weaver.typedefs import AnySettingsContainer, JSON

# pylint: disable=C0103,invalid-name
MongoDB = None  # type: Optional[Database]
MongodbStores = frozenset([
    MongodbServiceStore,
    MongodbProcessStore,
    MongodbJobStore,
    MongodbQuoteStore,
    MongodbBillStore,
])

if TYPE_CHECKING:
    # pylint: disable=E0601,used-before-assignment
    AnyMongodbStore = Union[MongodbStores]
    AnyMongodbStoreType = Union[
        StoreSelector,
        AnyMongodbStore,
        Type[MongodbServiceStore],
        Type[MongodbProcessStore],
        Type[MongodbJobStore],
        Type[MongodbQuoteStore],
        Type[MongodbBillStore],
    ]


class MongoDatabase(DatabaseInterface):
    _database = None
    _settings = None
    _stores = None
    type = "mongodb"

    def __init__(self, container):
        # type: (AnySettingsContainer) -> None
        super(MongoDatabase, self).__init__(container)
        self._database = get_mongodb_engine(container)
        self._settings = get_settings(container)
        self._stores = dict()

    def reset_store(self, store_type):
        store_type = self._get_store_type(store_type)
        return self._stores.pop(store_type, None)

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (Type[StoreBills], *Any, **Any) -> MongodbBillStore
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (Type[StoreQuotes], *Any, **Any) -> MongodbQuoteStore
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (Type[StoreJobs], *Any, **Any) -> MongodbJobStore
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (Type[StoreProcesses], *Any, **Any) -> MongodbProcessStore
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (Type[StoreServices], *Any, **Any) -> MongodbServiceStore
        ...

    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (Union[str, Type[StoreInterface], AnyMongodbStoreType], *Any, **Any) -> AnyMongodbStore
        """
        Retrieve a store from the database.

        :param store_type: type of the store to retrieve/create.
        :param store_args: additional arguments to pass down to the store.
        :param store_kwargs: additional keyword arguments to pass down to the store.
        """
        store_type = self._get_store_type(store_type)

        for store in MongodbStores:
            if store.type == store_type:
                if store_type not in self._stores:
                    if "settings" not in store_kwargs:
                        store_kwargs["settings"] = self._settings
                    self._stores[store_type] = store(
                        collection=getattr(self.get_session(), store_type),
                        *store_args, **store_kwargs
                    )
                return self._stores[store_type]
        raise NotImplementedError("Database '{}' cannot find matching store '{}'.".format(self.type, store_type))

    def get_session(self):
        # type: (...) -> Any
        return self._database

    def get_information(self):
        # type: (...) -> JSON
        """
        Obtain information about the database implementation.

        :returns: JSON with parameters: ``{"version": "<version>", "type": "<db_type>"}``.
        """
        result = list(self._database.version.find().limit(1))[0]
        db_version = result["version_num"]
        return {"version": db_version, "type": self.type}

    def is_ready(self):
        # type: (...) -> bool
        return self._database is not None and self._settings is not None

    def run_migration(self):
        # type: (...) -> None
        warnings.warn("Not implemented {}.run_migration implementation.".format(self.type))


def get_mongodb_connection(container):
    # type: (AnySettingsContainer) -> Database
    """
    Obtains the basic database connection from settings.
    """
    settings = get_settings(container)
    settings_default = [("mongodb.host", "localhost"), ("mongodb.port", 27017), ("mongodb.db_name", "weaver")]
    for setting, default in settings_default:
        if settings.get(setting, None) is None:
            warnings.warn("Setting '{}' not defined in registry, using default [{}].".format(setting, default))
            settings[setting] = default
    client = pymongo.MongoClient(settings["mongodb.host"], int(settings["mongodb.port"]), connect=False)
    return client[settings["mongodb.db_name"]]


def get_mongodb_engine(container):
    # type: (AnySettingsContainer) -> Database
    """
    Obtains the database with configuration ready for usage.
    """
    db = get_mongodb_connection(container)
    db.services.create_index("name", unique=True)
    db.services.create_index("url", unique=True)
    db.processes.create_index("identifier", unique=True)
    db.jobs.create_index("id", unique=True)
    db.quotes.create_index("id", unique=True)
    db.bills.create_index("id", unique=True)
    return db
