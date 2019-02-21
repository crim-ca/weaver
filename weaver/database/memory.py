from weaver.database.base import DatabaseInterface
from weaver.store.base import StoreInterface
from weaver.store.memory import (
    MemoryServiceStore,
    MemoryProcessStore,
    MemoryJobStore,
    MemoryQuoteStore,
    MemoryBillStore,
)
from typing import Any, AnyStr

MemoryStores = frozenset([
    MemoryServiceStore,
    MemoryProcessStore,
    MemoryJobStore,
    MemoryQuoteStore,
    MemoryBillStore,
])


class MemoryDatabase(DatabaseInterface):
    _database = None
    _settings = None
    _stores = None
    type = 'memory'

    def __init__(self, registry):
        super(MemoryDatabase, self).__init__(registry)
        self._database = dict()
        self._settings = registry.settings
        self._stores = dict()

    def is_ready(self):
        return self._database is not None and self._settings is not None

    def rollback(self):
        pass

    def get_session(self):
        return self._database

    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (AnyStr, Any, Any) -> StoreInterface
        for store in MemoryStores:
            if store.type == store_type:
                if store_type not in self._database:
                    self._database[store_type] = store(*store_args, **store_kwargs)
                return self._database[store_type]
        raise NotImplementedError("Database `{}` cannot find matching store `{}`.".format(self.type, store_type))

    def get_information(self):
        return {'version': '0', 'type': self.type}

    def run_migration(self):
        pass
