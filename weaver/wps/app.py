"""
PyWPS 4.x wrapper.
"""
import logging
from typing import TYPE_CHECKING

from cornice.service import Service
from pyramid.wsgi import wsgiapp2

from weaver.formats import ContentType, OutputFormat
from weaver.wps.service import get_pywps_service
from weaver.wps.utils import get_wps_path
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from pyramid.config import Configurator

    from weaver.typedefs import AnyResponseType, SettingsType, ViewHandler

LOGGER = logging.getLogger(__name__)


@wsgiapp2
def pywps_view(environ, start_response):
    # type: (SettingsType, ViewHandler) -> AnyResponseType
    """
    Served location for PyWPS Service that provides WPS-1/2 XML endpoint.
    """
    LOGGER.debug("pywps env: %s", environ)
    service = get_pywps_service(environ)
    return service(environ, start_response)


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding Weaver WPS views.")
    wps_path = get_wps_path(config)
    wps_tags = [sd.TAG_GETCAPABILITIES, sd.TAG_DESCRIBEPROCESS, sd.TAG_EXECUTE, sd.TAG_WPS]
    LOGGER.debug("Adding WPS KVP/XML schemas.")
    wps_service = Service(name="wps", path=wps_path, content_type=ContentType.TEXT_XML)
    LOGGER.debug("Adding WPS KVP/XML views.")
    wps_service.add_view("GET", pywps_view, tags=wps_tags, renderer=OutputFormat.XML,
                         schema=sd.WPSEndpointGet(), response_schemas=sd.wps_responses)
    wps_service.add_view("POST", pywps_view, tags=wps_tags, renderer=OutputFormat.XML,
                         schema=sd.WPSEndpointPost(), response_schemas=sd.wps_responses)
    LOGGER.debug("Applying WPS KVP/XML service schemas with views to application.")
    # note:
    #   cannot use 'add_cornice_service' directive in this case
    #   it uses a decorator-wrapper that provides arguments in a different manner than what is expected by 'pywps_view'
    config.add_route(wps_service.name, path=wps_path)
    config.add_view(pywps_view, route_name=wps_service.name)
    # provide the route name explicitly to resolve the correct path when generating the OpenAPI definition
    wps_service.pyramid_route = wps_service.name
