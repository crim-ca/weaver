from owslib.wps import ComplexData
from weaver.utils import parse_request_query, get_weaver_url
from distutils.version import LooseVersion
from pyramid.httpexceptions import HTTPSuccessful, HTTPError, HTTPInternalServerError
from lxml import etree
import requests

import logging
LOGGER = logging.getLogger("weaver")

VERSION_100 = '1.0.0'
VERSION_200 = '2.0.0'
CONTENT_TYPE_XML = 'application/xml'
CONTENT_TYPE_JSON = 'application/json'
OUTPUT_FORMAT_JSON = 'json'
OUTPUT_FORMAT_XML = 'xml'
OUTPUT_FORMATS = {
    VERSION_100: OUTPUT_FORMAT_XML,
    VERSION_200: OUTPUT_FORMAT_JSON,
    CONTENT_TYPE_XML: OUTPUT_FORMAT_XML,
    CONTENT_TYPE_JSON: OUTPUT_FORMAT_JSON,
}


def wps_restapi_base_path(settings):
    restapi_path = settings.get('weaver.wps_restapi_path', '').rstrip('/').strip()
    return restapi_path


def wps_restapi_base_url(settings):
    weaver_url = get_weaver_url(settings)
    restapi_path = wps_restapi_base_path(settings)
    return weaver_url + restapi_path


def get_cookie_headers(headers):
    try:
        return dict(Cookie=headers['Cookie'])
    except KeyError:  # No cookie
        return {}


def jsonify(value):
    # ComplexData type
    if isinstance(value, ComplexData):
        return {'mimeType': value.mimeType, 'encoding': value.encoding, 'schema': value.schema}
    # other type
    else:
        return value


def get_wps_output_format(request, service_url=None):
    """
    Get the preferred output format from WPS after checking various hints:
        - 'version' in query string
        - Content-Type in accept headers
        - GetCapabilities of the service

    :param request: request for which a response of WPS version-specific format must be generated.
    :param service_url: endpoint URL of the service to request 'GetCapabilities' if version not found by previous hints.
    :return: one of OUTPUT_FORMAT (default: 1.0.0 => 'xml' if no direct hint matched)
    """
    # return specific type if requested by 'version' query
    queries = parse_request_query(request)
    if 'version' in queries and len(queries['version']) > 0:
        out_version = min([LooseVersion(v) for v in queries['version']])
        out_format = OUTPUT_FORMATS.pop(out_version.version, None)
        return out_format or OUTPUT_FORMATS[VERSION_100]

    # version not specified as query, check accept headers for specific and unique case
    accepts = [accept[0] for accept in request.accept.parsed]
    matched_accepts = list(set(OUTPUT_FORMATS) & set(accepts))
    if len(matched_accepts) == 1:
        return OUTPUT_FORMATS[matched_accepts[0]]

    # version still ambiguous, verify service's GetCapabilities
    if service_url:
        getcap_url_100 = '{}?service=WPS&request=GetCapabilities'
        getcap_url_200 = '{}/processes'.format(service_url)
        getcap_resp_100 = requests.get(getcap_url_100)
        getcap_resp_200 = requests.get(getcap_url_200)

        # analyse JSON response
        if isinstance(getcap_resp_200, HTTPSuccessful):
            try:
                # TODO: update get version if it is ever added to 'GetCapabilities' from WPS REST response
                # for now, suppose that a valid list in json body means that the service is WPS 2.0.0
                if isinstance(getcap_resp_200.json()['processes'], list):
                    return OUTPUT_FORMATS[VERSION_200]
            except Exception as ex:
                LOGGER.error('Got exception in `get_wps_output_format` JSON parsing: {}'.format(repr(ex)))

        # analyse XML response
        if isinstance(getcap_resp_100, HTTPSuccessful):
            try:
                # TODO XML implementation
                etree.fromstring(getcap_resp_100.content)
                return OUTPUT_FORMATS[VERSION_100]
            except Exception as ex:
                LOGGER.error('Got exception in `get_wps_output_format` XML parsing: {}'.format(repr(ex)))

    # still not found, default to older version
    # for most probable format supported by services
    return OUTPUT_FORMATS[VERSION_100]
