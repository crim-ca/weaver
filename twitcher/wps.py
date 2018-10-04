"""
pywps 4.x wrapper
"""
import os

from pyramid.response import Response
from pyramid.wsgi import wsgiapp2
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.settings import asbool, aslist
from pyramid_celery import celery_app as app
from pywps import configuration as pywps_config
from six.moves.configparser import SafeConfigParser
import six

from twitcher.owsexceptions import OWSNoApplicableCode

import logging
LOGGER = logging.getLogger(__name__)

# can be overridden with 'settings.wps-cfg'
DEFAULT_PYWPS_CFG = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'wps.cfg')
PYWPS_CFG = None


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


def _processes(request):
    from twitcher.store import processstore_defaultfactory
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
    global PYWPS_CFG

    try:
        registry = app.conf['PYRAMID_REGISTRY']

        # get config file
        if 'PYWPS_CFG' not in environ:
            environ['PYWPS_CFG'] = os.getenv('PYWPS_CFG') or get_wps_cfg_path(registry.settings)

        if PYWPS_CFG is None:
            # get PyWPS config
            pywps_config.load_configuration(environ['PYWPS_CFG'])
            PYWPS_CFG = pywps_config

            # ensure the output dir exists if specified
            out_dir_path = PYWPS_CFG.get_config_value('server', 'outputpath')
            if not os.path.isdir(out_dir_path):
                os.makedirs(out_dir_path)

        # call pywps application
        from twitcher.store import processstore_defaultfactory
        processstore = processstore_defaultfactory(registry)
        processes_wps = [process.wps() for process in processstore.list_processes()]
        service = Service(processes_wps, [environ['PYWPS_CFG']])
    except Exception as ex:
        raise OWSNoApplicableCode("Failed setup of PyWPS Service and/or Processes. Error [{}]".format(ex))

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
        config.add_request_method(_processes, 'processes', reify=True)
