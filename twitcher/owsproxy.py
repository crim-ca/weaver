"""
The owsproxy is based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_

See also: https://github.com/nive/outpost/blob/master/outpost/proxy.py
"""

import urllib
import requests

from pyramid.response import Response
from pyramid.settings import asbool

from twitcher._compat import urlparse

from twitcher.owsexceptions import OWSAccessForbidden, OWSAccessFailed
from twitcher.utils import replace_caps_url
from twitcher.store import servicestore_factory


import logging
LOGGER = logging.getLogger(__name__)


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

# TODO: configure allowed hosts
allowed_hosts = (
    # list allowed hosts here (no port limiting)
    # "localhost",
)


def _send_request(request, service, extra_path=None, request_params=None):

    # TODO: fix way to build url
    url = service['url']
    if extra_path:
        url += '/' + extra_path
    if service.get('c4i', False):
        if 'C4I-Access-Token' in request.headers:
            LOGGER.debug('using c4i token')
            url += '/' + request.headers['C4I-Access-Token']
    if request_params:
        url += '?' + request_params
    LOGGER.debug('url = %s', url)

    # forward request to target (without Host Header)
    h = dict(request.headers)
    h.pop("Host", h)
    try:
        resp = requests.request(method=request.method.upper(), url=url, data=request.body, headers=h)
    except Exception, e:
        return OWSAccessFailed("Request failed: {}".format(e.message))

    if resp.ok is False:
        if 'ExceptionReport' in resp.content:
            pass
        else:
            return OWSAccessFailed("Response is not ok: {}".format(resp.reason))

    # check for allowed content types
    ct = None
    # LOGGER.debug("headers=", resp.headers)
    if "Content-Type" in resp.headers:
        ct = resp.headers["Content-Type"]
        if not ct.split(";")[0] in allowed_content_types:
            msg = "Content type is not allowed: {}.".format(ct)
            LOGGER.error(msg)
            return OWSAccessForbidden(msg)
    else:
        # return OWSAccessFailed("Could not get content type from response.")
        LOGGER.warn("Could not get content type from response")

    try:
        if ct in ['text/xml', 'application/xml', 'text/xml;charset=ISO-8859-1']:
                # replace urls in xml content
                proxy_url = request.route_url('owsproxy', service_name=service['name'])
                # TODO: where do i need to replace urls?
                content = replace_caps_url(resp.content, proxy_url, service.get('url'))
        else:
            # raw content
            content = resp.content
    except Exception:
        return OWSAccessFailed("Could not decode content.")

    headers = {}
    if ct:
        headers["Content-Type"] = ct
    return Response(content, status=resp.status_code, headers=headers)


def owsproxy_url(request):
    url = request.params.get("url")
    if url is None:
        return OWSAccessFailed("URL param is missing.")

    # check for full url
    parsed_url = urlparse(url)
    if not parsed_url.netloc or parsed_url.scheme not in ("http", "https"):
        return OWSAccessFailed("Not a valid URL.")
    return _send_request(request, service=dict(url=url, name='external'))


def owsproxy(request):
    """
    TODO: use ows exceptions
    """
    try:
        service_name = request.matchdict.get('service_name')
        extra_path = request.matchdict.get('extra_path')
        store = servicestore_factory(request.registry)
        service = store.fetch_by_name(service_name)
    except Exception as err:
        return OWSAccessFailed("Could not find service: {}.".format(err.message))
    else:
        return _send_request(request, service, extra_path, request_params=urllib.urlencode(request.params))


def owsproxy_delegate(request):
    """
    Delegates owsproxy request to external twitcher service.
    """
    twitcher_url = request.registry.settings.get('twitcher.url')
    url = twitcher_url + '/ows/proxy'
    if request.matchdict.get('service_name'):
        url += '/' + request.matchdict.get('service_name')
        if request.matchdict.get('access_token'):
            url += '/' + request.matchdict.get('service_name')
    url += '?' + urllib.urlencode(request.params)
    LOGGER.debug("delegate to owsproxy: %s", url)
    # forward request to target (without Host Header)
    # h = dict(request.headers)
    # h.pop("Host", h)
    resp = requests.request(method=request.method.upper(), url=url, data=request.body,
                            headers=request.headers, verify=False)
    return Response(resp.content, status=resp.status_code, headers=resp.headers)


def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.ows_proxy', True)):
        LOGGER.debug('Twitcher /ows/proxy enabled.')

        config.add_route('owsproxy', '/ows/proxy/{service_name}')
        # TODO: maybe configure extra path
        # config.add_route('owsproxy_extra', '/ows/proxy/{service_name}/{extra_path:.*}')
        config.add_route('owsproxy_secured', '/ows/proxy/{service_name}/{access_token}')

        # use delegation mode?
        if asbool(settings.get('twitcher.ows_proxy_delegate', False)):
            LOGGER.debug('Twitcher /ows/proxy delegation mode enabled.')
            config.add_view(owsproxy_delegate, route_name='owsproxy')
            config.add_view(owsproxy_delegate, route_name='owsproxy_secured')
        else:
            # include twitcher config
            config.include('twitcher.config')
            # include mongodb
            config.include('twitcher.db')
            config.add_view(owsproxy, route_name='owsproxy')
            config.add_view(owsproxy, route_name='owsproxy_secured')
        # use /owsproxy?
        if asbool(settings.get('twitcher.ows_proxy_url', True)):
            LOGGER.debug('Twitcher /owsproxy enabled.')
            config.add_route('owsproxy_url', '/owsproxy')
            config.add_view(owsproxy_url, route_name='owsproxy_url')
