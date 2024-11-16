import logging
from typing import TYPE_CHECKING

from pyramid.request import Request
from pyramid.settings import asbool

from weaver.database.mongodb import MongoDatabase
from weaver.utils import get_registry, get_settings

if TYPE_CHECKING:
    from typing import Union

    from pyramid.config import Configurator

    from weaver.database.base import DatabaseInterface
    from weaver.typedefs import AnyDatabaseContainer, AnyRegistryContainer, AnySettingsContainer

LOGGER = logging.getLogger(__name__)


def get_db(
    container=None,             # type: Union[AnyDatabaseContainer, AnyRegistryContainer, AnySettingsContainer, None]
    reset_connection=False,     # type: bool
):                              # type: (...) -> DatabaseInterface
    """
    Obtains the database connection from configured application settings.

    If :paramref:`reset_connection` is ``True``, the :paramref:`container` must be the application :class:`Registry` or
    any container that can retrieve it to accomplish reference reset. Otherwise, any settings container can be provided.

    .. note::
        It is preferable to provide a registry reference to reuse any available connection whenever possible.
        Giving application settings will require establishing a new connection.
    """
    if not reset_connection:
        if isinstance(container, MongoDatabase):
            return container
        if isinstance(container, Request):
            db = getattr(container, "db", None)
            if isinstance(db, MongoDatabase):
                return db
    registry = get_registry(container, nothrow=True)
    if not reset_connection and registry and isinstance(getattr(registry, "db", None), MongoDatabase):
        return registry.db
    database = MongoDatabase(container)
    if reset_connection and registry:
        registry.db = database
    return database


def includeme(config):
    # type: (Configurator) -> None
    settings = get_settings(config)
    if asbool(settings.get("weaver.build_docs", False)):  # pragma: no cover
        LOGGER.info("Skipping database when building docs...")
        return

    LOGGER.info("Adding database...")

    def _add_db(request):
        return MongoDatabase(request.registry)

    config.add_request_method(_add_db, "db", reify=True)
