import logging
from typing import TYPE_CHECKING

from pyramid.registry import Registry
from pyramid.request import Request
from pyramid.settings import asbool

from weaver.database.mongodb import MongoDatabase
from weaver.utils import get_registry, get_settings

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer


def get_db(container, reset_connection=False):
    # type: (AnySettingsContainer, bool) -> MongoDatabase
    """
    Obtains the database connection from configured application settings.

    If :paramref:`reset_connection` is ``True``, the :paramref:`container` must be the application :class:`Registry` or
    any container that can retrieve it to accomplish reference reset. Otherwise, any settings container can be provided.
    """
    registry = get_registry(container, nothrow=True)
    if not reset_connection and registry and registry.db:
        return registry.db
    database = MongoDatabase(container)
    if reset_connection:
        registry = get_registry(container)
        registry.db = database
    return database


def includeme(config):
    settings = get_settings(config)
    if asbool(settings.get("weaver.build_docs", False)):
        LOGGER.info("Skipping database when building docs...")
        return

    LOGGER.info("Adding database...")

    def _add_db(request):
        return MongoDatabase(request.registry)

    config.add_request_method(_add_db, "db", reify=True)
