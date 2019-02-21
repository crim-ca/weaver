from six.moves.urllib.parse import urlparse
from cornice_swagger import CorniceSwagger
from cornice.service import get_services
from pyramid.renderers import render_to_response
from pyramid.request import Request
from pyramid.settings import asbool
from pyramid.authentication import IAuthenticationPolicy, Authenticated
from pyramid.exceptions import PredicateMismatch
from pyramid.httpexceptions import (
    HTTPUnauthorized,
    HTTPForbidden,
    HTTPNotFound,
    HTTPMethodNotAllowed,
    HTTPInternalServerError,
    HTTPServerError,
)
from weaver.__meta__ import __version__ as weaver_version
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.colander_one_of import CustomTypeConversionDispatcher
from weaver.wps_restapi.utils import wps_restapi_base_url, wps_restapi_base_path
from simplejson import JSONDecodeError
import logging
import six
import os
LOGGER = logging.getLogger(__name__)


@sd.api_frontpage_service.get(tags=[sd.api_tag], renderer='json',
                              schema=sd.FrontpageEndpoint(), response_schemas=sd.get_api_frontpage_responses)
def api_frontpage(request):
    """Frontpage of weaver."""

    # import here to avoid circular import errors
    from weaver.config import get_weaver_configuration
    from weaver.utils import get_weaver_url
    from weaver.wps import get_wps_path

    settings = request.registry.settings
    weaver_url = get_weaver_url(settings)
    weaver_config = get_weaver_configuration(settings)

    weaver_api = asbool(settings.get('weaver.wps_restapi'))
    weaver_api_url = wps_restapi_base_url(settings) if weaver_api else None
    weaver_api_doc = weaver_api_url + sd.api_swagger_ui_uri if weaver_api else None
    weaver_api_ref = settings.get('weaver.wps_restapi_ref', None) if weaver_api else None
    weaver_wps = asbool(settings.get('weaver.wps'))
    weaver_wps_url = weaver_url + get_wps_path(settings) if weaver_wps else None

    return {
        'message': 'weaver Information',
        'configuration': weaver_config,
        'parameters': [
            {'name': 'api', 'enabled': weaver_api,
             'url': weaver_api_url,
             'doc': weaver_api_doc,
             'ref': weaver_api_ref},
            {'name': 'wps', 'enabled': weaver_wps,
             'url': weaver_wps_url},
        ]
    }


@sd.api_versions_service.get(tags=[sd.api_tag], renderer='json',
                             schema=sd.VersionsEndpoint(), response_schemas=sd.get_api_versions_responses)
def api_versions(request):
    """weaver versions information."""
    from weaver.adapter import adapter_factory
    adapter_info = adapter_factory(request.registry.settings).describe_adapter()
    adapter_info['type'] = 'adapter'
    weaver_info = {'name': 'weaver', 'version': weaver_version, 'type': 'api'}
    return {'versions': [weaver_info, adapter_info]}


@sd.api_swagger_json_service.get(tags=[sd.api_tag], renderer='json',
                                 schema=sd.SwaggerJSONEndpoint(), response_schemas=sd.get_api_swagger_json_responses)
def api_swagger_json(request, use_docstring_summary=True):
    # type: (Request, bool) -> dict
    """weaver REST API schema generation in JSON format."""
    CorniceSwagger.type_converter = CustomTypeConversionDispatcher
    swagger = CorniceSwagger(get_services())
    # function docstrings are used to create the route's summary in Swagger-UI
    swagger.summary_docstrings = use_docstring_summary
    swagger_base_spec = {'schemes': [request.scheme]}

    # obtain 'server' host and api-base-path, which doesn't correspond necessarily to the app's host and path
    # ex: 'server' adds '/weaver' with proxy redirect before API routes
    weaver_server_url = os.getenv('WEAVER_URL')
    LOGGER.debug("Request URL:  {}".format(request.url))
    LOGGER.debug("WEAVER_URL: {}".format(weaver_server_url))
    if weaver_server_url:
        weaver_parsed_url = urlparse(weaver_server_url)
        swagger_base_spec['host'] = weaver_parsed_url.netloc
        swagger_base_path = weaver_parsed_url.path
    else:
        swagger_base_spec['host'] = request.host
        swagger_base_path = sd.api_frontpage_uri
    swagger.swagger = swagger_base_spec
    return swagger.generate(title=sd.API_TITLE, version=weaver_version, base_path=swagger_base_path)


@sd.api_swagger_ui_service.get(tags=[sd.api_tag],
                               schema=sd.SwaggerUIEndpoint(), response_schemas=sd.get_api_swagger_ui_responses)
def api_swagger_ui(request):
    """weaver REST API swagger-ui schema documentation (this page)."""
    json_path = wps_restapi_base_path(request.registry.settings) + sd.api_swagger_json_uri
    json_path = json_path.lstrip('/')   # if path starts by '/', swagger-ui doesn't find it on remote
    data_mako = {'api_title': sd.API_TITLE, 'api_swagger_json_path': json_path}
    return render_to_response('templates/swagger_ui.mako', data_mako, request=request)


def not_found_or_method_not_allowed(request):
    """
    Overrides the default is HTTPNotFound [404] by appropriate HTTPMethodNotAllowed [405] when applicable.

    Not found response can correspond to underlying process operation not finding a required item, or a completely
    unknown route (path did not match any existing API definition).
    Method not allowed is more specific to the case where the path matches an existing API route, but the specific
    request method (GET, POST, etc.) is not allowed on this path.

    Without this fix, both situations return [404] regardless.
    """
    # noinspection PyProtectedMember
    if isinstance(request.exception, PredicateMismatch) and request.method not in request.exception._safe_methods:
        http_err = HTTPMethodNotAllowed
        http_msg = "Method not allowed on this resource."
    else:
        http_err = HTTPNotFound
        http_msg = str(request.exception)
    return http_err(json=get_request_info(request, http_msg))


def internal_server_error(request):
    """
    Adds additional details about the cause of the internal server error.
    """
    return HTTPInternalServerError(json=get_request_info(request))


def unauthorized_or_forbidden(request):
    """
    Overrides the default is HTTPForbidden [403] by appropriate HTTPUnauthorized [401] when applicable.

    Unauthorized response is for restricted user access according to credentials and/or authorization headers.
    Forbidden response is for operation refused by the underlying process operations.

    Without this fix, both situations return [403] regardless.

    .. seealso::
        http://www.restapitutorial.com/httpstatuscodes.html
    """
    authn_policy = request.registry.queryUtility(IAuthenticationPolicy)
    principals = authn_policy.effective_principals(request)
    if Authenticated not in principals:
        http_err = HTTPUnauthorized
        http_msg = "Unauthorized access to this resource."
    else:
        http_err = HTTPForbidden
        http_msg = "Forbidden operation under this resource."
    return http_err(json=get_request_info(request, http_msg))


def get_request_info(request, message=None):
    content = {u'route_name': str(request.upath_info), u'request_url': str(request.url), u'method': request.method}
    if isinstance(message, six.string_types):
        content.update({'detail': message})
    if hasattr(request, 'exception'):
        # handle error raised simply by checking for 'json' property in python 3 when body is invalid
        has_json = False
        try:
            has_json = hasattr(request.exception, 'json')
        except JSONDecodeError:
            pass
        if has_json and isinstance(request.exception.json, dict):
            content.update(request.exception.json)
        elif isinstance(request.exception, HTTPServerError) and hasattr(request.exception, 'message'):
            content.update({u'exception': str(request.exception.message)})
    elif hasattr(request, 'matchdict'):
        if request.matchdict is not None and request.matchdict != '':
            content.update(request.matchdict)
    return content
