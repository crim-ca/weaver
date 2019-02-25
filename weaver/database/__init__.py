from pyramid.config import Configurator
from pyramid.registry import Registry
from pyramid.request import Request
from typing import Union, TYPE_CHECKING
import logging
LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from weaver.database.mongodb import MongoDatabase


def get_db(container):
    # type: (Union[Configurator, Registry, Request]) -> MongoDatabase
    if isinstance(container, (Configurator, Request)):
        return container.registry.db
    if isinstance(container, Registry):
        return container.db
    raise NotImplementedError("Could not obtain database from [{}].".format(type(container)))


def includeme(config):
    LOGGER.info("Adding database...")
    from weaver.database.mongodb import MongoDatabase
    config.registry.db = MongoDatabase(config.registry)

    def _add_db(request):
        db = request.registry.db
        # if db_url.username and db_url.password:
        #     db.authenticate(db_url.username, db_url.password)
        return db
    config.add_request_method(_add_db, 'db', reify=True)
