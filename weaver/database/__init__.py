import logging
from typing import TYPE_CHECKING

from pyramid.settings import asbool

from weaver.database.mongodb import MongoDatabase
from weaver.utils import get_registry, get_settings

if TYPE_CHECKING:
    from typing import Optional

    from pyramid.config import Configurator

    from weaver.typedefs import AnyRegistryContainer

LOGGER = logging.getLogger(__name__)


def get_db(container=None, reset_connection=False):
    # type: (Optional[AnyRegistryContainer], bool) -> MongoDatabase
    """
    Obtains the database connection from configured application settings.

    If :paramref:`reset_connection` is ``True``, the :paramref:`container` must be the application :class:`Registry` or
    any container that can retrieve it to accomplish reference reset. Otherwise, any settings container can be provided.
    """
    registry = get_registry(container, nothrow=True)
    if not reset_connection and registry and isinstance(getattr(registry, "db", None), MongoDatabase):
        return registry.db
    database = MongoDatabase(container)
    if reset_connection:
        registry.db = database
    return database


def includeme(config):
    # type: (Configurator) -> None
    settings = get_settings(config)
    if asbool(settings.get("weaver.build_docs", False)):
        LOGGER.info("Skipping database when building docs...")
        return

    LOGGER.info("Adding database...")

    def _add_db(request):
        return MongoDatabase(request.registry)

    config.add_request_method(_add_db, "db", reify=True)
