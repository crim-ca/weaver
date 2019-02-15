from six.moves.urllib.parse import urlparse
from cornice_swagger import CorniceSwagger
from cornice.service import get_services
from pyramid.renderers import render_to_response
from pyramid.request import Request
from pyramid.settings import asbool
from weaver.__meta__ import __version__ as weaver_version
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.colander_one_of import CustomTypeConversionDispatcher
from weaver.wps_restapi.utils import wps_restapi_base_url, wps_restapi_base_path
import logging
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
    weaver_server_url = os.getenv('weaver_URL')
    LOGGER.debug("Request URL:  {}".format(request.url))
    LOGGER.debug("weaver_URL: {}".format(weaver_server_url))
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
