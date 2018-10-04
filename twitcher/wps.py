"""
pywps 4.x wrapper
"""
import os

from pyramid.response import Response
from pyramid.wsgi import wsgiapp2
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.settings import asbool, aslist
from six.moves.configparser import SafeConfigParser
import six

from twitcher.processes import processes
from twitcher.owsexceptions import OWSNoApplicableCode
from twitcher.utils import get_twitcher_url

import logging
LOGGER = logging.getLogger(__name__)

# can be overridden with 'settings.wps-cfg'
DEFAULT_PYWPS_CFG = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'wps.cfg')


def get_wps_cfg_path(settings):
    return settings.get('twitcher.wps_cfg', DEFAULT_PYWPS_CFG)


def get_wps_path(settings):
    wps_path = settings.get('twitcher.wps_path')
    if not wps_path:
        wps_cfg = get_wps_cfg_path(settings)
        config = SafeConfigParser()
        config.read(wps_cfg)
        wps_path = config.get('server', 'url')
    if not isinstance(wps_path, six.string_types):
        LOGGER.warn("WPS path not set in configuration, using default value.")
        wps_path = '/ows/wps'
    return wps_path.rstrip('/').strip()


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
        environ['PYWPS_CFG'] = DEFAULT_PYWPS_CFG
    service = Service(processes, [environ['PYWPS_CFG']])
    return service(environ, start_response)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.wps', True)):
        LOGGER.debug("Twitcher WPS enabled.")

        # include twitcher config
        config.include('twitcher.config')

        wps_path = get_wps_path(settings)
        config.add_route('wps', wps_path)
        config.add_route('wps_secured', wps_path + '/{access_token}')
        config.add_view(pywps_view, route_name='wps')
        config.add_view(pywps_view, route_name='wps_secured')
        config.add_request_method(lambda req: get_wps_cfg_path(req.registry.settings), 'wps_cfg', reify=True)
