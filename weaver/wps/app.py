"""
pywps 4.x wrapper
"""
import logging

from pyramid.wsgi import wsgiapp2

from weaver.wps.service import get_pywps_service

LOGGER = logging.getLogger(__name__)


@wsgiapp2
def pywps_view(environ, start_response):
    """
    Served location for PyWPS Service that provides WPS-1/2 XML endpoint.
    """
    LOGGER.debug("pywps env: %s", environ)
    service = get_pywps_service(environ)
    return service(environ, start_response)
