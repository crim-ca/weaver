from pyramid.view import view_config
from pyramid.httpexceptions import (HTTPForbidden, HTTPBadRequest,
                                    HTTPBadGateway, HTTPNotAcceptable)

from models import add_service, remove_service, list_services, clear

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
            return HTTPBadRequest("url parameter is required.")
        try:
            service = add_service(self.request, url=url, identifier=identifier)
        except Exception as err:
            return HTTPBadRequest("Could not add service: %s" % err.message)
        return dict(identifier=service['identifier'], url=service['url'])

    @view_config(route_name='remove_service', renderer='json')
    def remove_service(self):
        identifier = self.request.params.get('identifier')
        if identifier is None:
            return HTTPBadRequest("identifier parameter is required.")
        try:
            remove_service(self.request, identifier=identifier)
        except Exception as err:
            return HTTPBadRequest("Could not remove service: %s" % err.message)
        return {}

    @view_config(route_name='list_services', renderer='json')
    def list_services(self):
        services = []
        try:
            services = list_services(self.request)
        except Exception as err:
            return HTTPBadRequest("Could not list services: %s" % err.message)
        return services

    @view_config(route_name='clear_services', renderer='json')
    def clear(self):
        clear(self.request)
        return dict()


