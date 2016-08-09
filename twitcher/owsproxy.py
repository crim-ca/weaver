"""
The owsproxy is based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_
"""

import urllib
import requests

from pyramid.httpexceptions import HTTPBadRequest, HTTPBadGateway, HTTPNotAcceptable
from twitcher.owsexceptions import OWSAccessForbidden
from pyramid.response import Response
from pyramid.settings import asbool

from twitcher.registry import service_registry_factory, proxy_url

import logging
logger = logging.getLogger(__name__)


allowed_content_types = (
    "application/xml",                       # XML
    "text/xml",
    "text/xml;charset=ISO-8859-1"
    "application/vnd.ogc.se_xml",            # OGC Service Exception
    "application/vnd.ogc.se+xml",            # OGC Service Exception
    # "application/vnd.ogc.success+xml",      # OGC Success (SLD Put)
    "application/vnd.ogc.wms_xml",           # WMS Capabilities
    # "application/vnd.ogc.gml",              # GML
    # "application/vnd.ogc.sld+xml",          # SLD
    "application/vnd.google-earth.kml+xml",  # KML
    "application/vnd.google-earth.kmz",
    "image/png",                             # PNG
    "image/png;mode=32bit",
    "image/gif",                             # GIF
    "image/jpeg",                            # JPEG
    "application/json",                      # JSON
    "application/json;charset=ISO-8859-1",    
    )

          
def _send_request(request, service, extra_path=None):
    
    # TODO: fix way to build url
    url = service['url']
    if extra_path:
        url += '/' + extra_path
    url += '?' + urllib.urlencode(request.params)
    # logger.debug('url = %s', url)
    
    # forward request to target (without Host Header)
    h = dict(request.headers)
    h.pop("Host", h)
    try:
        resp = requests.request(method=request.method.upper(), url=url, data=request.body, headers=h)
    except Exception, e:
        return HTTPBadGateway("Request failed: %s" % (e.message))

    if resp.ok is False:
        return HTTPBadGateway("Response is not ok: %s" % (resp.reason))

    # check for allowed content types
    ct = None
    # logger.debug("headers=", resp.headers)
    if "Content-Type" in resp.headers:
        ct = resp.headers["Content-Type"]
        if not ct.split(";")[0] in allowed_content_types:
            msg = "Content type is not allowed: %s." % (ct)
            logger.error(msg)
            return OWSAccessForbidden(msg)
    else:
        # return HTTPNotAcceptable("Could not get content type from response.")
        logger.warn("Could not get content type from response")

    try:
        if ct in ['text/xml', 'application/xml', 'text/xml;charset=ISO-8859-1']:
                # replace urls in xml content
                content = resp.content.decode('utf-8', 'ignore')
                content = content.replace(service['url'], proxy_url(request, service['name']))
                # TODO: remove default namespace in ncwms2 getcaps
                # content = content.replace('xmlns="http://www.opengis.net/wms"', '')
        else:
            # raw content
            content = resp.content
    except:
        return HTTPNotAcceptable("Could not decode content.")

    headers = {}
    if ct:
        headers["Content-Type"] = ct
    return Response(content, status=resp.status_code, headers=headers)


def owsproxy_view(request):
    """
    TODO: use ows exceptions
    """
    try:
        service_name = request.matchdict.get('service_name')
        extra_path = request.matchdict.get('extra_path')
        registry = service_registry_factory(request.registry)
        service = registry.get_service(service_name)
    except Exception as err:
        return HTTPBadRequest("Could not find service: %s." % (err.message))
    else:
        return _send_request(request, service, extra_path)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.ows_proxy', True)):
        logger.info('Add OWS proxy')
        
        # include mongodb
        config.include('twitcher.db')

        config.add_route('owsproxy', '/ows/proxy/{service_name}')
        # TODO: maybe configure extra path
        # config.add_route('owsproxy_extra', '/ows/proxy/{service_name}/{extra_path:.*}')
        config.add_route('owsproxy_secured', '/ows/proxy/{service_name}/{access_token}')
        config.add_view(owsproxy_view, route_name='owsproxy')
        # config.add_view(owsproxy_view, route_name='owsproxy_extra')
        config.add_view(owsproxy_view, route_name='owsproxy_secured')
