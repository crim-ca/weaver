import urllib
from httplib2 import Http

from pyramid.view import view_config
from pyramid.httpexceptions import (HTTPForbidden, HTTPBadRequest,
                                    HTTPBadGateway, HTTPNotAcceptable)
from pyramid.response import Response

from pywpsproxy import models

import logging
logger = logging.getLogger(__name__)

allowed_service_types = (
    'wps', 'wms'
    )

allowed_requests = (
    'getcapabilities', 'describeprocess',
    )

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

class OWSProxy(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session
        
    def ows_service(self):
        ows_service = None
        if 'service' in self.request.params:
            ows_service = self.request.params['service']
        elif 'SERVICE' in self.request.params:
            ows_service = self.request.params['SERVICE']

        if ows_service is not None:
            if ows_service.lower() in allowed_service_types:
                ows_service = ows_service.lower()
            else:
                ows_service = None
        logger.debug("service = %s", ows_service)
        return ows_service

    def ows_request(self):
        ows_request = None
        if 'request' in self.request.params:
            ows_request = self.request.params['request']
        elif 'REQUEST' in self.request.params:
            ows_request = self.request.params['REQUEST']
        logger.debug("request = %s", ows_request)
        return ows_request

    def allow_access(self):
        ows_service = self.ows_service()
        if ows_service is None:
            return False

        ows_request = self.ows_request()
        if ows_request is None:
            return False
        
        if ows_request.lower() in allowed_requests:
            return True
        
        try:
            tokenid = self.request.matchdict.get('tokenid')
            models.validate_token(self.request, tokenid)
        except:
            return False
        return True
    
    def send_request(self, url):
        # TODO: fix way to build url
        logger.debug('params = %s', self.request.params)
        url = url + '?' + urllib.urlencode(self.request.params)

        logger.debug('url %s', url)

        # forward request to target (without Host Header)
        http = Http(disable_ssl_certificate_validation=True)
        h = dict(self.request.headers)
        h.pop("Host", h)
        try:
            resp, content = http.request(url, method=self.request.method, body=self.request.body, headers=h)
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

        return Response(content, status=resp.status, headers={"Content-Type": ct})
    
    @view_config(route_name='owsproxy')
    @view_config(route_name='owsproxy_secured')
    def owsproxy(self):
        url = models.service_url(self.request.matchdict.get('service_id'))
        if url is None:
            return HTTPBadRequest()
        
        if not self.allow_access():
            return HTTPForbidden()

        return self.send_request(url)
