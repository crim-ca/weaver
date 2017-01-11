"""
pywps 4.x wrapper
"""
import os

from pyramid.response import Response
from pyramid.wsgi import wsgiapp2
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.settings import asbool, aslist

from twitcher.processes import processes
from twitcher.owsexceptions import OWSNoApplicableCode


import logging
LOGGER = logging.getLogger(__name__)

PYWPS_CFG = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'wps.cfg')


def _wps_cfg(request):
    settings = request.registry.settings
    return settings.get('twitcher.wps_cfg')


@wsgiapp2
def pywps_view(environ, start_response):
    """
    * TODO: add xml response renderer
    * TODO: fix exceptions ... use OWSException (raise ...)
    """
    from pywps.app.Service import Service
    LOGGER.debug('pywps env: %s', environ.keys())

    # call pywps application
    if 'PYWPS_CFG' not in environ:
        environ['PYWPS_CFG'] = PYWPS_CFG
    service = Service(processes, [environ['PYWPS_CFG']])
    return service(environ, start_response)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.wps', True)):
        LOGGER.debug("Twitcher WPS enabled.")

        # include twitcher config
        config.include('twitcher.config')

        config.add_route('wps', '/ows/wps')
        config.add_route('wps_secured', '/ows/wps/{access_token}')
        config.add_view(pywps_view, route_name='wps')
        config.add_view(pywps_view, route_name='wps_secured')
        config.add_request_method(_wps_cfg, 'wps_cfg', reify=True)
