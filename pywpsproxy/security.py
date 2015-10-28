from pyramid.exceptions import HTTPForbidden

import logging
logger = logging.getLogger(__name__)

Admin = 'group.admin'

def groupfinder(username, password, request):
    if username == 'admin':
        return [Admin]
    else:
        return []
    return HTTPForbidden()


# Authentication and Authorization

from pyramid.security import (
        Allow,
        Everyone,
        ALL_PERMISSIONS)


class Root():
    __acl__ = [
        (Allow, Everyone, 'view'),
        (Allow, Admin, ALL_PERMISSIONS)
        ]

    def __init__(self, request):
        self.request = request

def root_factory(request):
    return Root(request)
