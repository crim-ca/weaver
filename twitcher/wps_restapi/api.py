from . import __version__
from pyramid.view import view_config
import os
from cornice_swagger import CorniceSwagger
from cornice import Service
from cornice.service import get_services
from pyramid.response import Response, FileResponse
import colander
from twitcher.wps_restapi import swagger_definitions as sd


@sd.api_swagger_json_service.get(tags=[sd.api_tag], response_schemas=sd.get_api_swagger_json_responses)
def api_schema(request, use_docstring_summary=True):
    """Twitcher REST API schema generation in JSON format."""
    cornice = CorniceSwagger(get_services())
    # function docstrings are used to create the route's summary in Swagger-UI
    cornice.summary_docstrings = use_docstring_summary
    return cornice.generate(title='Twitcher REST API', version=__version__)


@sd.api_swagger_ui_service.get(tags=[sd.api_tag], response_schemas=sd.get_api_swagger_ui_responses)
def api(request):
    """Twitcher REST API swagger-ui schema documentation (this page)."""
    here = os.path.dirname(__file__)
    template = os.path.join(here, 'templates', 'swagger_ui.html')
    return FileResponse(template, request=request)
