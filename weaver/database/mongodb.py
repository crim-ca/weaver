# MongoDB
# http://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/database/mongodb.html
from weaver.database.base import DatabaseInterface
from weaver.store.mongodb import (
    MongodbServiceStore,
    MongodbProcessStore,
    MongodbJobStore,
    MongodbQuoteStore,
    MongodbBillStore,
)
from typing import Any, AnyStr, Union
import pymongo
import warnings

MongoDB = None
MongodbStores = Union[
    MongodbServiceStore,
    MongodbProcessStore,
    MongodbJobStore,
    MongodbQuoteStore,
    MongodbBillStore,
]


class MongoDatabase(DatabaseInterface):
    _database = None
    _settings = None
    type = 'mongodb'

    def __init__(self, registry):
        super(MongoDatabase, self).__init__(registry)
        self._database = get_mongodb_engine(registry)
        self._settings = registry.settings

    def is_ready(self):
        return self._database is not None and self._settings is not None

    def rollback(self):
        pass

    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (AnyStr, Any, Any) -> MongodbStores
        for store in MongodbStores:
            if store.type == store_type:
                return store(collection=getattr(self.get_session(), store_type), *store_args, **store_kwargs)
        raise NotImplementedError("Database `{}` cannot find matching store `{}`.".format(self.type, store_type))

    def get_session(self):
        return self._database

    def get_information(self):
        result = list(self._database.version.find().limit(1))[0]
        db_version = result['version_num']
        return {'version': db_version, 'type': self.type}

    def run_migration(self):
        warnings.warn("Not implemented {}.run_migration implementation.".format(self.type))
        pass


def get_mongodb_client(registry):
    global MongoDB
    if not MongoDB:
        settings = registry.settings
        client = pymongo.MongoClient(settings['mongodb.host'], int(settings['mongodb.port']))
        MongoDB = client[settings['mongodb.db_name']]
    return MongoDB


def get_mongodb_engine(registry):
    db = get_mongodb_client(registry)
    db.services.create_index("name", unique=True)
    db.services.create_index("url", unique=True)
    db.processes.create_index("identifier", unique=True)
    db.jobs.create_index("id", unique=True)
    db.quotes.create_index("id", unique=True)
    db.bills.create_index("id", unique=True)
    return db
