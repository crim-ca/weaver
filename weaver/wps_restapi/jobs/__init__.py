import logging
from typing import TYPE_CHECKING

from pyramid.settings import asbool

from weaver.utils import get_settings

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding WPS REST API jobs...")
    config.include("weaver.wps_restapi.jobs.jobs")

    settings = get_settings(config)
    weaver_cwl_prov = asbool(settings.get("weaver.cwl_prov", True))
    if not weaver_cwl_prov:
        LOGGER.warning(
            "Skipping Weaver PROV views [weaver.cwl_prov=false]. "
            "Job Provenance endpoints will not be available."
        )
    else:
        LOGGER.info("Adding Weaver REST API Job Provenance....")
        config.include("weaver.wps_restapi.jobs.prov")
