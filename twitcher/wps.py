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

DEFAULT_KEYS = ['PYWPS_CFG', 'PYWPS_PROCESSES', 'PYWPS_TEMPLATES', 'DODS_CONF']


def _wps_environ_keys(request):
    settings = request.registry.settings
    if 'twitcher.wps_environ_keys' in settings:
        keys = aslist(settings['twitcher.wps_environ_keys'])
    else:
        keys = DEFAULT_KEYS
    return keys


def _wps_cfg(request):
    settings = request.registry.settings
    return settings.get('twitcher.wps_cfg')


def pywps_view2(request):
    """
    * TODO: add xml response renderer
    * TODO: fix exceptions ... use OWSException (raise ...)
    """
    if request.wps_cfg:
        os.environ['PYWPS_CFG'] = request.wps_cfg

    # set the environ for wps from request environ
    for key in request.wps_environ_keys:
        if key in request.environ:
            os.environ[key] = request.environ[key]

    # create the WPS object
    service = request.context
    return Response(service)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.wps', True)):
        # convert pywps app to pyramid view
        pywps_app = Service(processes, ['wps.cfg'])
        pywps_view = wsgiapp2(pywps_app)

        config.add_route('wps', '/ows/wps')
        config.add_route('wps_secured', '/ows/wps/{access_token}')
        config.add_view(pywps_view, route_name='wps')
        config.add_view(pywps_view, route_name='wps_secured')
        config.add_request_method(_wps_environ_keys, 'wps_environ_keys', reify=True)
        config.add_request_method(_wps_cfg, 'wps_cfg', reify=True)
