import logging
logger = logging.getLogger(__name__)


def includeme(config):
    config.add_route('providers', '/providers')
    config.add_route('get_capabilities', '/providers/{provider_name}')
