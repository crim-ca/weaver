# MongoDB
# http://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/database/mongodb.html
import logging
import uuid
import warnings
from typing import TYPE_CHECKING, overload

import pymongo
import pymongo.errors

from weaver.database.base import DatabaseInterface
from weaver.store.mongodb import (
    MongodbBillStore,
    MongodbJobStore,
    MongodbProcessStore,
    MongodbQuoteStore,
    MongodbServiceStore,
    MongodbVaultStore
)
from weaver.utils import get_settings, is_uuid

if TYPE_CHECKING:
    from typing import Any, Optional, Type, Union

    from pymongo.database import Database

    from weaver.database.base import (
        StoreSelector,
        StoreBillsSelector,
        StoreJobsSelector,
        StoreProcessesSelector,
        StoreQuotesSelector,
        StoreServicesSelector,
        StoreVaultSelector
    )
    from weaver.typedefs import AnySettingsContainer, JSON

LOGGER = logging.getLogger(__name__)

# pylint: disable=C0103,invalid-name
MongoDB = None  # type: Optional[Database]
MongodbStores = frozenset([
    MongodbServiceStore,
    MongodbProcessStore,
    MongodbJobStore,
    MongodbQuoteStore,
    MongodbBillStore,
    MongodbVaultStore,
])

if TYPE_CHECKING:
    # pylint: disable=E0601,used-before-assignment
    AnyMongodbStore = Union[
        MongodbServiceStore,
        MongodbProcessStore,
        MongodbJobStore,
        MongodbQuoteStore,
        MongodbBillStore,
        MongodbVaultStore,
    ]
    AnyMongodbStoreType = Union[
        StoreSelector,
        AnyMongodbStore,
        Type[MongodbServiceStore],
        Type[MongodbProcessStore],
        Type[MongodbJobStore],
        Type[MongodbQuoteStore],
        Type[MongodbBillStore],
        Type[MongodbVaultStore],
    ]


class MongoDatabase(DatabaseInterface):
    _revision = 1
    _database = None
    _settings = None
    _stores = None
    type = "mongodb"

    def __init__(self, container):
        # type: (AnySettingsContainer) -> None
        super(MongoDatabase, self).__init__(container)
        self._database = get_mongodb_engine(container)
        self._settings = get_settings(container)
        self._stores = {}
        LOGGER.debug("Database [%s] using versions: {MongoDB: %s, pymongo: %s}",
                     self._database.name, self._database.client.server_info()["version"], pymongo.__version__)

    def reset_store(self, store_type):
        # type: (StoreSelector) -> AnyMongodbStore
        store_type = self._get_store_type(store_type)
        return self._stores.pop(store_type, None)

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreBillsSelector, *Any, **Any) -> MongodbBillStore
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreQuotesSelector, *Any, **Any) -> MongodbQuoteStore
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreJobsSelector, *Any, **Any) -> MongodbJobStore
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreProcessesSelector, *Any, **Any) -> MongodbProcessStore
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreServicesSelector, *Any, **Any) -> MongodbServiceStore
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreVaultSelector, *Any, **Any) -> MongodbVaultStore
        ...

    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreSelector, *Any, **Any) -> AnyMongodbStore
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
        raise NotImplementedError(f"Database '{self.type}' cannot find matching store '{store_type}'.")

    def get_session(self):
        # type: (...) -> Any
        return self._database

    def get_information(self):
        # type: (...) -> JSON
        """
        Obtain information about the database implementation.

        :returns: JSON with parameters: ``{"version": "<version>", "type": "<db_type>"}``.
        """
        result = list(self._database.version.find().limit(1))
        revision = result[0]["revision"] if result else 0
        return {"version": revision, "type": self.type}

    def is_ready(self):
        # type: (...) -> bool
        return self._database is not None and self._settings is not None

    def run_migration(self):
        # type: (...) -> None
        """
        Runs any necessary data-schema migration steps.
        """
        db_info = self.get_information()
        LOGGER.info("Running database migration as needed for %s", db_info)
        version = db_info["version"]
        assert self._revision >= version, "Cannot process future DB revision."
        for rev in range(version, self._revision):
            from_to_msg = f"[Migrating revision: {rev} -> {rev + 1}]"

            if rev == 0:
                LOGGER.info("%s Convert objects with string for UUID-like fields to real UUID types.", from_to_msg)
                collection = self._database.jobs
                for cur in collection.find({"id": {"$type": "string"}}):
                    collection.update_one(
                        {"_id": cur["_id"]},
                        {"$set": {
                            "id": uuid.UUID(str(cur["id"])),
                            "task_id": uuid.UUID(str(cur["task_id"])) if is_uuid(cur["task_id"]) else cur["task_id"],
                            "wps_id": uuid.UUID(str(cur["wps_id"])) if is_uuid(cur["wps_id"]) else None
                        }}
                    )
                for collection in [self._database.bills, self._database.quotes]:
                    for cur in collection.find({"id": {"$type": "string"}}):
                        collection.update_one({"_id": cur["_id"]}, {"$set": {"id": uuid.UUID(str(cur["id"]))}})

            # NOTE: add any needed migration revisions here with (if rev = next-index)...

            # update and move to next revision
            self._database.version.update_one({"revision": rev}, {"$set": {"revision": rev + 1}}, upsert=True)
            db_info["version"] = rev
        LOGGER.info("Database up-to-date with: %s", db_info)


def get_mongodb_connection(container):
    # type: (AnySettingsContainer) -> Database
    """
    Obtains the basic database connection from settings.
    """
    settings = get_settings(container)
    settings_default = [("mongodb.host", "localhost"), ("mongodb.port", 27017), ("mongodb.db_name", "weaver")]
    for setting, default in settings_default:
        if settings.get(setting, None) is None:
            warnings.warn(f"Setting '{setting}' not defined in registry, using default [{default}].")
            settings[setting] = default
    client = pymongo.MongoClient(settings["mongodb.host"], int(settings["mongodb.port"]), connect=False,
                                 # Must specify representation since PyMongo 4.0 and also to avoid Python 3.6 error
                                 #  https://pymongo.readthedocs.io/en/stable/examples/uuid.html#unspecified
                                 uuidRepresentation="pythonLegacy",
                                 # Require that datetime objects be returned with timezone awareness.
                                 # This ensures that missing 'tzinfo' does not get misinterpreted as locale time when
                                 # loading objects from DB, since by default 'datetime.datetime' employs 'tzinfo=None'
                                 # for locale naive datetime objects, while MongoDB stores Date in ISO-8601 format.
                                 tz_aware=True)
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
