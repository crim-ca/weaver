from pyramid.httpexceptions import HTTPUnauthorized
from pyramid.security import forget
from pyramid.view import forbidden_view_config
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
    logger.error("u=%s, p=%s", request.username, request.password)
    if request.username and request.password:
        if username == request.username and password == request.password:
            return [Admin]
        else:
            return []
    else:
        # Warning: no access restrictions!
        return [Admin]


class RootFactory(object):
    __acl__ = [
        (Allow, Everyone, 'view'),
        (Allow, Admin, ALL_PERMISSIONS)
    ]

    def __init__(self, request):
        pass


def root_factory(request):
    return RootFactory(request)


@forbidden_view_config()
def basic_challenge(request):
    response = HTTPUnauthorized()
    response.headers.update(forget(request))
    return response


def _get_username(request):
    settings = request.registry.settings
    if 'twitcher.username' in settings:
        username = settings['twitcher.username']
        if username:
            username = username.strip()
            if len(username) > 2:
                return username
    return None


def _get_password(request):
    settings = request.registry.settings
    if 'twitcher.password' in settings:
        password = settings['twitcher.password']
        if password:
            password = password.strip()
            if len(password) > 2:
                return password
    return None


def auth_activated(registry):
    settings = registry.settings
    username = settings.get('twitcher.username')
    if username:
        if len(username.strip()) > 2:
            return True
    return False


def includeme(config):
    if auth_activated(config.registry):
        logger.debug("basic authentication is activated.")
        # Security policies for basic auth
        authn_policy = BasicAuthAuthenticationPolicy(check=groupfinder, realm="Birdhouse")
        authz_policy = ACLAuthorizationPolicy()
        config.set_authentication_policy(authn_policy)
        config.set_authorization_policy(authz_policy)
        config.set_root_factory(root_factory)
        config.add_request_method(_get_username, 'username', reify=True)
        config.add_request_method(_get_password, 'password', reify=True)
