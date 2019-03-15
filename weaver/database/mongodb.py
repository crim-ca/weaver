# MongoDB
# http://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/database/mongodb.html
from weaver.database.base import DatabaseInterface
from weaver.store.base import StoreInterface
from weaver.store.mongodb import (
    MongodbServiceStore,
    MongodbProcessStore,
    MongodbJobStore,
    MongodbQuoteStore,
    MongodbBillStore,
)
from weaver.utils import get_settings
from typing import TYPE_CHECKING
import warnings
import pymongo
if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer
    from typing import Any, AnyStr, Union
    from pymongo.database import Database

MongoDB = None  # type: Database
MongodbStores = frozenset([
    MongodbServiceStore,
    MongodbProcessStore,
    MongodbJobStore,
    MongodbQuoteStore,
    MongodbBillStore,
])

if TYPE_CHECKING:
    AnyStoreType = Union[MongodbStores]
    from weaver.typedefs import JSON


class MongoDatabase(DatabaseInterface):
    _database = None
    _settings = None
    _stores = None
    type = "mongodb"

    def __init__(self, registry, reset_connection=False):
        super(MongoDatabase, self).__init__(registry)
        self._database = get_mongodb_engine(registry, reset_connection)
        self._settings = registry.settings
        self._stores = dict()

    def is_ready(self):
        # type: (...) -> bool
        return self._database is not None and self._settings is not None

    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (Union[AnyStr, StoreInterface, MongodbStores], Any, Any) -> AnyStoreType
        """
        Retrieve a store from the database.

        :param store_type: type of the store to retrieve/create.
        :param store_args: additional arguments to pass down to the store.
        :param store_kwargs: additional keyword arguments to pass down to the store.
        """
        if isinstance(store_type, StoreInterface) or issubclass(store_type, StoreInterface):
            store_type = store_type.type

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
        :returns: {'version': version, 'type': db_type}
        """
        result = list(self._database.version.find().limit(1))[0]
        db_version = result["version_num"]
        return {"version": db_version, "type": self.type}

    def run_migration(self):
        # type: (...) -> None
        warnings.warn("Not implemented {}.run_migration implementation.".format(self.type))
        pass


def get_mongodb_connection(container, reset_connection=False):
    # type: (AnySettingsContainer, bool) -> Database
    """Obtains the basic database connection from settings."""
    global MongoDB
    if reset_connection:
        MongoDB = None
    if not MongoDB:
        settings = get_settings(container)
        settings_default = [("mongodb.host", "localhost"), ("mongodb.port", 27017), ("mongodb.db_name", "weaver")]
        for setting, default in settings_default:
            if settings.get(setting, None) is None:
                warnings.warn("Setting '{}' not defined in registry, using default [{}].".format(setting, default))
                settings[setting] = default
        client = pymongo.MongoClient(settings["mongodb.host"], int(settings["mongodb.port"]))
        MongoDB = client[settings["mongodb.db_name"]]
    return MongoDB


def get_mongodb_engine(container, reset_connection=False):
    # type: (AnySettingsContainer, bool) -> Database
    """Obtains the database with configuration ready for usage."""
    db = get_mongodb_connection(container, reset_connection)
    db.services.create_index("name", unique=True)
    db.services.create_index("url", unique=True)
    db.processes.create_index("identifier", unique=True)
    db.jobs.create_index("id", unique=True)
    db.quotes.create_index("id", unique=True)
    db.bills.create_index("id", unique=True)
    return db
