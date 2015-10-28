from pyramid.view import view_config, view_defaults

import logging
logger = logging.getLogger(__name__)

from registry.models import list_services

@view_defaults(permission='view')
class Home(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

    @view_config(route_name='home', renderer='json')
    def view(self):
        services = list_services(self.request)
        return {'services': services}
