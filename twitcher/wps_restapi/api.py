from six.moves.urllib.parse import urlparse
from cornice_swagger import CorniceSwagger
from cornice.service import get_services
from pyramid.renderers import render_to_response
from pyramid.request import Request
from pyramid.settings import asbool
from twitcher.__meta__ import __version__ as twitcher_version
from twitcher.config import get_twitcher_configuration
from twitcher.utils import get_twitcher_url
from twitcher.wps import get_wps_path
from twitcher.owsproxy import owsproxy_base_path
from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.colander_one_of import CustomTypeConversionDispatcher
from twitcher.wps_restapi.utils import wps_restapi_base_url, wps_restapi_base_path
import logging
import os
LOGGER = logging.getLogger(__name__)


@sd.api_frontpage_service.get(tags=[sd.api_tag], renderer='json',
                              schema=sd.FrontpageEndpoint(), response_schemas=sd.get_api_frontpage_responses)
def api_frontpage(request):
    """Frontpage of Twitcher."""
    settings = request.registry.settings
    twitcher_url = get_twitcher_url(settings)
    twitcher_config = get_twitcher_configuration(settings)

    twitcher_api = asbool(settings.get('twitcher.wps_restapi'))
    twitcher_api_url = wps_restapi_base_url(settings) if twitcher_api else None
    twitcher_api_doc = twitcher_api_url + sd.api_swagger_ui_uri if twitcher_api else None
    twitcher_api_ref = settings.get('twitcher.wps_restapi_ref', None) if twitcher_api else None
    twitcher_wps = asbool(settings.get('twitcher.wps'))
    twitcher_wps_url = twitcher_url + get_wps_path(settings) if twitcher_wps else None
    twitcher_proxy = asbool(settings.get('twitcher.ows_proxy'))
    twitcher_proxy_url = twitcher_url + owsproxy_base_path(settings) if twitcher_proxy else None

    return {
        'message': 'Twitcher Information',
        'configuration': twitcher_config,
        'parameters': [
            {'name': 'api', 'enabled': twitcher_api,
             'url': twitcher_api_url,
             'doc': twitcher_api_doc,
             'ref': twitcher_api_ref},
            {'name': 'proxy', 'enabled': twitcher_proxy,
             'url': twitcher_proxy_url},
            {'name': 'wps', 'enabled': twitcher_wps,
             'url': twitcher_wps_url},
        ]
    }


@sd.api_versions_service.get(tags=[sd.api_tag], renderer='json',
                             schema=sd.VersionsEndpoint(), response_schemas=sd.get_api_versions_responses)
def api_versions(request):
    """Twitcher versions information."""
    from twitcher.adapter import adapter_factory
    adapter_info = adapter_factory(request.registry.settings).describe_adapter()
    adapter_info['type'] = 'adapter'
    twitcher_info = {'name': 'Twitcher', 'version': twitcher_version, 'type': 'api'}
    return {'versions': [twitcher_info, adapter_info]}


@sd.api_swagger_json_service.get(tags=[sd.api_tag], renderer='json',
                                 schema=sd.SwaggerJSONEndpoint(), response_schemas=sd.get_api_swagger_json_responses)
def api_swagger_json(request, use_docstring_summary=True):
    # type: (Request, bool) -> dict
    """Twitcher REST API schema generation in JSON format."""
    CorniceSwagger.type_converter = CustomTypeConversionDispatcher
    swagger = CorniceSwagger(get_services())
    # function docstrings are used to create the route's summary in Swagger-UI
    swagger.summary_docstrings = use_docstring_summary
    swagger_base_spec = {'schemes': [request.scheme]}

    # obtain 'server' host and api-base-path, which doesn't correspond necessarily to the app's host and path
    # ex: 'server' adds '/twitcher' with proxy redirect before API routes
    twitcher_server_url = os.getenv('TWITCHER_URL')
    LOGGER.debug("Request URL:  {}".format(request.url))
    LOGGER.debug("TWITCHER_URL: {}".format(twitcher_server_url))
    if twitcher_server_url:
        swagger_base_spec['host'] = twitcher_server_url
        swagger_base_path = twitcher_server_url
    else:
        swagger_base_spec['host'] = request.host
        swagger_base_path = sd.api_frontpage_uri
    swagger.swagger = swagger_base_spec
    return swagger.generate(title=sd.API_TITLE, version=twitcher_version, base_path=swagger_base_path)


@sd.api_swagger_ui_service.get(tags=[sd.api_tag],
                               schema=sd.SwaggerUIEndpoint(), response_schemas=sd.get_api_swagger_ui_responses)
def api_swagger_ui(request):
    """Twitcher REST API swagger-ui schema documentation (this page)."""
    json_path = wps_restapi_base_path(request.registry.settings) + sd.api_swagger_json_uri
    json_path = json_path.lstrip('/')   # if path starts by '/', swagger-ui doesn't find it on remote
    data_mako = {'api_title': sd.API_TITLE, 'api_swagger_json_path': json_path}
    return render_to_response('templates/swagger_ui.mako', data_mako, request=request)
