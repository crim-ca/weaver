import logging
from typing import TYPE_CHECKING

from pyramid.settings import asbool

from weaver.utils import get_settings

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None
    settings = get_settings(config)
    if asbool(settings.get("weaver.vault", True)):
        LOGGER.info("Adding file vault...")
        config.include("weaver.vault.views")
