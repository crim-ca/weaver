from owslib.wps import ComplexData
from twitcher.utils import parse_request_query
from distutils.version import LooseVersion


def wps_restapi_base_path(settings):
    restapi_path = settings.get('twitcher.wps_restapi_path', '').rstrip('/').strip()
    return restapi_path


def wps_restapi_base_url(settings):
    twitcher_url = settings.get('twitcher.url').rstrip('/').strip()
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


def get_wps_output_format(request):
    """
    Get the preferred output format from WPS after checking various hints:
        - 'version' in query string
        - 'application/xml' or 'application/json' in accept headers

    :param request:
    :return: 'json' or 'xml' (default: 'json' if no direct hint matched)
    """
    # return specific type if requested by 'version'
    queries = parse_request_query(request)
    if 'version' in queries and len(queries['version']) > 0:
        max_version = max([LooseVersion(v) for v in queries['version']])
        if max_version >= LooseVersion('2.0.0'):
            return 'json'
        return 'xml'
    # version not specified as input, check accept headers
    accepts = [accept[0] for accept in request.accept.parsed]
    if 'application/xml' in accepts:
        return 'xml'
    return 'json'
