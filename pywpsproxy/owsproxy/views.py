import urllib
from urlparse import urlparse
from httplib2 import Http

from pyramid.view import view_config
from pyramid.httpexceptions import (HTTPForbidden, HTTPBadRequest,
                                    HTTPBadGateway, HTTPNotAcceptable)
from pyramid.response import Response

from pywpsproxy import models

import logging
logger = logging.getLogger(__name__)


allowed_content_types = (
    "application/xml", "text/xml",
    "application/vnd.ogc.se_xml",           # OGC Service Exception
    "application/vnd.ogc.se+xml",           # OGC Service Exception
    "application/vnd.ogc.success+xml",      # OGC Success (SLD Put)
    "application/vnd.ogc.wms_xml",          # WMS Capabilities
    "application/vnd.ogc.context+xml",      # WMC
    "application/vnd.ogc.gml",              # GML
    "application/vnd.ogc.sld+xml",          # SLD
    "application/vnd.google-earth.kml+xml", # KML
    )

allowed_hosts = (
    "localhost",
    )

ows_registry = {
    'emu': 'http://localhost:8094/wps'
    }

class OWSProxy(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

    @view_config(route_name='owsproxy')
    def owsproxy(self):
        ows_service = self.request.matchdict.get('ows_service')
        logger.debug("ows_service = %s", ows_service)
        if ows_service is None:
            return HTTPBadRequest()
        
        if not ows_service in ows_registry:
            return HTTPBadRequest()

        token = self.request.matchdict.get('token')
        logger.debug("token = %s", token)
        if not models.is_token_valid(self.request, token):
            return HTTPBadRequest()

        url = ows_registry.get(ows_service)
        logger.debug('url %s', url)
        if url is None:
            return HTTPBadRequest()

        # check for full url
        parsed_url = urlparse(url)
        if not parsed_url.netloc or parsed_url.scheme not in ("http", "https"):
            return HTTPBadRequest()

        # TODO: fix way to build url
        logger.debug('params = %s', self.request.params)
        url = url + '?' + urllib.urlencode(self.request.params)

        logger.debug('url %s', url)

        # forward request to target (without Host Header)
        http = Http(disable_ssl_certificate_validation=True)
        logger.debug("headers = %s", dict(self.request.headers))
        logger.debug("method = %s", self.request.method)
        logger.debug("body = %s", self.request.body)
        h = dict(self.request.headers)
        h.pop("Host", h)
        try:
            resp, content = http.request(url, method=self.request.method, body=self.request.body, headers=h)
            logger.debug("content = %s", content)
        except:
            return HTTPBadGateway()

        # check for allowed content types
        if resp.has_key("content-type"):
            ct = resp["content-type"]
            if not ct.split(";")[0] in allowed_content_types:
                # allow any content type from allowed hosts (any port)
                if not parsed_url.netloc in allowed_hosts:
                    return HTTPForbidden()
        else:
            return HTTPNotAcceptable()

        response = Response(content, status=resp.status,
                            headers={"Content-Type": ct})

        return response
