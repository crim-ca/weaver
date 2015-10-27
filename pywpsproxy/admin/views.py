from pyramid.view import view_config
from pyramid.httpexceptions import (HTTPForbidden, HTTPBadRequest,
                                    HTTPBadGateway, HTTPNotAcceptable)
from pywpsproxy import models

import logging
logger = logging.getLogger(__name__)

class Admin(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

    @view_config(route_name='register_service', renderer='json')
    def register_service(self):
        url = self.request.params['url']
        if url is None:
            return HTTPBadRequest()
        # TODO: check url
        service = models.register_service(self.request, url=url)
        return dict(service=service['identifier'])

    @view_config(route_name='create_token', renderer='json')
    def create_token(self):
        token = models.create_token(self.request)
        return dict(token=token['identifier'])
