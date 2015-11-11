from pyramid.config import Configurator
#from pyramid.events import subscriber
from pyramid.events import NewRequest
#from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authentication import BasicAuthAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

from twitcher.security import groupfinder, root_factory
from twitcher import owsproxy

import logging
logger = logging.getLogger(__name__)

def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    config = Configurator(settings=settings, root_factory=root_factory)

    # pyramid xml-rpc
    # http://docs.pylonsproject.org/projects/pyramid-rpc/en/latest/xmlrpc.html
    config.include('pyramid_rpc.xmlrpc')
    config.add_xmlrpc_endpoint('api', '/RPC2')

    # beaker session
    config.include('pyramid_beaker')

    # owsproxy
    config.include(owsproxy)
        
    # Security policies
    ## authn_policy = AuthTktAuthenticationPolicy(
    ##     settings['twitcher.secret'], callback=groupfinder,
    ##     hashalg='sha512')
    authn_policy = BasicAuthAuthenticationPolicy(check=groupfinder, realm="Birdhouse")
    authz_policy = ACLAuthorizationPolicy()
    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)

    # static views (stylesheets etc)
    config.add_static_view('static', 'static', cache_max_age=3600)

    # routes 
    config.add_route('home', '/')

    # MongoDB
    # TODO: maybe move this to models.py?
    #@subscriber(NewRequest)
    def add_mongodb(event):
        settings = event.request.registry.settings
        if settings.get('db') is None:
            try:
                from .models import mongodb
                settings['db'] = mongodb(event.request.registry)
            except:
                logger.exception('Could not connect to mongodb')
        event.request.db = settings.get('db')
    config.add_subscriber(add_mongodb, NewRequest)
    
    config.scan()

    return config.make_wsgi_app()

