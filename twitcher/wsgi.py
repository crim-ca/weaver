from twitcher.middleware import OWSSecurityMiddleware
from twitcher import wpsapp

import logging
logger = logging.getLogger(__name__)

def wpsapp_factory(global_config, **local_conf):
    if True:
        raise Exception('global_config %s, local_conf %s' % (global_config, local_conf))
    
    return OWSSecurityMiddleware(wpsapp.app)
