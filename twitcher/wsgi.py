from twitcher.middleware import DummyMiddleware
from twitcher import wpsapp

def wpsapp_factory(global_config, **local_conf):
    return DummyMiddleware(wpsapp.app)
