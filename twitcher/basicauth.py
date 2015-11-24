from pyramid.authentication import BasicAuthAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.security import (
        Allow,
        Everyone,
        ALL_PERMISSIONS)

import logging
logger = logging.getLogger(__name__)


Admin = 'group:admin'

def groupfinder(username, password, request):
    if username == 'admin':
        return [Admin]
    else:
        return []
    
class RootFactory(object):
    __acl__ = [
        (Allow, Everyone, 'view'),
        (Allow, Admin, ALL_PERMISSIONS)
        ]

    def __init__(self, request):
        pass

def root_factory(request):
    return RootFactory(request)


def includeme(config):
    # Security policies for basic auth
    authn_policy = BasicAuthAuthenticationPolicy(check=groupfinder, realm="Birdhouse")
    authz_policy = ACLAuthorizationPolicy()
    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)
    config.set_root_factory(root_factory)
