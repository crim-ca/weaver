from owslib.wps import ComplexData


def restapi_base_url(request):
    twitcher_url = request.registry.settings.get('twitcher.url').rstrip('/')
    restapi_path = request.registry.settings.get('twitcher.restapi_path', '').rstrip('/')
    return twitcher_url + restapi_path


def get_cookie_headers(headers):
    try:
        return dict(Cookie=headers['Cookie'])
    except KeyError: #No cookie
        return {}


def jsonify(value):
    # ComplexData type
    if isinstance(value, ComplexData):
        return {'mimeType': value.mimeType, 'encoding': value.encoding, 'schema': value.schema}
    # other type
    else:
        return value
