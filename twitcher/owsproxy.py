"""
The owsproxy is based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_
"""

import urllib
from httplib2 import Http

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest, HTTPBadGateway, HTTPNotAcceptable
from pyramid.response import Response
from pyramid.settings import asbool

from twitcher.registry import registry_factory

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
    http = Http(disable_ssl_certificate_validation=True)
    h = dict(request.headers)
    h.pop("Host", h)
    try:
        resp, content = http.request(url, method=request.method, body=request.body, headers=h)
    except:
        return HTTPBadGateway()

    # check for allowed content types
    if resp.has_key("content-type"):
        ct = resp["content-type"]
        if not ct.split(";")[0] in allowed_content_types:
            return HTTPForbidden()
    else:
        return HTTPNotAcceptable()

    # replace urls in xml content
    if 'xml' in ct:
        content = content.replace(service['url'], service['proxy_url'])

    return Response(content, status=resp.status, headers={"Content-Type": ct})

def owsproxy_view(request):
    """
    TODO: use ows exceptions
    """
    service_name = request.matchdict.get('service_name')
    if service_name is None:
        return HTTPBadRequest('Parameter service_name is required.')

    service = None
    try:
        registry = registry_factory(request)
        service = registry.get_service(service_name)
    except Exception as err:
        return HTTPBadRequest("Could not find service: %s." % (err.message))

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
