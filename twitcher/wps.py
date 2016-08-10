"""
pywps wrapper
"""
import os

from pyramid.httpexceptions import HTTPBadRequest
from pyramid.settings import asbool, aslist

import pywps
from pywps.Exceptions import WPSException
from twitcher.owsexceptions import OWSNoApplicableCode

import logging
logger = logging.getLogger(__name__)

DEFAULT_KEYS = ['PYWPS_CFG', 'PYWPS_PROCESSES', 'PYWPS_TEMPLATES']


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

    
def pywps_view(request):
    """
    * TODO: add xml response renderer
    * TODO: fix exceptions ... use OWSException (raise ...)
    """
    response = request.response
    response.status = "200 OK"
    response.content_type = "text/xml"

    inputQuery = None
    os.environ["REQUEST_METHOD"] = request.method
    if request.method == "GET":
        inputQuery = request.query_string
    elif request.method == "POST":
        inputQuery = request.body_file_raw
    else:
        return HTTPBadRequest()

    if not inputQuery:
        return OWSNoApplicableCode("No query string found.")

    if request.wps_cfg:
        os.environ['PYWPS_CFG'] = request.wps_cfg

    # set the environ for wps from request environ
    for key in request.wps_environ_keys:
        if key in request.environ:
            os.environ[key] = request.environ[key]

    # create the WPS object
    try:
        wps = pywps.Pywps(os.environ["REQUEST_METHOD"], os.environ.get("PYWPS_CFG"))
        if wps.parseRequest(inputQuery):
            pywps.debug(wps.inputs)
            wps.performRequest(processes=os.environ.get("PYWPS_PROCESSES"))
            response_headers = [('Content-type', wps.request.contentType)]
            return wps.response
    except WPSException,e:
        return str(e)
    except Exception, e:
        return OWSNoApplicableCode(e.message)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.wps', True)):
        # logger.debug('Add twitcher wps application')

        config.add_route('wps', '/ows/wps')
        config.add_route('wps_secured', '/ows/wps/{access_token}')
        config.add_view(pywps_view, route_name='wps', renderer='string')
        config.add_view(pywps_view, route_name='wps_secured', renderer='string')
        config.add_request_method(_wps_environ_keys, 'wps_environ_keys', reify=True)
        config.add_request_method(_wps_cfg, 'wps_cfg', reify=True)



