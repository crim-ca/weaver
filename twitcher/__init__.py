from pyramid.config import Configurator
from pyramid.authentication import BasicAuthAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

from twitcher.security import groupfinder, root_factory
from twitcher import owsproxy, rpcinterface
from twitcher.models import mongodb

import logging
logger = logging.getLogger(__name__)

def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings, root_factory=root_factory)

    # beaker session
    config.include('pyramid_beaker')

    # include twitcher components
    config.include(rpcinterface)
    config.include(owsproxy)
        
    # Security policies
    authn_policy = BasicAuthAuthenticationPolicy(check=groupfinder, realm="Birdhouse")
    authz_policy = ACLAuthorizationPolicy()
    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)

    # routes 
    config.add_route('home', '/')

    # MongoDB
    # http://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/database/mongodb.html
    # maybe use event to register mongodb    
    config.registry.db = mongodb(config.registry)

    def add_db(request):
        db = config.registry.db
        #if db_url.username and db_url.password:
        #    db.authenticate(db_url.username, db_url.password)
        return db

    config.add_request_method(add_db, 'db', reify=True)
    
    config.scan()

    return config.make_wsgi_app()

