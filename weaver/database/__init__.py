from weaver.utils import get_registry
from typing import TYPE_CHECKING
import logging
LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from weaver.database.mongodb import MongoDatabase
    from weaver.typedefs import AnyDatabaseContainer


def get_db(container):
    # type: (AnyDatabaseContainer) -> MongoDatabase
    registry = get_registry(container)
    return registry.db


def includeme(config):
    LOGGER.info("Adding database...")
    from weaver.database.mongodb import MongoDatabase
    config.registry.db = MongoDatabase(config.registry)

    def _add_db(request):
        db = request.registry.db
        # if db_url.username and db_url.password:
        #     db.authenticate(db_url.username, db_url.password)
        return db
    config.add_request_method(_add_db, "db", reify=True)
