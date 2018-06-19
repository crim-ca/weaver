from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
import os
from magpie.models import get_user
from ziggurat_foundations.models import groupfinder

def includeme(config):

    magpie_secret = os.getenv('MAGPIE_SECRET')
    magpie_secret = config.get_settings().get('magpie.secret', magpie_secret)

    authn_policy = AuthTktAuthenticationPolicy(
        magpie_secret,
        callback=groupfinder,
    )
    authz_policy = ACLAuthorizationPolicy()

    config.set_request_property(get_user, 'user', reify=True)
    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)