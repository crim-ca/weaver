from pyramid.view import view_config

import logging
logger = logging.getLogger(__name__)

class Home(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

    @view_config(route_name='home', renderer='json')
    def view(self):
        return {'message': 'welcome to the real world'}
