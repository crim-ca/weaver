from typing import Any, AnyStr, Dict, Union, TYPE_CHECKING
from pyramid.registry import Registry
import logging
logger = logging.getLogger(__name__)
if TYPE_CHECKING:
    from twitcher.store.base import AccessTokenStore, ServiceStore, ProcessStore, JobStore, QuoteStore, BillStore
    AnyStoreType = Union[AccessTokenStore, ServiceStore, ProcessStore, JobStore, QuoteStore, BillStore]


class DatabaseInterface(object):
    """Return the unique identifier of db type matching settings."""
    type = None

    # noinspection PyUnusedLocal
    def __init__(self, registry):
        if not self.type:
            raise ValueError("Database 'type' must be overridden in inheriting class.")

    def is_ready(self):
        # type: (...) -> bool
        raise NotImplementedError

    def run_migration(self):
        # type: (...) -> None
        raise NotImplementedError

    def rollback(self):
        # type: (...) -> None
        """Rollback current database transaction."""
        raise NotImplementedError

    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (AnyStr, Any, Any) -> AnyStoreType
        """
        Retrieve a store from the database.

        :param store_type: type of the store to retrieve/create.
        :param store_args: additional arguments to pass down to the store.
        :param store_kwargs: additional keyword arguments to pass down to the store.
        """
        raise NotImplementedError

    def get_session(self):
        # type: (...) -> Any
        raise NotImplementedError

    def get_information(self):
        # type: (...) -> Dict[AnyStr, AnyStr]
        """
        :returns: {'version': version, 'type': db_type}
        """
        raise NotImplementedError

    def get_revision(self):
        # type: (...) -> AnyStr
        return self.get_information().get('version')


def get_database_factory_type(registry):
    # type: (Registry) -> AnyStr
    """
    Obtains `twitcher.db_factory` from `config.registry.settings` and validates it.
    :returns: A string representing the configured database factory. (default: 'mongodb')
    """
    from twitcher.database.postgres import PostgresDatabase
    from twitcher.database.mongodb import MongoDatabase
    from twitcher.database.memory import MemoryDatabase

    settings = registry.settings
    db_factory = settings.get('twitcher.db_factory', MongoDatabase.type)
    if db_factory in frozenset([PostgresDatabase.type, MongoDatabase.type, MemoryDatabase.type]):
        return db_factory
    raise NotImplementedError("Unknown settings `twitcher.db_factory` == `{}`.".format(str(db_factory)))


def get_database_factory(registry):
    # type: (Registry) -> DatabaseInterface
    """Get the database factory corresponding to setting `twitcher.db_factory`."""
    from twitcher.database.postgres import PostgresDatabase
    from twitcher.database.mongodb import MongoDatabase
    from twitcher.database.memory import MemoryDatabase

    db_type = get_database_factory_type(registry)
    if db_type == PostgresDatabase.type:
        return PostgresDatabase(registry.settings)
    elif db_type == MongoDatabase.type:
        return MongoDatabase(registry)
    return MemoryDatabase(registry)
