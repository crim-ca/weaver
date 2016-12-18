"""
pywps 4.x wrapper
"""
import os

from pyramid.response import Response
from pyramid.wsgi import wsgiapp2
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.settings import asbool, aslist

from pywps.app.Service import Service
from twitcher.processes import processes
from twitcher.owsexceptions import OWSNoApplicableCode

import logging
logger = logging.getLogger(__name__)

DEFAULT_KEYS = ['PYWPS_CFG', 'DODS_CONF', 'HOME']
PYWPS_CFG = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'wps.cfg')


def _wps_cfg(request):
    settings = request.registry.settings
    return settings.get('twitcher.wps_cfg')


def _wps_environ_keys(request):
    settings = request.registry.settings
    if 'twitcher.wps_environ_keys' in settings:
        keys = aslist(settings['twitcher.wps_environ_keys'])
    else:
        keys = DEFAULT_KEYS
    return keys


@wsgiapp2
def pywps_view(environ, start_response):
    """
    * TODO: add xml response renderer
    * TODO: fix exceptions ... use OWSException (raise ...)
    """
    # set the environ for wps from request environ
    # for key in request.wps_environ_keys:
    #    if key in request.environ:
    #        os.environ[key] = request.environ[key]

    logger.debug('pywps env: %s', environ.keys())

    # call pywps application
    if 'PYWPS_CFG' not in environ:
        environ['PYWPS_CFG'] = PYWPS_CFG
    service = Service(processes, [environ['PYWPS_CFG']])
    return service(environ, start_response)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.wps', True)):
        config.add_route('wps', '/ows/wps')
        config.add_route('wps_secured', '/ows/wps/{access_token}')
        config.add_view(pywps_view, route_name='wps')
        config.add_view(pywps_view, route_name='wps_secured')
        config.add_request_method(_wps_environ_keys, 'wps_environ_keys', reify=True)
        config.add_request_method(_wps_cfg, 'wps_cfg', reify=True)
