# code based on https://github.com/elemoine/papyrus_ogcproxy

from urlparse import urlparse
from httplib2 import Http

from pyramid.view import view_config
from pyramid.httpexceptions import (HTTPForbidden, HTTPBadRequest,
                                    HTTPBadGateway, HTTPNotAcceptable)
from pyramid.response import Response

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
    # list allowed hosts here (no port limiting)
    'localhost',
    )

@view_config(route_name='ogcproxy')
def ogcproxy(request):
    url = request.params.get("url")
    if url is None:
        return HTTPBadRequest()

    logger.debug("url = %s", url)

    # check for full url
    parsed_url = urlparse(url)
    if not parsed_url.netloc or parsed_url.scheme not in ("http", "https"):
        return HTTPBadRequest()

    # forward request to target (without Host Header)
    http = Http(disable_ssl_certificate_validation=True)
    logger.debug("headers = %s", dict(request.headers))
    logger.debug("method = %s", request.method)
    logger.debug("body = %s", request.body)
    h = dict(request.headers)
    h.pop("Host", h)
    try:
        resp, content = http.request(url, method=request.method, body=request.body, headers=h)
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
