from owslib.wps import ComplexData
from twitcher.utils import parse_request_query, get_twitcher_url
from distutils.version import LooseVersion
from pyramid.httpexceptions import HTTPError, HTTPInternalServerError


def wps_restapi_base_path(settings):
    restapi_path = settings.get('twitcher.wps_restapi_path', '').rstrip('/').strip()
    return restapi_path


def wps_restapi_base_url(settings):
    twitcher_url = get_twitcher_url(settings)
    restapi_path = wps_restapi_base_path(settings)
    return twitcher_url + restapi_path


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
