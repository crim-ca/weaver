from pyramid.view import view_config

from pywpsproxy import models

import logging
logger = logging.getLogger(__name__)

class Admin(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

    @view_config(route_name='create_token', renderer='json')
    def create_token(self):
        token = models.create_token(self.request)
        return dict(token=token['identifier'])
