from pyramid.view import view_config
from pyramid.httpexceptions import (HTTPForbidden, HTTPBadRequest,
                                    HTTPBadGateway, HTTPNotAcceptable)
from models import add_service, clear

import logging
logger = logging.getLogger(__name__)

class Registry(object):
    def __init__(self, request):
        self.request = request
        self.session = self.request.session

    @view_config(route_name='add_service', renderer='json')
    def add_service(self):
        url = self.request.params.get('url')
        identifier = self.request.params.get('identifier')
        if url is None:
            return HTTPBadRequest()
        # TODO: check url
        service = add_service(self.request, url=url, identifier=identifier)
        return dict(identifier=service['identifier'], url=service['url'])

    @view_config(route_name='clear_services', renderer='json')
    def clear(self):
        clear(self.request)
        return dict()


