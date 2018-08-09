from . import __version__ as wps_restapi_version
from twitcher import __version__ as twitcher_version
from twitcher.adapter import adapter_factory
from cornice_swagger import CorniceSwagger
from cornice.service import get_services
from pyramid.renderers import render_to_response
from twitcher.wps_restapi import swagger_definitions as sd
from twitcher.wps_restapi.utils import wps_restapi_base_url, wps_restapi_base_path


@sd.api_versions_service.get(tags=[sd.api_tag], renderer='json',
                             schema=sd.VersionsEndpoint(), response_schemas=sd.get_api_versions_responses)
def api_versions(request):
    """Twitcher versions information."""
    adapter_info = adapter_factory(request.registry.settings).describe_adapter()
    return {'versions': {'wps_restapi': wps_restapi_version, 'twitcher': twitcher_version, 'adapter': adapter_info}}


@sd.api_swagger_json_service.get(tags=[sd.api_tag], renderer='json',
                                 schema=sd.SwaggerJsonEndpoint(), response_schemas=sd.get_api_swagger_json_responses)
def api_swagger_json(request, use_docstring_summary=True):
    """Twitcher REST API schema generation in JSON format."""

    cornice = CorniceSwagger(get_services())
    # function docstrings are used to create the route's summary in Swagger-UI
    cornice.summary_docstrings = use_docstring_summary
    return cornice.generate(title=sd.API_TITLE, version=wps_restapi_version,
                            base_path=wps_restapi_base_url(request.registry.settings))


@sd.api_swagger_ui_service.get(tags=[sd.api_tag], response_schemas=sd.get_api_swagger_ui_responses)
def api_swagger_ui(request):
    """Twitcher REST API swagger-ui schema documentation (this page)."""
    json_path = wps_restapi_base_path(request.registry.settings) + sd.api_swagger_json_uri
    data_mako = {'api_title': sd.API_TITLE, 'api_swagger_json_path': json_path}
    return render_to_response('templates/swagger_ui.mako', data_mako, request=request)
