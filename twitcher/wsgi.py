from twitcher.middleware import OWSSecurityMiddleware
from twitcher import wpsapp

def wpsapp_factory(global_config, **local_conf):
    return OWSSecurityMiddleware(wpsapp.app)
