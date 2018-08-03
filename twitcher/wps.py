"""
pywps 4.x wrapper
"""
import os

from pyramid.response import Response
from pyramid.wsgi import wsgiapp2
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.settings import asbool, aslist
from pyramid_celery import celery_app as app

from twitcher.processes import default_processes
from twitcher.store import processstore_defaultfactory
from twitcher.owsexceptions import OWSNoApplicableCode


import logging
LOGGER = logging.getLogger(__name__)

PYWPS_CFG = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'wps.cfg')


def _wps_cfg(request):
    settings = request.registry.settings
    return settings.get('twitcher.wps_cfg')


def _processes(request):
    return processstore_defaultfactory(request.registry)


#@app.task(bind=True)
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

    registry = app.conf['PYRAMID_REGISTRY']
    processstore = processstore_defaultfactory(registry)
    processes_wps = [process.wps() for process in processstore.list_processes()]
    service = Service(processes_wps, [environ['PYWPS_CFG']])
    return service(environ, start_response)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.wps', True)):
        LOGGER.debug("Twitcher WPS enabled.")

        # include twitcher config
        config.include('twitcher.config')

        wps_path = settings.get('twitcher.wps_path', '/ows/wps').rstrip('/').strip()
        config.add_route('wps', wps_path)
        config.add_route('wps_secured', wps_path + '/{access_token}')
        config.add_view(pywps_view, route_name='wps')
        config.add_view(pywps_view, route_name='wps_secured')
        config.add_request_method(_wps_cfg, 'wps_cfg', reify=True)
        config.add_request_method(_processes, 'processes', reify=True)
