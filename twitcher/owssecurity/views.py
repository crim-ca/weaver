from pyramid.view import view_config, view_defaults

from .models import create_token

import logging
logger = logging.getLogger(__name__)

@view_defaults(permission='admin')
class OWSSecurity(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

    @view_config(route_name='create_token', renderer='json')
    def create_token(self):
        token = create_token(self.request)
        return dict(token=token['identifier'])
