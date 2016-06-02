"""
The owsproxy is based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_
"""

import urllib
import requests

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest, HTTPBadGateway, HTTPNotAcceptable, HTTPForbidden
from twitcher.owsexceptions import OWSNoApplicableCode, OWSAccessForbidden
from pyramid.response import Response
from pyramid.settings import asbool

from twitcher.registry import service_registry_factory, proxy_url

import logging
logger = logging.getLogger(__name__)


allowed_content_types = (
    "application/xml", "text/xml",
    "application/vnd.ogc.se_xml",           # OGC Service Exception
    "application/vnd.ogc.se+xml",           # OGC Service Exception
    #"application/vnd.ogc.success+xml",      # OGC Success (SLD Put)
    #"application/vnd.ogc.wms_xml",          # WMS Capabilities
    #"application/vnd.ogc.gml",              # GML
    #"application/vnd.ogc.sld+xml",          # SLD
    #"application/vnd.google-earth.kml+xml", # KML
    )

          
def _send_request(request, service):
    # TODO: fix way to build url
    logger.debug('params = %s', request.params)
    url = service['url'] + '?' + urllib.urlencode(request.params)

    # forward request to target (without Host Header)
    h = dict(request.headers)
    h.pop("Host", h)
    resp = None
    try:
        resp = requests.request(method=request.method.upper(), url=url, data=request.body, headers=h)
    except Exception, e:
        return HTTPBadGateway(e.message)

    if resp.ok == False:
        return HTTPBadGateway(resp.reason)

    # check for allowed content types
    ct = None
    if "Content-Type" in resp.headers:
        ct = resp.headers["Content-Type"]
        if not ct.split(";")[0] in allowed_content_types:
            return OWSAccessForbidden()
    else:
        return HTTPNotAcceptable()

    content = None
    try:
        content = resp.content.decode('utf-8', 'ignore')
        # replace urls in xml content
        if ct in ['text/xml', 'application/xml']:
            content = content.replace(service['url'], proxy_url(request, service['name']))
    except:
        return HTTPNotAcceptable("Could not decode content.")

    return Response(content, status=resp.status_code, headers={"Content-Type": ct})

def owsproxy_view(request):
    """
    TODO: use ows exceptions
    """
    service_name = request.matchdict.get('service_name')
    if service_name is None:
        return HTTPBadRequest('Parameter service_name is required.')

    try:
        registry = service_registry_factory(request.registry)
        service = registry.get_service(service_name)
    except Exception as err:
        return HTTPBadRequest("Could not find service: %s." % (err.message))
    else:
        return _send_request(request, service)

def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.ows_proxy', True)):
        logger.info('Add OWS proxy')
        
        # include mongodb
        config.include('twitcher.db')
    
        config.add_route('owsproxy', '/ows/proxy/{service_name}')
        config.add_route('owsproxy_secured', '/ows/proxy/{service_name}/{access_token}')
        config.add_view(owsproxy_view, route_name='owsproxy')
        config.add_view(owsproxy_view, route_name='owsproxy_secured')
