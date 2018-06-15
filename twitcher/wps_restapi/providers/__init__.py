import logging
logger = logging.getLogger(__name__)


def includeme(config):
    config.add_route('providers', '/providers')
    config.add_route('provider', '/providers/{provider_name}')
