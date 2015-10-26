import logging
logger = logging.getLogger(__name__)

def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    from pyramid.config import Configurator
    #from pyramid.events import subscriber
    #from pyramid.events import NewRequest
    #from pyramid.authentication import AuthTktAuthenticationPolicy
    #from pyramid.authorization import ACLAuthorizationPolicy
    #from phoenix.security import groupfinder, root_factory

    # security
    # TODO: move to security
    #authn_policy = AuthTktAuthenticationPolicy(
    #    settings.get('authomatic.secret'), callback=groupfinder, hashalg='sha512')
    #authz_policy = ACLAuthorizationPolicy()
    #config = Configurator(root_factory=root_factory, settings=settings)
    config = Configurator(settings=settings)
    #config.set_authentication_policy(authn_policy)
    #config.set_authorization_policy(authz_policy)

    # beaker session
    config.include('pyramid_beaker')

    # owsproxy
    from pywpsproxy import owsproxy
    config.include(owsproxy)
        
    # mailer
    #config.include('pyramid_mailer')

    # static views (stylesheets etc)
    config.add_static_view('static', 'static', cache_max_age=3600)

    # routes 
    config.add_route('home', '/')
    
    config.scan('pywpsproxy')

    return config.make_wsgi_app()

