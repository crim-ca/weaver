from pyramid.view import view_config
import os
from cornice_swagger import CorniceSwagger
from cornice import Service
from cornice.service import get_services
from pyramid.response import Response, FileResponse
import colander


def api_schema(request, use_docstring_summary=True):
    cornice = CorniceSwagger(get_services())
    # function docstrings are used to create the route's summary in Swagger-UI
    cornice.summary_docstrings = use_docstring_summary
    return cornice.generate(title='Twitcher', version='0.1')


def api(request):
    here = os.path.dirname(__file__)
    template = os.path.join(here, 'templates', 'swagger_ui.html')
    return FileResponse(template, request=request)
